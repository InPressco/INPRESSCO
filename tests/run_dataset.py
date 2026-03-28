"""tests/run_dataset.py — Runner de test autonome, sans aucune clé API.

Ce script simule le pipeline complet (steps s02→s07) en remplaçant
les appels aux APIs externes par les données mockées des fichiers dataset/.

Ce qui est testé (100% Python, zéro API) :
  ✓ html_cleaner.prepare_email_for_ai()     — nettoyage HTML
  ✓ s03_clean_data logic                    — exclusion données InPressco
  ✓ imposition.post_process_composants()    — calcul poses + feuilles + score
  ✓ devis_builder.build_lines()             — construction lignes Dolibarr

Ce qui est mocké (remplacé par les données du dataset) :
  ~ s01 : récupération Outlook              → email dans le JSON
  ~ s02 : extraction client OpenAI          → mock_ai_client dans le JSON
  ~ s04 : recherche/création Dolibarr       → toujours socid=999 (fictif)
  ~ s06 : analyse impression OpenAI         → mock_ai_impression dans le JSON
  ~ s08-s11 : Dolibarr + Outlook            → non simulés (affichage seulement)

Usage :
  python tests/run_dataset.py                    # tous les datasets
  python tests/run_dataset.py 01                 # dataset 01 uniquement
  python tests/run_dataset.py 02 --verbose       # avec détail des lignes HTML
"""

