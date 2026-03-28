"""tests/run_with_openai.py — Test avec vraie API OpenAI, sans Outlook ni Dolibarr.

Ce script charge les emails des datasets et appelle VRAIMENT GPT pour :
  ✓ extract_client_data()          — extraction client réelle
  ✓ analyse_besoin_impression()    — analyse impression réelle
  ✓ post_process_composants()      — imposition + score Python
  ✓ build_lines()                  — construction lignes Dolibarr

Moqué (pas d'appel réseau) :
  ~ Outlook  → corps email depuis dataset JSON
  ~ Dolibarr → pas d'appel, résultat simulé

Prérequis :
  OPENAI_API_KEY dans .env (les autres clés peuvent rester en placeholder)

Usage :
  python tests/run_with_openai.py               # tous les datasets
  python tests/run_with_openai.py 01            # dataset 01 uniquement
  python tests/run_with_openai.py 02 --compare  # compare IA réelle vs mock dataset
"""

# ── sys.path avant tout import src ────────────────────────────────────────
import sys as _sys
import os as _os
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

# Charger .env avant config.py (qui fait os.environ["OPENAI_API_KEY"])
from dotenv import load_dotenv
load_dotenv()

# Placeholders pour les clés non encore disponibles
_os.environ.setdefault("OUTLOOK_TENANT_ID", "00000000-0000-0000-0000-000000000000")
_os.environ.setdefault("OUTLOOK_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
_os.environ.setdefault("OUTLOOK_CLIENT_SECRET", "placeholder")
_os.environ.setdefault("OUTLOOK_REFRESH_TOKEN", "placeholder")

# ── Imports ────────────────────────────────────────────────────────────────
import asyncio
import json
import sys
import textwrap
import time
from pathlib import Path

from src.connectors.openai_client import OpenAIClient
from src.utils.html_cleaner import prepare_email_for_ai
from src.utils.imposition import post_process_composants
from src.utils.devis_builder import build_lines

DATASET_DIR = Path(__file__).parent / "dataset"

# ── Couleurs terminal ──────────────────────────────────────────────────────
RESET  = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
GREEN  = "\033[32m"; YELLOW = "\033[33m"; RED = "\033[31m"
CYAN   = "\033[36m"; BLUE = "\033[34m"; GRAY = "\033[90m"
MAGENTA = "\033[35m"

def c(color, text): return f"{color}{text}{RESET}"
def hr(ch="─", w=70): print(c(GRAY, ch * w))
def section(t): print(); hr("═"); print(c(BOLD+CYAN, f"  {t}")); hr("═")
def subsection(t): print(); print(c(BOLD, f"  ▸ {t}")); hr("·", 50)
def info(m): print(f"    {c(GRAY,'·')}  {m}")
def ok(m): print(f"    {c(GREEN,'✓')}  {m}")
def warn(m): print(f"    {c(YELLOW,'⚠')}  {c(YELLOW, m)}")
def fail(m): print(f"    {c(RED,'✗')}  {c(RED, m)}")
def ai_tag(): return c(MAGENTA, "[GPT]")

def strip_html(s):
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()

def check(label, val, exp=None):
    if exp is None:
        print(f"    {c(GREEN,'✓')} {label}: {c(BOLD, str(val))}")
    else:
        match = str(val) == str(exp)
        st = c(GREEN,'✓') if match else c(YELLOW,'≠')
        detail = str(val)
        if not match:
            detail += f"  {c(GRAY, f'(dataset: {exp})')}"
        print(f"    {st} {label}: {c(BOLD, detail)}")


# ── Comparaison champ à champ IA réelle vs mock ────────────────────────────

def comparer_client(real: dict, mock: dict):
    champs = ["soc_nom", "email", "contact_nom", "contact_prenom", "nom_projet"]
    print()
    print(f"    {'Champ':<20} {'IA réelle':<30} {'Mock dataset':<30}")
    hr("·", 70)
    for champ in champs:
        r = str(real.get(champ) or "—")
        m = str(mock.get(champ) or "—")
        match = r.lower().strip() == m.lower().strip()
        sym = c(GREEN, "=") if match else c(YELLOW, "≠")
        print(f"    {sym} {champ:<18} {c(BOLD, r[:28]):<38} {c(DIM, m[:28])}")


def comparer_composants(real_list: list, mock_list: list):
    for i, (r, m) in enumerate(zip(real_list, mock_list), 1):
        print(f"\n    {c(BOLD, f'Composant {i} :')} {r.get('produit','?')}")
        champs = [
            "intitule_maitre", "produit", "nombre_pages",
            "type_impression", "support_grammage", "type_finition",
            "type_reliure", "quantite",
        ]
        for champ in champs:
            rv = str(r.get(champ) or "—")
            mv = str(m.get(champ) or "—")
            match = rv.lower().strip() == mv.lower().strip()
            sym = c(GREEN,"=") if match else c(YELLOW,"≠")
            print(f"      {sym} {champ:<20} IA: {c(BOLD, rv[:25]):<35} Mock: {c(DIM, mv[:25])}")

        # Format ouvert
        rfo = r.get("format_ouvert_mm") or {}
        mfo = m.get("format_ouvert_mm") or {}
        fo_match = rfo.get("largeur") == mfo.get("largeur") and rfo.get("hauteur") == mfo.get("hauteur")
        sym = c(GREEN,"=") if fo_match else c(YELLOW,"≠")
        fo_real = f"{rfo.get('largeur')}×{rfo.get('hauteur')}mm"
        fo_mock = f"{mfo.get('largeur')}×{mfo.get('hauteur')}mm"
        print(f"      {sym} {'format_ouvert_mm':<20} IA: {c(BOLD, fo_real):<35} Mock: {c(DIM, fo_mock)}")


# ── Runner d'un dataset ────────────────────────────────────────────────────

async def run_dataset(path: Path, compare: bool = False) -> dict:
    with path.open(encoding="utf-8") as f:
        ds = json.load(f)

    meta = ds["meta"]
    email = ds["email"]
    mock_client = ds["mock_ai_client"]
    mock_impression = ds["mock_ai_impression"]
    expected = ds["expected"]

    section(f"Dataset {meta['id']} — {meta['description']}")
    print(f"  {c(DIM, meta['scenario'])}")

    ai = OpenAIClient()

    # ── Email + HTML cleaning ──────────────────────────────────────────────
    subsection("Email + HTML Cleaner")
    body_html = email["body"]["content"]
    body_clean = prepare_email_for_ai(body_html)
    info(f"HTML brut  : {len(body_html)} chars → nettoyé : {len(body_clean)} chars")
    info(f"Expéditeur : {email['sender']['name']} <{email['sender']['address']}>")

    # ── Appel IA — Extraction client ──────────────────────────────────────
    subsection(f"Extraction client {ai_tag()} — appel GPT réel")
    sender_info = f"{email['sender']['name']} <{email['sender']['address']}>"

    t0 = time.perf_counter()
    real_client = await ai.extract_client_data(sender_info, body_clean)
    t1 = time.perf_counter()

    # Filtrer email interne
    from src import config
    email_val = real_client.get("email") or ""
    if any(excl in email_val for excl in config.INPRESSCO_EXCLUDE_EMAILS):
        real_client["email"] = None

    info(f"Temps appel : {t1-t0:.2f}s")
    print()

    check("soc_nom",       real_client.get("soc_nom"),         mock_client.get("soc_nom"))
    check("email",         real_client.get("email"),            mock_client.get("email"))
    check("contact",       f"{real_client.get('contact_prenom','')} {real_client.get('contact_nom','')}".strip(),
                           f"{mock_client.get('contact_prenom','')} {mock_client.get('contact_nom','')}".strip())
    check("nom_projet",    real_client.get("nom_projet"),       mock_client.get("nom_projet"))

    # Vérif exclusions InPressco
    soc = (real_client.get("soc_nom") or "").lower()
    if any(e.lower() in soc for e in config.INPRESSCO_EXCLUDE_NAMES):
        fail("ALERTE : soc_nom contient une donnée InPressco !")
    else:
        ok("Exclusion InPressco : OK")

    if compare:
        print()
        print(c(DIM, "    ── Comparaison détaillée client ──"))
        comparer_client(real_client, mock_client)

    # ── Appel IA — Analyse impression ─────────────────────────────────────
    subsection(f"Analyse impression {ai_tag()} — appel GPT réel")

    t0 = time.perf_counter()
    real_impression = await ai.analyse_besoin_impression(body_clean)
    t1 = time.perf_counter()

    info(f"Temps appel : {t1-t0:.2f}s")

    real_composants_raw = real_impression.get("composants_isoles", [])
    mock_composants_raw = mock_impression.get("composants_isoles", [])

    check("nb composants", len(real_composants_raw), len(mock_composants_raw))
    check("synthese",      real_impression.get("synthese_contexte","")[:60]+"…")
    check("date livraison", real_impression.get("date_livraison_souhaitee"),
                            mock_impression.get("date_livraison_souhaitee"))

    if compare and real_composants_raw and mock_composants_raw:
        print()
        print(c(DIM, "    ── Comparaison détaillée composants ──"))
        comparer_composants(real_composants_raw, mock_composants_raw)

    # ── Post-processing Python ─────────────────────────────────────────────
    subsection("Post-processing Python — imposition + score")

    real_composants = post_process_composants([dict(c2) for c2 in real_composants_raw])

    for i, comp in enumerate(real_composants, 1):
        produit = comp.get("produit", "?")
        intitule = comp.get("intitule_maitre", "?")
        print(f"\n    {c(BOLD, f'[{i}] {intitule} — {produit}')}")

        imp700 = comp.get("IMPOSITION_BRUTE_700x1000") or {}
        imp330 = comp.get("IMPOSITION_BRUTE_330x480") or {}
        f700 = (imp700.get("calcul_feuilles") or {}).get("feuilles", "?")
        f330 = (imp330.get("calcul_feuilles") or {}).get("feuilles", "?")

        fo = comp.get("format_ouvert_mm") or {}
        info(f"  Format ouvert  : {fo.get('largeur')}×{fo.get('hauteur')} mm")
        info(f"  700×1000       : {imp700.get('poses_total','?')} poses → {f700} feuilles")
        info(f"  330×480        : {imp330.get('poses_total','?')} poses → {f330} feuilles")

        score_data = comp.get("SCORE_DEVIS") or {}
        score = score_data.get("score_sur_10")
        score_color = GREEN if (score or 0) >= 7 else (YELLOW if (score or 0) >= 5 else RED)
        info(f"  Score          : {c(score_color+BOLD, str(score))}/10")

        alertes = score_data.get("alertes", [])
        for a in alertes:
            warn(f"  {a}")

    # ── Build lines ────────────────────────────────────────────────────────
    subsection("Build lines Dolibarr")

    synthese = real_impression.get("synthese_contexte", "")
    lines = build_lines(real_composants, synthese)
    exp_lines = expected.get("expected_nb_lines_devis") or expected.get("nb_lines_devis")

    check("Nb lignes devis", len(lines), exp_lines)
    print()

    for line in lines:
        pt = line.get("product_type")
        qty = line.get("qty", "?")
        desc_short = textwrap.shorten(strip_html(line.get("desc","")), 75, placeholder="…")

        if pt == 9 and line.get("special_code") == config.DOLIBARR_SPECIAL_CODE_CONTEXTE:
            label = c(BLUE, "L.0 [contexte ]")
        elif pt == 9:
            label = c(CYAN, "L.A [descriptif]")
        else:
            label = c(GREEN, f"L.B [prix q={qty:<5}]")
        print(f"    {label}  {desc_short}")

    # ── Résumé dataset ─────────────────────────────────────────────────────
    print()
    lines_ok = len(lines) == exp_lines
    comp_ok  = len(real_composants) == (expected.get("expected_nb_composants") or expected.get("nb_composants"))

    return {
        "id": meta["id"],
        "nb_composants": len(real_composants),
        "nb_lines": len(lines),
        "ok": lines_ok and comp_ok,
        "client_soc_nom": real_client.get("soc_nom"),
        "client_email": real_client.get("email"),
    }


# ── Point d'entrée ─────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    compare = "--compare" in args or "-c" in args
    ids = [a for a in args if a.isdigit()]

    files = sorted(DATASET_DIR.glob("email_*.json"))
    if ids:
        files = [f for f in files if any(f.name.startswith(f"email_{i.zfill(2)}") for i in ids)]

    if not files:
        print(c(RED, "Aucun dataset trouvé.")); sys.exit(1)

    results = []
    for file in files:
        result = await run_dataset(file, compare=compare)
        results.append(result)

    section("Résumé global")
    ok_count = sum(1 for r in results if r["ok"])
    for r in results:
        print(f"  {c(GREEN,'✓ PASS') if r['ok'] else c(RED,'✗ FAIL')}  "
              f"Dataset {r['id']} — "
              f"{r['nb_composants']} composant(s), {r['nb_lines']} ligne(s) — "
              f"{r['client_soc_nom']} / {r['client_email'] or 'email=null'}")

    print()
    if ok_count == len(results):
        print(c(GREEN+BOLD, f"  Tous les datasets passent ({ok_count}/{len(results)}) ✓"))
    else:
        print(c(YELLOW+BOLD, f"  {len(results)-ok_count} dataset(s) avec écart ({ok_count}/{len(results)} OK)"))
    print()


if __name__ == "__main__":
    asyncio.run(main())