# ── Patch sys.path + env AVANT tout import de src ─────────────────────────
import os
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-no-api-needed")
os.environ.setdefault("OUTLOOK_TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("OUTLOOK_CLIENT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("OUTLOOK_CLIENT_SECRET", "test-secret-dummy")
os.environ.setdefault("OUTLOOK_REFRESH_TOKEN", "test-refresh-dummy")
os.environ.setdefault("DOLIBARR_API_KEY", "test-dolibarr-dummy")

import json
import re
import sys
import textwrap
from pathlib import Path

# Maintenant les imports src sont sûrs
from src.utils.html_cleaner import prepare_email_for_ai
from src.utils.imposition import post_process_composants
from src.utils.devis_builder import build_lines, nettoyer_finition
from src import config

DATASET_DIR = Path(__file__).parent / "dataset"


# ── Couleurs terminal ──────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"


def c(color, text):
    return f"{color}{text}{RESET}"


def hr(char="─", width=70):
    print(c(GRAY, char * width))


def section(title):
    print()
    hr("═")
    print(c(BOLD + CYAN, f"  {title}"))
    hr("═")


def subsection(title):
    print()
    print(c(BOLD, f"  ▸ {title}"))
    hr("·", 50)


# ── Helpers ────────────────────────────────────────────────────────────────

def strip_html_for_display(html_str: str) -> str:
    """Enlève les balises pour afficher le HTML de manière lisible."""
    text = re.sub(r"<[^>]+>", "", html_str or "")
    text = re.sub(r"\s+", " ", text)
    return text[:200].strip()


def check(label, value, expected=None, invert=False):
    """Affiche un check avec statut."""
    if expected is None:
        status = c(GREEN, "✓")
        detail = str(value)
    elif invert:
        ok = expected not in str(value).lower()
        status = c(GREEN, "✓") if ok else c(RED, "✗")
        detail = str(value)
    else:
        ok = value == expected
        status = c(GREEN, "✓") if ok else c(RED, "✗")
        detail = f"{value}" + (f"  {c(GRAY, f'(attendu: {expected})')}" if not ok else "")

    print(f"    {status} {label}: {c(BOLD, detail)}")


def warn(msg):
    print(f"    {c(YELLOW, '⚠')}  {c(YELLOW, msg)}")


def info(msg):
    print(f"    {c(GRAY, '·')}  {msg}")


# ── Logique de vérification des exclusions InPressco ───────────────────────

def appliquer_exclusions(client_data: dict) -> dict:
    """Applique la même logique que s03_clean_data."""
    data = dict(client_data)

    # Trim
    for k, v in data.items():
        if isinstance(v, str):
            data[k] = v.strip()

    # Email interne → null
    email = data.get("email") or ""
    if any(excl in email for excl in config.INPRESSCO_EXCLUDE_EMAILS):
        data["email"] = None

    # soc_nom InPressco → null
    soc = (data.get("soc_nom") or "").lower()
    if any(excl.lower() in soc for excl in config.INPRESSCO_EXCLUDE_NAMES):
        data["soc_nom"] = None

    data["creation_si_non_trouve"] = False
    return data


# ── Runner d'un dataset ────────────────────────────────────────────────────

def run_dataset(path: Path, verbose: bool = False) -> dict:
    with path.open(encoding="utf-8") as f:
        ds = json.load(f)

    meta = ds["meta"]
    email = ds["email"]
    mock_client = ds["mock_ai_client"]
    mock_impression = ds["mock_ai_impression"]
    expected = ds["expected"]

    section(f"Dataset {meta['id']} — {meta['description']}")
    print(f"  {c(DIM, meta['scenario'])}")

    # ── ÉTAPE 1 : Email source ─────────────────────────────────────────────
    subsection("Email source (simulé Outlook)")
    info(f"Sujet     : {email['subject']}")
    info(f"Expéditeur: {email['sender']['name']} <{email['sender']['address']}>")
    info(f"Reçu le   : {email['receivedDateTime']}")
    info(f"PJ        : {email.get('hasAttachments', False)}")

    # ── ÉTAPE 2 : HTML Cleaner ─────────────────────────────────────────────
    subsection("HTML Cleaner — prepare_email_for_ai()")
    body_html = email["body"]["content"]
    body_clean = prepare_email_for_ai(body_html)

    info(f"Longueur HTML brut : {len(body_html)} chars")
    info(f"Longueur nettoyé   : {len(body_clean)} chars  ({int(len(body_clean)/len(body_html)*100)}% du brut)")
    print()
    print(c(GRAY, "    Corps nettoyé :"))
    for line in body_clean.splitlines():
        if line.strip():
            print(f"    {c(DIM, '│')} {line.strip()}")

    # ── ÉTAPE 3 : Extraction client (mocké) + exclusions ──────────────────
    subsection("Extraction client (mocké IA) + s03 exclusions")
    client_data = appliquer_exclusions(mock_client)

    check("soc_nom", client_data.get("soc_nom"))
    check("email", client_data.get("email"))
    check("contact", f"{client_data.get('contact_prenom', '')} {client_data.get('contact_nom', '')}".strip())
    check("nom_projet", client_data.get("nom_projet"))

    # Vérification exclusions InPressco
    soc = (client_data.get("soc_nom") or "").lower()
    email_val = client_data.get("email") or ""
    inpressco_in_soc = any(e.lower() in soc for e in config.INPRESSCO_EXCLUDE_NAMES)
    inpressco_in_email = "@in-pressco.com" in email_val

    if inpressco_in_soc:
        print(c(RED, "    ✗ ALERTE : soc_nom contient une donnée InPressco !"))
    else:
        print(c(GREEN, "    ✓ Exclusion InPressco soc_nom : OK"))

    if inpressco_in_email:
        print(c(RED, "    ✗ ALERTE : email InPressco non filtré !"))
    else:
        print(c(GREEN, "    ✓ Exclusion InPressco email : OK"))

    # ── ÉTAPE 4 : Client Dolibarr (mocké) ─────────────────────────────────
    subsection("Dolibarr — Tiers (simulé)")
    socid_fictif = 999
    info(f"Résultat simulé : socid={socid_fictif} (fictif — pas d'appel API)")
    info(f"Comportement attendu : {expected.get('client_crm', '?')}")

    # ── ÉTAPE 5 : Analyse impression (mocké) + imposition Python ──────────
    subsection("Analyse impression (mocké IA) + imposition Python")

    composants_raw = mock_impression["composants_isoles"]
    info(f"Composants IA bruts   : {len(composants_raw)}")

    # POST-PROCESSING PYTHON (imposition + score)
    composants = post_process_composants([dict(c) for c in composants_raw])
    info(f"Composants post-traités: {len(composants)}")
    print()

    for i, comp in enumerate(composants, 1):
        produit = comp.get("produit", "?")
        intitule = comp.get("intitule_maitre", "?")
        print(f"    {c(BOLD, f'[{i}] {intitule} — {produit}')}")

        ff = comp.get("format_ferme_mm") or {}
        fo = comp.get("format_ouvert_mm") or {}
        info(f"  Format fermé  : {ff.get('largeur')}×{ff.get('hauteur')} mm")
        info(f"  Format ouvert : {fo.get('largeur')}×{fo.get('hauteur')} mm")
        info(f"  Impression    : {comp.get('type_impression')}")
        info(f"  Grammage      : {comp.get('support_grammage') or c(RED, 'NON RENSEIGNÉ')}")
        info(f"  Quantité      : {comp.get('quantite')} ex")

        imp700 = comp.get("IMPOSITION_BRUTE_700x1000") or {}
        imp330 = comp.get("IMPOSITION_BRUTE_330x480") or {}
        f700 = (imp700.get("calcul_feuilles") or {}).get("feuilles", "?")
        f330 = (imp330.get("calcul_feuilles") or {}).get("feuilles", "?")
        info(f"  Imposition 700×1000 : {imp700.get('poses_total', '?')} poses → {f700} feuilles")
        info(f"  Imposition 330×480  : {imp330.get('poses_total', '?')} poses → {f330} feuilles")

        score_data = comp.get("SCORE_DEVIS") or {}
        score = score_data.get("score_sur_10")
        score_color = GREEN if (score or 0) >= 7 else (YELLOW if (score or 0) >= 5 else RED)
        info(f"  Score         : {c(score_color + BOLD, str(score))}/10")

        alertes = score_data.get("alertes", [])
        if alertes:
            for a in alertes:
                warn(f"  {a}")
        else:
            info(f"  {c(GREEN, 'Aucune alerte')}")
        print()

    # ── ÉTAPE 6 : Construction lignes devis ───────────────────────────────
    subsection("Build lines — devis_builder.build_lines()")
    synthese = mock_impression["synthese_contexte"]
    lines = build_lines(composants, synthese)

    nb_lines = len(lines)
    check(
        "Nombre de lignes",
        nb_lines,
        expected.get("expected_nb_lines_devis") or expected.get("nb_lines_devis")
    )
    print()

    for i, line in enumerate(lines):
        pt = line.get("product_type")
        sc = line.get("special_code") or line.get("txtva") and "—"
        qty = line.get("qty") or line.get("qty", "?")
        desc_raw = line.get("desc", "")
        desc_short = strip_html_for_display(desc_raw)

        if pt == 9 and line.get("special_code") == config.DOLIBARR_SPECIAL_CODE_CONTEXTE:
            label = c(BLUE, "Ligne 0")
            tag = c(GRAY, "[contexte]")
        elif pt == 9:
            label = c(CYAN, "Ligne A")
            tag = c(GRAY, "[descriptif]")
        else:
            label = c(GREEN, "Ligne B")
            tag = c(GRAY, f"[prix, qty={qty}]")

        print(f"    {label} {tag}")
        print(f"    {c(DIM, '  desc:')} {textwrap.shorten(desc_short, 80, placeholder='...')}")

        if verbose and pt == 0:
            opts = (line.get("array_options") or {}).get("options_analysen8n", "")
            opts_clean = strip_html_for_display(opts)
            if opts_clean:
                print(f"    {c(DIM, '  n8n :')} {textwrap.shorten(opts_clean, 100, placeholder='...')}")
        print()

    # ── Comparaison attendu / obtenu ───────────────────────────────────────
    subsection("Synthèse — comparaison vs expected")

    exp_composants = expected.get("expected_nb_composants") or expected.get("nb_composants")
    exp_lines = expected.get("expected_nb_lines_devis") or expected.get("nb_lines_devis")

    check("Nb composants", len(composants), exp_composants)
    check("Nb lignes devis", nb_lines, exp_lines)

    exp_soc = expected.get("soc_nom")
    if exp_soc:
        check("soc_nom", client_data.get("soc_nom"), exp_soc)

    if expected.get("email_client") is None and "email_client" in expected:
        check("email null (interne)", client_data.get("email"), None)

    print()
    return {
        "id": meta["id"],
        "nb_composants": len(composants),
        "nb_lines": nb_lines,
        "ok": nb_lines == exp_lines and len(composants) == exp_composants,
    }


# ── Point d'entrée ─────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    ids = [a for a in args if a.isdigit()]

    files = sorted(DATASET_DIR.glob("email_*.json"))
    if not files:
        print(c(RED, f"Aucun fichier dataset trouvé dans {DATASET_DIR}"))
        sys.exit(1)

    if ids:
        files = [f for f in files if any(f.name.startswith(f"email_{i.zfill(2)}") for i in ids)]

    if not files:
        print(c(RED, f"Aucun dataset correspondant aux IDs : {ids}"))
        sys.exit(1)

    results = []
    for file in files:
        result = run_dataset(file, verbose=verbose)
        results.append(result)

    # Résumé global
    section("Résumé global")
    ok_count = sum(1 for r in results if r["ok"])
    total = len(results)

    for r in results:
        status = c(GREEN, "✓ PASS") if r["ok"] else c(RED, "✗ FAIL")
        print(f"  {status}  Dataset {r['id']} — {r['nb_composants']} composant(s), {r['nb_lines']} ligne(s)")

    print()
    if ok_count == total:
        print(c(GREEN + BOLD, f"  Tous les datasets passent ({ok_count}/{total}) ✓"))
    else:
        print(c(RED + BOLD, f"  {total - ok_count} dataset(s) en échec ({ok_count}/{total} OK)"))
    print()


if __name__ == "__main__":
    main()
