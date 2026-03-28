"""dashboard/app.py — Dashboard de monitoring InPressco Pipeline.

Démarrer avec :
    uvicorn dashboard.app:app --reload --port 8080

Ou directement :
    python -m dashboard.app
"""
import asyncio
import base64
import json
import re
import subprocess
import sys

from src.utils.dolibarr_urls import build_links
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent.parent

# Chargement .env pour les clés Dolibarr (dashboard tourne indépendamment du pipeline)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import os
_DOLIBARR_BASE  = os.environ.get("DOLIBARR_BASE_URL", "")
_DOLIBARR_KEY   = os.environ.get("DOLIBARR_API_KEY", "")
_DOLI_HEADERS   = {"DOLAPIKEY": _DOLIBARR_KEY, "Accept": "application/json"}
_DOLI_WEB       = _DOLIBARR_BASE.removesuffix("/api/index.php")
_N8N_BASE       = os.environ.get("N8N_BASE_URL", "https://srv1196537.hstgr.cloud")
_N8N_KEY        = os.environ.get("N8N_API_KEY", "")
_ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")

_CHAT_SYSTEM = """\
Tu es le moteur IA central du dashboard InPressco.
InPressco est une imprimerie façonnière basée à Aix-les-Bains (73100), spécialisée impression offset et numérique.
Tu aides Nicolas Bompois (fondateur) à piloter son activité au quotidien.

Ce que tu peux faire :
- Analyser les devis, factures, commandes et clients depuis Dolibarr
- Aider à rédiger des réponses ou emails clients
- Calculer des impositions, prix, marges impression
- Comprendre les KPIs du pipeline d'automatisation devis
- Conseiller sur les matières, finitions, formats d'impression

Réponds en français, de façon directe et professionnelle. Sois concis sauf si on te demande du détail.\
"""
LOG_FILE   = ROOT / "pipeline.log"
STAGES_DIR = ROOT / "stages"

# ── Catalogue statique des workflows n8n (depuis debug_flux_a.py) ──────────
_N8N_WORKFLOWS_STATIC = [
    {"id": None,                  "name": "WF1 · Pipeline devis",           "role": "pipeline"},
    {"id": None,                  "name": "WF2 · Factures fournisseurs",    "role": "finance"},
    {"id": "9ZWy7Wqdh8T17zXI",   "name": "WF3 · Analyse besoin SOLARIS",   "role": "pipeline"},
    {"id": None,                  "name": "WF4 · Archivage Outlook",        "role": "pipeline"},
    {"id": "SP9wUTm5KWQhDhtN",   "name": "WF5 · Trouver/créer tiers",      "role": "crm"},
    {"id": None,                  "name": "WF6 · Visuel packaging",         "role": "design"},
    {"id": "gsyqoijimVdBj0Nz",   "name": "WF7 · Synchro clients DB",       "role": "crm"},
    {"id": None,                  "name": "WF8 · Moteur calcul imprimerie", "role": "pipeline"},
    {"id": None,                  "name": "WF9 · Carousel Instagram",       "role": "marketing"},
    {"id": "nGvYO2CtWwrdjF99",   "name": "WF_DOLI · Créer devis/facture",  "role": "finance"},
]

app = FastAPI(title="InPressco Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent), name="static")


# ── Helpers ────────────────────────────────────────────────────────────────

def _read_log_lines(n: int = 200) -> list[str]:
    if not LOG_FILE.exists():
        return []
    with LOG_FILE.open(encoding="utf-8") as f:
        lines = f.readlines()
    return [l.rstrip() for l in lines[-n:]]


def _parse_log_runs(lines: list[str]) -> list[dict]:
    """Extrait les blocs d'exécution depuis le log."""
    runs = []
    current: dict | None = None

    for line in lines:
        if "═" * 10 in line and "démarrage" in line:
            current = {
                "started_at": None,
                "finished_at": None,
                "flux_a": {"status": "unknown", "devis_ref": None, "errors": []},
                "flux_b": {"status": "unknown", "emails_traites": 0, "errors": []},
            }
            # Extraire le timestamp de la ligne précédente si possible
            ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if ts_match:
                current["started_at"] = ts_match.group(1)
        elif current is not None:
            ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            ts = ts_match.group(1) if ts_match else None

            if "Flux A OK" in line:
                current["flux_a"]["status"] = "ok"
                ref_match = re.search(r"devis créé : (\S+)", line)
                if ref_match:
                    current["flux_a"]["devis_ref"] = ref_match.group(1)
            elif "Flux A terminé avec erreurs" in line:
                current["flux_a"]["status"] = "error"
                current["flux_a"]["errors"].append(line)
            elif "aucun email à traiter" in line:
                current["flux_a"]["status"] = "idle"
            elif "Flux B OK" in line:
                current["flux_b"]["status"] = "ok"
                nb_match = re.search(r"(\d+) email", line)
                if nb_match:
                    current["flux_b"]["emails_traites"] = int(nb_match.group(1))
            elif "Flux B terminé avec erreurs" in line:
                current["flux_b"]["status"] = "error"
                current["flux_b"]["errors"].append(line)
            elif "Pipeline terminé" in line:
                if ts:
                    current["finished_at"] = ts
                runs.append(current)
                current = None
            elif "ERROR" in line and current:
                if "flux_a" in current:
                    # Associer l'erreur au flux en cours
                    current["flux_a"]["errors"].append(line.strip())

    return list(reversed(runs))  # Plus récent en premier


def _read_stage_output(stage_num: int) -> dict | None:
    pattern = f"{stage_num:02d}_*"
    matches = list(STAGES_DIR.glob(pattern))
    if not matches:
        return None
    output_file = matches[0] / "output" / "result.json"
    if not output_file.exists():
        return None
    try:
        return json.loads(output_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _last_run_summary() -> dict:
    """Résumé du dernier run depuis le log."""
    lines = _read_log_lines(500)
    runs = _parse_log_runs(lines)
    if not runs:
        return {"status": "never_run", "last_run": None}
    last = runs[0]
    return {
        "status": "ok" if last["flux_a"]["status"] in ("ok", "idle") else "error",
        "last_run": last.get("finished_at") or last.get("started_at"),
        "flux_a": last["flux_a"],
        "flux_b": last["flux_b"],
    }


# ── Routes API ─────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    html_file = Path(__file__).parent / "index.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(html_file)


@app.get("/notice")
async def notice():
    html_file = Path(__file__).parent / "notice.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="notice.html not found")
    return FileResponse(html_file)


@app.get("/admin/dev")
async def admin_dev():
    html_file = Path(__file__).parent / "admin_dev.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="admin_dev.html not found")
    return FileResponse(html_file)


@app.get("/api/status")
async def get_status():
    """Résumé du dernier run + état des stages."""
    summary = _last_run_summary()
    stages = {}
    for i in range(1, 6):
        output = _read_stage_output(i)
        stages[f"stage_{i:02d}"] = {
            "has_output": output is not None,
            "data": output,
        }
    return JSONResponse({"summary": summary, "stages": stages})


@app.get("/api/log")
async def get_log(lines: int = 100):
    """Retourne les N dernières lignes du pipeline.log."""
    if lines > 500:
        lines = 500
    log_lines = _read_log_lines(lines)
    return JSONResponse({"lines": log_lines, "total": len(log_lines)})


@app.get("/api/runs")
async def get_runs(limit: int = 10):
    """Retourne l'historique des runs parsé depuis le log."""
    log_lines = _read_log_lines(1000)
    runs = _parse_log_runs(log_lines)
    return JSONResponse({"runs": runs[:limit]})


@app.get("/api/admin/runs-logs")
async def get_admin_runs_logs():
    """Page admin/dev : runs + log + statut connecteurs."""
    log_lines = _read_log_lines(200)
    runs = _parse_log_runs(_read_log_lines(1000))
    connectors = [
        {
            "id":     "dolibarr",
            "name":   "Dolibarr",
            "ok":     bool(_DOLIBARR_BASE and _DOLIBARR_KEY),
            "detail": _DOLI_WEB or "Non configuré",
        },
        {
            "id":     "n8n",
            "name":   "n8n",
            "ok":     bool(_N8N_KEY),
            "detail": _N8N_BASE or "Non configuré",
        },
        {
            "id":     "anthropic",
            "name":   "Anthropic",
            "ok":     bool(_ANTHROPIC_KEY),
            "detail": "",
        },
    ]
    return JSONResponse({
        "runs":        runs[:20],
        "log_lines":   log_lines,
        "connectors":  connectors,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/kpis")
async def get_kpis():
    """KPIs financiers depuis Dolibarr : CA, impayés clients, impayés fournisseurs, devis ouverts."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "DOLIBARR_BASE_URL ou DOLIBARR_API_KEY non configuré"}, status_code=503)

    now = datetime.now(timezone.utc)
    debut_mois = int(datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp())
    debut_mois_prec = int(
        datetime(now.year if now.month > 1 else now.year - 1,
                 now.month - 1 if now.month > 1 else 12, 1,
                 tzinfo=timezone.utc).timestamp()
    )

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    # Requêtes parallèles (supplier_invoices avec fallback type=1 si 501)
    invoices_raw, proposals_raw, orders_raw = await asyncio.gather(
        doli_get("/invoices",  {"limit": 500, "type": 0, }),
        doli_get("/proposals", {"limit": 500,             }),
        doli_get("/orders",    {"limit": 500,             }),
    )
    try:
        async with httpx.AsyncClient() as _c:
            _r = await _c.get(f"{_DOLIBARR_BASE}/supplier_invoices",
                              params={"limit": 200, },
                              headers=_DOLI_HEADERS, timeout=15)
            if _r.status_code == 501:
                _r2 = await _c.get(f"{_DOLIBARR_BASE}/invoices",
                                   params={"limit": 200, "type": 1, },
                                   headers=_DOLI_HEADERS, timeout=15)
                supplier_raw = _r2.json() if _r2.status_code == 200 else []
            else:
                supplier_raw = _r.json() if _r.status_code == 200 else []
    except Exception:
        supplier_raw = []

    invoices      = invoices_raw  if isinstance(invoices_raw, list)  else []
    supplier_inv  = supplier_raw  if isinstance(supplier_raw, list)  else []
    proposals     = proposals_raw if isinstance(proposals_raw, list) else []
    orders        = orders_raw    if isinstance(orders_raw,    list) else []

    # ── Résolution noms clients via /thirdparties/{socid}
    # Étape 1 : construire la map en propageant d'abord les noms déjà présents
    # (factures retournent socnom, proposals non → on partage la map entre les deux)
    all_objs = invoices + supplier_inv + proposals + orders
    thirds_map: dict[str, str] = {}
    for obj in all_objs:
        sid = str(obj.get("socid") or "")
        if not sid or sid == "0":
            continue
        name = obj.get("socnom") or obj.get("thirdparty_name") or ""
        if name and not thirds_map.get(sid):
            thirds_map[sid] = name      # propager le nom depuis facture vers devis
        elif sid not in thirds_map:
            thirds_map[sid] = ""        # placeholder à résoudre

    # Étape 2 : résoudre les socids encore inconnus
    unresolved = [sid for sid, n in thirds_map.items() if not n]
    if unresolved:
        fetched = await asyncio.gather(*[doli_get(f"/thirdparties/{sid}") for sid in unresolved[:300]])
        for sid, data in zip(unresolved[:300], fetched):
            if isinstance(data, dict):
                thirds_map[sid] = data.get("name") or ""

    def _client(obj: dict) -> str:
        return (obj.get("socnom") or obj.get("thirdparty_name")
                or thirds_map.get(str(obj.get("socid") or "")) or "")

    # ── CA mois en cours (HT, factures validées ou payées)
    ca_mois = sum(
        float(f.get("total_ht") or 0)
        for f in invoices
        if int(f.get("date") or 0) >= debut_mois
        and int(f.get("statut") or 0) in (1, 2)
    )

    # ── CA mois précédent
    ca_mois_prec = sum(
        float(f.get("total_ht") or 0)
        for f in invoices
        if debut_mois_prec <= int(f.get("date") or 0) < debut_mois
        and int(f.get("statut") or 0) in (1, 2)
    )

    # ── Factures clients impayées (HT)
    impayes_clients = [
        {
            "ref":      f.get("ref"),
            "client":   _client(f),
            "montant":  round(float(f.get("total_ht") or 0), 2),
            "echeance": f.get("date_lim_reglement"),
            "retard":   max(0, int(now.timestamp()) - int(f.get("date_lim_reglement") or now.timestamp())) // 86400,
            **build_links(f, "facture", _DOLI_WEB),
        }
        for f in invoices
        if int(f.get("statut") or 0) == 1
    ]
    total_impaye_clients_ht = round(sum(f["montant"] for f in impayes_clients), 2)

    # ── Factures fournisseurs impayées (HT)
    impayes_four = [
        {
            "ref":      f.get("ref"),
            "fourni":   _client(f),
            "montant":  round(float(f.get("total_ht") or 0), 2),
            "echeance": f.get("date_lim_reglement"),
            **build_links(f, "facture_fournisseur", _DOLI_WEB),
        }
        for f in supplier_inv
        if int(f.get("statut") or 0) == 1
    ]
    total_impaye_four_ht = round(sum(f["montant"] for f in impayes_four), 2)

    # ── Devis ouverts (brouillon + validé)
    devis_ouverts = [
        {
            "ref":          p.get("ref"),
            "client":       _client(p),
            "project_name": (p.get("array_options") or {}).get("options_fhp_project_name") or "",
            "montant":      round(float(p.get("total_ht") or 0), 2),
            "statut":       int(p.get("statut") or 0),
            **build_links(p, "propal", _DOLI_WEB),
        }
        for p in proposals
        if int(p.get("statut") or 0) in (0, 1)
    ]
    total_devis = round(sum(d["montant"] for d in devis_ouverts), 2)

    # ── Taux de transformation (année en cours)
    debut_annee  = int(datetime(now.year, 1, 1, tzinfo=timezone.utc).timestamp())
    proposals_an = [p for p in proposals if int(p.get("date") or 0) >= debut_annee]
    nb_signes    = sum(1 for p in proposals_an if int(p.get("statut") or 0) == 2)
    nb_actifs    = sum(1 for p in proposals_an if int(p.get("statut") or 0) in (0, 1, 2, 3))
    taux_transfo = round(nb_signes / nb_actifs * 100, 1) if nb_actifs else None

    # ── Rentabilité du mois (CA HT - coût fournisseurs HT du mois)
    cout_four_mois_ht = sum(
        float(f.get("total_ht") or 0)
        for f in supplier_inv
        if int(f.get("date") or 0) >= debut_mois
        and int(f.get("statut") or 0) in (1, 2)
    )
    rentabilite_ht = round(ca_mois - cout_four_mois_ht, 2)

    # ── Commandes non facturées (statut validé/en cours/expédié, billed=0)
    cmds_non_facturees = [
        o for o in orders
        if int(o.get("statut") or 0) in (1, 2, 3, 4)
        and int(o.get("billed") or o.get("facturee") or 0) == 0
    ]
    cmds_non_fact_ht = round(sum(float(o.get("total_ht") or 0) for o in cmds_non_facturees), 2)

    return JSONResponse({
        "ca": {
            "mois_en_cours_ht":  round(ca_mois, 2),
            "mois_precedent_ht": round(ca_mois_prec, 2),
            "evolution_pct":     round((ca_mois - ca_mois_prec) / ca_mois_prec * 100, 1) if ca_mois_prec else None,
        },
        "taux_transfo": {
            "pct":      taux_transfo,
            "nb_signes": nb_signes,
            "nb_total":  nb_actifs,
        },
        "rentabilite": {
            "ht":           rentabilite_ht,
            "ca_ht":        round(ca_mois, 2),
            "cout_four_ht": round(cout_four_mois_ht, 2),
        },
        "impayes_clients": {
            "total_ht": total_impaye_clients_ht,
            "nb":       len(impayes_clients),
            "detail":   sorted(impayes_clients, key=lambda x: x["retard"], reverse=True)[:10],
        },
        "impayes_fournisseurs": {
            "total_ht": total_impaye_four_ht,
            "nb":       len(impayes_four),
            "detail":   impayes_four[:10],
        },
        "devis_ouverts": {
            "total_ttc": total_devis,
            "nb":        len(devis_ouverts),
            "detail":    devis_ouverts[:10],
        },
        "cmds_non_facturees": {
            "nb":       len(cmds_non_facturees),
            "total_ht": cmds_non_fact_ht,
        },
        "doli_web":    _DOLI_WEB,
        "generated_at": now.isoformat(),
    })


@app.get("/api/stats")
async def get_stats():
    """Stats opérationnelles : devis brouillon/semaine, commandes Dolibarr."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    now = datetime.now(timezone.utc)
    debut_semaine = int(
        (now - timedelta(days=now.weekday()))
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    proposals_raw, orders_raw = await asyncio.gather(
        doli_get("/proposals", {"limit": 500, }),
        doli_get("/orders",    {"limit": 500, }),
    )
    proposals = proposals_raw if isinstance(proposals_raw, list) else []
    orders    = orders_raw    if isinstance(orders_raw,    list) else []

    def p_date(obj):
        return int(obj.get("date") or obj.get("date_creation") or 0)

    def ht(obj):
        return float(obj.get("total_ht") or 0)

    def suppl(o):
        return str((o.get("array_options") or {}).get("options_statut_suppl") or "").lower().strip()

    # Devis semaine (tous statuts confondus, créés depuis lundi)
    dv_semaine  = [p for p in proposals if p_date(p) >= debut_semaine]
    # Devis brouillon
    dv_brouillon = [p for p in proposals if int(p.get("statut") or 0) == 0]
    # Commandes de la semaine (toutes)
    cmds_semaine  = [o for o in orders if p_date(o) >= debut_semaine]
    # Commandes bloquées / attente fichier (statut=0)
    cmds_bloque  = [o for o in orders if int(o.get("statut") or 0) == 0]
    # Fichiers en cours de traitement (statut=1, suppl vide)
    cmds_fichiers = [o for o in orders if int(o.get("statut") or 0) == 1 and not suppl(o)]
    # En cours de prod (statut=1, suppl contient "approu")
    cmds_en_prod  = [o for o in orders if int(o.get("statut") or 0) == 1 and "approu" in suppl(o)]
    # En attente de BAT (statut=1, suppl contient "trait")
    cmds_bat      = [o for o in orders if int(o.get("statut") or 0) == 1 and "trait" in suppl(o)]

    return JSONResponse({
        "devis_semaine":    {"nb": len(dv_semaine),   "total_ht": round(sum(ht(p) for p in dv_semaine),   2)},
        "devis_brouillon":  {"nb": len(dv_brouillon), "total_ht": round(sum(ht(p) for p in dv_brouillon), 2)},
        "cmds_semaine":     {"nb": len(cmds_semaine),  "total_ht": round(sum(ht(o) for o in cmds_semaine),  2)},
        "cmds_bloque":      {"nb": len(cmds_bloque),  "total_ht": round(sum(ht(o) for o in cmds_bloque),  2)},
        "cmds_fichiers":    {"nb": len(cmds_fichiers),"total_ht": round(sum(ht(o) for o in cmds_fichiers),2)},
        "cmds_en_prod":     {"nb": len(cmds_en_prod), "total_ht": round(sum(ht(o) for o in cmds_en_prod), 2)},
        "cmds_bat":         {"nb": len(cmds_bat),     "total_ht": round(sum(ht(o) for o in cmds_bat),     2)},
        "doli_web":         _DOLI_WEB,
        "generated_at":     now.isoformat(),
    })


@app.get("/api/daf")
async def get_daf():
    """Analyse DAF : DSO, encours tranches, top clients CA, prévisionnel 30j."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    from collections import defaultdict

    now = datetime.now(timezone.utc)
    debut_annee = int(datetime(now.year, 1, 1, tzinfo=timezone.utc).timestamp())
    now_ts = int(now.timestamp())

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    invoices_raw, orders_raw = await asyncio.gather(
        doli_get("/invoices", {"limit": 500, "type": 0, }),
        doli_get("/orders",   {"limit": 500,             }),
    )
    invoices = invoices_raw if isinstance(invoices_raw, list) else []
    orders   = orders_raw   if isinstance(orders_raw,   list) else []

    # Résolution noms clients (invoices parfois sans socnom sur Freshprocess)
    thirds_map: dict[str, str] = {}
    for obj in invoices:
        name = obj.get("socnom") or obj.get("thirdparty_name") or ""
        sid  = str(obj.get("socid") or "")
        if sid and not name and sid not in thirds_map:
            thirds_map[sid] = ""
        elif sid and name and not thirds_map.get(sid):
            thirds_map[sid] = name
    unresolved_daf = [sid for sid, n in thirds_map.items() if not n]
    if unresolved_daf:
        fetched_daf = await asyncio.gather(*[doli_get(f"/thirdparties/{sid}") for sid in unresolved_daf[:100]])
        for sid, data in zip(unresolved_daf[:100], fetched_daf):
            if isinstance(data, dict):
                thirds_map[sid] = data.get("name") or ""

    def _daf_client(obj):
        return (obj.get("socnom") or obj.get("thirdparty_name")
                or thirds_map.get(str(obj.get("socid") or "")) or f"#{obj.get('socid','?')}")

    # ── CA année en cours (factures validées + payées)
    ca_annee = sum(
        float(f.get("total_ht") or 0) for f in invoices
        if int(f.get("date") or 0) >= debut_annee and int(f.get("statut") or 0) in (1, 2)
    )

    # ── DSO (Days Sales Outstanding)
    impayes_total = sum(float(f.get("total_ht") or 0) for f in invoices if int(f.get("statut") or 0) == 1)
    ca_90j = sum(
        float(f.get("total_ht") or 0) for f in invoices
        if int(f.get("date") or 0) >= now_ts - 90 * 86400
        and int(f.get("statut") or 0) in (1, 2)
    )
    dso = round(impayes_total / (ca_90j / 90) if ca_90j > 0 else 0)

    # ── Encours clients par tranche de retard
    enc_courant = enc_30 = enc_60 = enc_90p = 0.0
    for f in invoices:
        if int(f.get("statut") or 0) != 1:
            continue
        echeance = int(f.get("date_lim_reglement") or 0)
        montant  = float(f.get("total_ht") or 0)
        if not echeance or echeance >= now_ts:
            enc_courant += montant
        else:
            retard = (now_ts - echeance) // 86400
            if retard <= 30:
                enc_30 += montant
            elif retard <= 60:
                enc_60 += montant
            else:
                enc_90p += montant

    # ── Top 5 clients CA année
    ca_by_client: dict[str, float] = defaultdict(float)
    for f in invoices:
        if int(f.get("date") or 0) >= debut_annee and int(f.get("statut") or 0) in (1, 2):
            name = _daf_client(f)
            ca_by_client[name] += float(f.get("total_ht") or 0)
    top_clients = sorted(ca_by_client.items(), key=lambda x: x[1], reverse=True)[:5]

    # ── Top 5 produits CA année (via lignes de factures)
    prod_ca: dict[str, dict] = {}
    for f in invoices:
        if int(f.get("date") or 0) >= debut_annee and int(f.get("statut") or 0) in (1, 2):
            for line in (f.get("lines") or []):
                ref   = str(line.get("product_ref") or line.get("ref") or "—")
                label = line.get("product_label") or line.get("label") or ref
                lht   = float(line.get("total_ht") or 0)
                if ref not in prod_ca:
                    prod_ca[ref] = {"label": label, "ca_ht": 0.0}
                prod_ca[ref]["ca_ht"] += lht
    top_produits = sorted(prod_ca.values(), key=lambda x: x["ca_ht"], reverse=True)[:5]

    # ── Commandes non facturées
    cmds_nf = [
        o for o in orders
        if int(o.get("statut") or 0) in (1, 2, 3, 4)
        and int(o.get("billed") or o.get("facturee") or 0) == 0
    ]
    cmds_nf_ht = round(sum(float(o.get("total_ht") or 0) for o in cmds_nf), 2)

    # ── Prévisionnel encaissements 30 prochains jours
    horizon = now_ts + 30 * 86400
    prev_30 = sum(
        float(f.get("total_ht") or 0) for f in invoices
        if int(f.get("statut") or 0) == 1
        and 0 < int(f.get("date_lim_reglement") or 0) <= horizon
    )

    return JSONResponse({
        "ca_annee_ht":  round(ca_annee, 2),
        "dso_jours":    dso,
        "encours": {
            "courant":       round(enc_courant, 2),
            "retard_30j":    round(enc_30, 2),
            "retard_60j":    round(enc_60, 2),
            "retard_90j_plus": round(enc_90p, 2),
        },
        "top_clients":  [{"nom": n, "ca_ht": round(v, 2)} for n, v in top_clients],
        "top_produits": [{"label": p["label"], "ca_ht": round(p["ca_ht"], 2)} for p in top_produits],
        "cmds_non_facturees": {"nb": len(cmds_nf), "total_ht": cmds_nf_ht},
        "previsionnel_30j": round(prev_30, 2),
        "doli_web":    _DOLI_WEB,
        "generated_at": now.isoformat(),
    })


@app.get("/api/ca-chart")
async def get_ca_chart():
    """CA mensuel HT sur 4 ans (N, N-1, N-2, N-3) pour le graphique."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    from collections import defaultdict

    now  = datetime.now(timezone.utc)
    year = now.year
    debut_4ans = int(datetime(year - 3, 1, 1, tzinfo=timezone.utc).timestamp())

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{_DOLIBARR_BASE}/invoices",
                params={"limit": 1000, "type": 0, },
                headers=_DOLI_HEADERS,
                timeout=20,
            )
            invoices = r.json() if r.status_code == 200 else []
    except Exception:
        invoices = []
    if not isinstance(invoices, list):
        invoices = []

    monthly: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for f in invoices:
        d = int(f.get("date") or 0)
        if d < debut_4ans:
            continue
        if int(f.get("statut") or 0) not in (1, 2):
            continue
        dt = datetime.fromtimestamp(d, tz=timezone.utc)
        monthly[dt.year][dt.month] += float(f.get("total_ht") or 0)

    years_data = {
        str(y): {str(m): round(monthly[y].get(m, 0), 2) for m in range(1, 13)}
        for y in [year, year - 1, year - 2, year - 3]
    }
    return JSONResponse({"years": years_data, "current_year": year, "generated_at": now.isoformat()})


@app.get("/api/devis-suivre")
async def get_devis_suivre():
    """Devis validés (statut=1) depuis >= 14 jours, triés du plus ancien."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    now = datetime.now(timezone.utc)
    cutoff = int((now - timedelta(days=14)).timestamp())
    now_ts = int(now.timestamp())

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    proposals_raw = await doli_get("/proposals", {"limit": 500, })
    proposals = proposals_raw if isinstance(proposals_raw, list) else []

    # Filtrer : validé (statut=1), soumis depuis >= 14 jours
    a_suivre = [
        p for p in proposals
        if int(p.get("statut") or 0) == 1
        and int(p.get("date") or p.get("date_creation") or 0) <= cutoff
    ]

    # Résolution noms clients
    thirds_map: dict[str, str] = {}
    for p in a_suivre:
        name = p.get("socnom") or p.get("thirdparty_name") or ""
        sid  = str(p.get("socid") or "")
        if sid and not name and sid not in thirds_map:
            thirds_map[sid] = ""

    unresolved = [sid for sid, n in thirds_map.items() if not n]
    if unresolved:
        fetched = await asyncio.gather(*[doli_get(f"/thirdparties/{sid}") for sid in unresolved[:50]])
        for sid, data in zip(unresolved[:50], fetched):
            if isinstance(data, dict):
                thirds_map[sid] = data.get("name") or ""

    def client_name(p):
        return (p.get("socnom") or p.get("thirdparty_name")
                or thirds_map.get(str(p.get("socid") or "")) or "")

    # Trier du plus ancien au plus récent
    a_suivre.sort(key=lambda p: int(p.get("date") or p.get("date_creation") or 0))

    result = [
        {
            "ref":          p.get("ref"),
            "client":       client_name(p),
            "project_name": (p.get("array_options") or {}).get("options_fhp_project_name") or "",
            "montant":      round(float(p.get("total_ht") or 0), 2),
            "date_ts":      int(p.get("date") or p.get("date_creation") or 0),
            "jours_ecoul":  (now_ts - int(p.get("date") or p.get("date_creation") or 0)) // 86400,
            **build_links(p, "propal", _DOLI_WEB),
        }
        for p in a_suivre
    ]

    return JSONResponse({
        "devis":        result,
        "nb":           len(result),
        "doli_web":     _DOLI_WEB,
        "generated_at": now.isoformat(),
    })


@app.get("/api/clients")
async def get_clients(limit: int = 20):
    """Liste des tiers clients Dolibarr avec agrégation devis + CA."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    thirds_raw, proposals_raw, invoices_raw = await asyncio.gather(
        doli_get("/thirdparties", {"limit": limit, "client": 1}),
        doli_get("/proposals",    {"limit": 200, }),
        doli_get("/invoices",     {"limit": 200, "type": 0, }),
    )

    thirds    = thirds_raw    if isinstance(thirds_raw, list)    else []
    proposals = proposals_raw if isinstance(proposals_raw, list) else []
    invoices  = invoices_raw  if isinstance(invoices_raw, list)  else []

    from collections import defaultdict
    devis_by_socid: dict[str, list] = defaultdict(list)
    ca_by_socid:    dict[str, float] = defaultdict(float)

    for p in proposals:
        devis_by_socid[str(p.get("socid", ""))].append(p)

    for f in invoices:
        if int(f.get("statut", 0)) in (1, 2):
            ca_by_socid[str(f.get("socid", ""))] += float(f.get("total_ht") or 0)

    clients = []
    for t in thirds:
        sid = str(t.get("id", ""))
        devis = devis_by_socid.get(sid, [])

        # Dernier devis : date la plus récente
        dernier = None
        max_epoch = 0
        for d in devis:
            ep = int(d.get("date") or 0)
            if ep > max_epoch:
                max_epoch = ep
                dernier = datetime.fromtimestamp(ep, tz=timezone.utc).strftime("%d/%m/%Y")

        clients.append({
            "id":          t.get("id"),
            "nom":         t.get("name") or "",
            "email":       t.get("email") or "",
            "nb_devis":    len(devis),
            "ca_total_ht": round(ca_by_socid.get(sid, 0.0), 2),
            "dernier_devis": dernier,
        })

    clients.sort(key=lambda x: x["nb_devis"], reverse=True)

    return JSONResponse({
        "clients": clients,
        "total":   len(clients),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/n8n/workflows")
async def get_n8n_workflows():
    """
    Retourne la liste des workflows n8n avec leur statut live si N8N_API_KEY est défini,
    sinon retourne le catalogue statique avec les IDs connus.
    """
    editor_base = _N8N_BASE.rstrip("/")

    # Enrichir le catalogue statique avec une URL d'édition directe
    def enrich(wf: dict, active: bool | None = None) -> dict:
        wid = wf["id"]
        return {
            "id":       wid,
            "name":     wf["name"],
            "role":     wf["role"],
            "active":   active,
            "has_id":   wid is not None,
            "url":      f"{editor_base}/workflow/{wid}" if wid else None,
        }

    if not _N8N_KEY:
        # Pas de clé → catalogue statique, statut inconnu
        return JSONResponse({
            "workflows":   [enrich(w) for w in _N8N_WORKFLOWS_STATIC],
            "source":      "static",
            "n8n_url":     editor_base,
        })

    # Clé disponible → appel live
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{_N8N_BASE.rstrip('/')}/api/v1/workflows",
                params={"limit": 50},
                headers={"X-N8N-API-KEY": _N8N_KEY},
                timeout=10,
            )
        if r.status_code != 200:
            raise ValueError(f"n8n HTTP {r.status_code}")

        live = {str(w["id"]): w for w in r.json().get("data", [])}

        # Fusionner catalogue statique avec données live
        merged = []
        for wf in _N8N_WORKFLOWS_STATIC:
            wid = wf["id"]
            live_data = live.get(str(wid)) if wid else None
            active = live_data["active"] if live_data else (None if not wid else False)
            item = enrich(wf, active)
            if live_data:
                item["updated_at"] = live_data.get("updatedAt", "")[:10]
            merged.append(item)

        # Workflows live non dans le catalogue statique
        static_ids = {w["id"] for w in _N8N_WORKFLOWS_STATIC if w["id"]}
        for wid, w in live.items():
            if wid not in static_ids:
                merged.append({
                    "id":      wid,
                    "name":    w.get("name", "Workflow inconnu"),
                    "role":    "other",
                    "active":  w.get("active"),
                    "has_id":  True,
                    "url":     f"{editor_base}/workflow/{wid}",
                    "updated_at": w.get("updatedAt", "")[:10],
                })

        return JSONResponse({
            "workflows": merged,
            "source":    "live",
            "n8n_url":   editor_base,
        })

    except Exception as e:
        # Fallback statique en cas d'erreur
        return JSONResponse({
            "workflows": [enrich(w) for w in _N8N_WORKFLOWS_STATIC],
            "source":    "static_fallback",
            "n8n_url":   editor_base,
            "error":     str(e),
        })


@app.get("/api/proposals-orders")
async def get_proposals_orders():
    """Retourne les devis ouverts + commandes en cours pour le sélecteur d'upload assets."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=15,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    proposals_raw, orders_raw = await asyncio.gather(
        doli_get("/proposals", {"limit": 100, }),
        doli_get("/orders",    {"limit": 100, }),
    )

    proposals = proposals_raw if isinstance(proposals_raw, list) else []
    orders    = orders_raw    if isinstance(orders_raw,    list) else []

    # Résolution noms clients via socid
    all_items = proposals + orders
    thirds_map: dict[str, str] = {}
    for obj in all_items:
        name = obj.get("socnom") or obj.get("thirdparty_name") or ""
        sid = str(obj.get("socid") or "")
        if sid and not name and sid not in thirds_map:
            thirds_map[sid] = ""

    unresolved = [sid for sid, n in thirds_map.items() if not n]
    if unresolved:
        fetched = await asyncio.gather(*[
            doli_get(f"/thirdparties/{sid}") for sid in unresolved[:50]
        ])
        for sid, data in zip(unresolved[:50], fetched):
            if isinstance(data, dict):
                thirds_map[sid] = data.get("name") or ""

    def client_name(obj):
        return (obj.get("socnom") or obj.get("thirdparty_name")
                or thirds_map.get(str(obj.get("socid") or "")) or "")

    devis = [
        {
            "module":  "propal",
            "id":      p.get("id"),
            "ref":     p.get("ref"),
            "client":  client_name(p),
            "projet":  (p.get("array_options") or {}).get("options_fhp_project_name") or "",
            "statut":  int(p.get("statut") or 0),
        }
        for p in proposals
        if int(p.get("statut") or 0) in (0, 1)
    ]

    commandes = [
        {
            "module":  "commande",
            "id":      o.get("id"),
            "ref":     o.get("ref"),
            "client":  client_name(o),
            "projet":  (o.get("array_options") or {}).get("options_fhp_project_name") or "",
            "statut":  int(o.get("statut") or 0),
        }
        for o in orders
        if int(o.get("statut") or 0) in (1, 2)
    ]

    return JSONResponse({
        "devis":     devis,
        "commandes": commandes,
    })


_ASSET_TYPES = {"charte", "inspiration"}
_MODULE_PARTS = {"propal": "propal", "commande": "commande"}
_MAX_UPLOAD_MB = 20


@app.post("/api/upload-asset")
async def upload_asset(
    file:       UploadFile = File(...),
    asset_type: str        = Form(...),   # "charte" | "inspiration"
    module:     str        = Form(...),   # "propal" | "commande"
    doc_id:     int        = Form(...),   # ID Dolibarr du devis / commande
):
    """Dépose une PJ (charte graphique ou inspiration) sur un devis/commande Dolibarr."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        raise HTTPException(status_code=503, detail="Dolibarr non configuré")

    if asset_type not in _ASSET_TYPES:
        raise HTTPException(status_code=422, detail=f"asset_type doit être : {_ASSET_TYPES}")

    modulepart = _MODULE_PARTS.get(module)
    if not modulepart:
        raise HTTPException(status_code=422, detail=f"module doit être : {set(_MODULE_PARTS)}")

    # Lire le fichier et vérifier la taille
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > _MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"Fichier trop lourd ({size_mb:.1f} Mo > {_MAX_UPLOAD_MB} Mo)")

    # Récupérer la référence Dolibarr depuis l'ID
    path = "proposals" if module == "propal" else "orders"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{_DOLIBARR_BASE}/{path}/{doc_id}",
                headers=_DOLI_HEADERS,
                timeout=15,
            )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Dolibarr GET {path}/{doc_id} → {r.status_code}")
        ref = r.json().get("ref")
        if not ref:
            raise HTTPException(status_code=502, detail="Référence Dolibarr introuvable dans la réponse")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur Dolibarr : {e}")

    # Construire le nom de fichier préfixé
    original_name = (file.filename or "file").replace(" ", "_")
    prefixed_name = f"{asset_type}__{original_name}"

    # Uploader dans Dolibarr
    b64 = base64.b64encode(content).decode("ascii")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_DOLIBARR_BASE}/documents/upload",
                headers=_DOLI_HEADERS,
                json={
                    "filename":          prefixed_name,
                    "modulepart":        modulepart,
                    "ref":               ref,
                    "filecontent":       b64,
                    "fileencoding":      "base64",
                    "overwriteifexists": 1,
                },
                timeout=60,
            )
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Dolibarr upload → {r.status_code} : {r.text[:200]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur upload Dolibarr : {e}")

    return JSONResponse({
        "status":     "ok",
        "filename":   prefixed_name,
        "module":     module,
        "ref":        ref,
        "asset_type": asset_type,
        "size_kb":    round(len(content) / 1024, 1),
    })


@app.get("/api/config")
async def get_config():
    """Expose les URLs publiques utiles (sans clés)."""
    base = _DOLIBARR_BASE.removesuffix("/api/index.php").removesuffix("/api")
    return JSONResponse({
        "dolibarr_url": base or None,
        "n8n_url":      _N8N_BASE or None,
        "n8n_configured": bool(_N8N_KEY),
    })


@app.post("/api/run")
async def trigger_run():
    """Lance le pipeline main.py en subprocess non-bloquant."""
    python = sys.executable
    main_py = str(ROOT / "main.py")

    try:
        proc = subprocess.Popen(
            [python, main_py],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return JSONResponse({
            "status": "launched",
            "pid": proc.pid,
            "message": f"Pipeline lancé (PID {proc.pid}) — vérifiez le log dans quelques secondes",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Moteur IA Claude ────────────────────────────────────────────────────────

async def _fetch_dolibarr_context() -> str:
    """Charge un snapshot Dolibarr compact à injecter dans le contexte Claude."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return ""

    async def doli_get(path: str, params: dict = None):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}{path}",
                    params=params or {},
                    headers=_DOLI_HEADERS,
                    timeout=10,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    proposals_raw, invoices_raw, orders_raw, ships_raw = await asyncio.gather(
        doli_get("/proposals", {"limit": 100, }),
        doli_get("/invoices",  {"limit": 100, "type": 0, }),
        doli_get("/orders",    {"limit": 50,  }),
        doli_get("/shipments", {"limit": 30}),
    )

    # Résolution des noms : collecter les socids uniques non résolus dans les objets
    all_items = (
        (proposals_raw if isinstance(proposals_raw, list) else [])
        + (invoices_raw  if isinstance(invoices_raw,  list) else [])
        + (orders_raw    if isinstance(orders_raw,    list) else [])
        + (ships_raw     if isinstance(ships_raw,     list) else [])
    )
    thirds_map: dict[str, str] = {}
    for obj in all_items:
        name = obj.get("socnom") or obj.get("thirdparty_name") or obj.get("name") or ""
        sid = str(obj.get("socid") or "")
        if sid and not name and sid not in thirds_map:
            thirds_map[sid] = ""  # placeholder

    unresolved = [sid for sid, n in thirds_map.items() if not n]
    if unresolved:
        fetched = await asyncio.gather(*[
            doli_get(f"/thirdparties/{sid}") for sid in unresolved[:50]
        ])
        for sid, data in zip(unresolved[:50], fetched):
            if isinstance(data, dict):
                thirds_map[sid] = data.get("name") or ""

    now_ts = int(datetime.now(timezone.utc).timestamp())

    def fmt_date(ts):
        if not ts:
            return "—"
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d/%m/%Y")
        except Exception:
            return "—"

    STATUT_DEVIS  = {0: "Brouillon", 1: "Validé", 2: "Signé", 3: "Refusé", 4: "Expiré"}
    STATUT_FAC    = {0: "Brouillon", 1: "Non payée", 2: "Payée", 3: "Abandonnée"}
    STATUT_CMD    = {-1: "Annulée", 0: "Brouillon", 1: "Validée", 2: "En cours", 3: "Expédiée", 4: "Livrée"}
    STATUT_BL     = {0: "Brouillon", 1: "Validé", 2: "Livré"}

    def rows(items, fields_fn):
        return [fields_fn(x) for x in (items if isinstance(items, list) else [])]

    def client_name(obj):
        return (obj.get("socnom") or obj.get("thirdparty_name") or obj.get("name")
                or thirds_map.get(str(obj.get("socid") or "")) or "")

    devis_rows = rows(proposals_raw, lambda p: {
        "ref":    p.get("ref"),
        "client": client_name(p),
        "projet": (p.get("array_options") or {}).get("options_fhp_project_name") or "",
        "date":   fmt_date(p.get("date")),
        "ht":     round(float(p.get("total_ht") or 0), 2),
        "statut": STATUT_DEVIS.get(int(p.get("statut") or 0), str(p.get("statut"))),
    })

    fac_rows = rows(invoices_raw, lambda f: {
        "ref":     f.get("ref"),
        "client":  client_name(f),
        "date":    fmt_date(f.get("date")),
        "ttc":     round(float(f.get("total_ttc") or 0), 2),
        "statut":  STATUT_FAC.get(int(f.get("statut") or 0), str(f.get("statut"))),
        "retard_j": max(0, now_ts - int(f.get("date_lim_reglement") or now_ts)) // 86400
                    if int(f.get("statut") or 0) == 1 else 0,
    })

    cmd_rows = rows(orders_raw, lambda o: {
        "ref":    o.get("ref"),
        "client": client_name(o),
        "date":   fmt_date(o.get("date")),
        "ht":     round(float(o.get("total_ht") or 0), 2),
        "statut": STATUT_CMD.get(int(o.get("statut") or 0), str(o.get("statut"))),
    })

    bl_rows = rows(ships_raw, lambda s: {
        "ref":    s.get("ref"),
        "client": client_name(s),
        "date":   fmt_date(s.get("date_creation")),
        "statut": STATUT_BL.get(int(s.get("statut") or 0), str(s.get("statut"))),
    })

    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    return f"""
--- DONNÉES DOLIBARR EN TEMPS RÉEL (snapshot {now_str}) ---

DEVIS ({len(devis_rows)}) :
{json.dumps(devis_rows, ensure_ascii=False)}

FACTURES CLIENTS ({len(fac_rows)}) :
{json.dumps(fac_rows, ensure_ascii=False)}

COMMANDES ({len(cmd_rows)}) :
{json.dumps(cmd_rows, ensure_ascii=False)}

BONS DE LIVRAISON ({len(bl_rows)}) :
{json.dumps(bl_rows, ensure_ascii=False)}

--- FIN DONNÉES DOLIBARR ---
"""


# ── Tools Dolibarr exposés au chat IA ──────────────────────────────────────

_DOLIBARR_TOOLS = [
    {
        "name": "search_proposals",
        "description": "Recherche des devis Dolibarr. Retourne ref, client, statut, total HT, date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "statut": {"type": "integer",
                           "description": "Filtre statut : 0=brouillon, 1=validé, 2=signé, 3=refusé. Omis = tous."},
                "limit": {"type": "integer", "description": "Nombre max de résultats (défaut 20, max 100)"},
            },
        },
    },
    {
        "name": "get_proposal",
        "description": "Récupère un devis complet (lignes, notes, conditions) par sa référence ou son ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Référence du devis (ex: PRO2025-0042)"},
                "id":  {"type": "integer", "description": "ID numérique du devis"},
            },
        },
    },
    {
        "name": "search_thirdparties",
        "description": "Recherche des clients/tiers Dolibarr par nom ou email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":  {"type": "string", "description": "Nom de la société (recherche partielle)"},
                "email": {"type": "string", "description": "Email du contact"},
                "limit": {"type": "integer", "description": "Nombre max (défaut 20)"},
            },
        },
    },
    {
        "name": "get_thirdparty",
        "description": "Récupère la fiche complète d'un client par son ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "ID du tiers dans Dolibarr"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "search_invoices",
        "description": "Recherche des factures clients. Utile pour vérifier les impayés ou l'historique.",
        "input_schema": {
            "type": "object",
            "properties": {
                "statut": {"type": "integer",
                           "description": "Statut : 1=non payée, 2=payée, 3=abandonnée. Omis = toutes."},
                "limit": {"type": "integer", "description": "Nombre max (défaut 20)"},
            },
        },
    },
    {
        "name": "search_orders",
        "description": "Recherche des commandes clients.",
        "input_schema": {
            "type": "object",
            "properties": {
                "statut": {"type": "integer",
                           "description": "Statut : 0=brouillon, 1=validée, 2=en cours, 3=expédiée. Omis = toutes."},
                "limit": {"type": "integer", "description": "Nombre max (défaut 20)"},
            },
        },
    },
    {
        "name": "update_proposal",
        "description": (
            "Modifie les champs d'en-tête d'un devis. Champs disponibles :\n"
            "- note_public : texte visible sur le PDF client\n"
            "- note_private : note interne équipe\n"
            "- ref_client : référence client\n"
            "- project_name : nom du projet (champ custom options_fhp_project_name)\n"
            "- date_livraison : date de livraison souhaitée (format YYYY-MM-DD)\n"
            "- cond_reglement_id : ID condition de règlement (15=BAT, autres à vérifier)\n"
            "- mode_reglement_id : ID mode de règlement (2=virement bancaire)\n"
            "Passer uniquement les champs à modifier, les autres restent inchangés."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id":      {"type": "integer", "description": "ID du devis"},
                "note_public":      {"type": "string",  "description": "Note visible sur le PDF client"},
                "note_private":     {"type": "string",  "description": "Note interne équipe"},
                "ref_client":       {"type": "string",  "description": "Référence client"},
                "project_name":     {"type": "string",  "description": "Nom du projet"},
                "date_livraison":   {"type": "string",  "description": "Date livraison YYYY-MM-DD"},
                "cond_reglement_id":{"type": "integer", "description": "ID condition de règlement"},
                "mode_reglement_id":{"type": "integer", "description": "ID mode de règlement"},
            },
            "required": ["proposal_id"],
        },
    },
    {
        "name": "update_proposal_line",
        "description": (
            "Modifie une ligne d'un devis. Utiliser get_proposal d'abord pour récupérer les IDs de lignes.\n"
            "Champs disponibles :\n"
            "- desc : description HTML de la ligne (contexte client, descriptif technique, ou intitulé prix)\n"
            "- qty : quantité\n"
            "- subprice : prix unitaire HT\n"
            "- remise_percent : remise en %\n"
            "- tva_tx : taux TVA (défaut 20)\n"
            "Passer uniquement les champs à modifier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "integer", "description": "ID du devis"},
                "line_id":     {"type": "integer", "description": "ID de la ligne (issu de get_proposal → lines[].id)"},
                "desc":        {"type": "string",  "description": "Description HTML de la ligne"},
                "qty":         {"type": "number",  "description": "Quantité"},
                "subprice":    {"type": "number",  "description": "Prix unitaire HT"},
                "remise_percent": {"type": "number", "description": "Remise en %"},
                "tva_tx":      {"type": "number",  "description": "Taux TVA (défaut 20)"},
            },
            "required": ["proposal_id", "line_id"],
        },
    },
    {
        "name": "validate_proposal",
        "description": "Valide un devis (passe de brouillon à validé, génère la référence définitive). "
                       "Action irréversible sans intervention manuelle — confirme toujours avec l'utilisateur avant.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "integer", "description": "ID du devis à valider"},
            },
            "required": ["proposal_id"],
        },
    },
    {
        "name": "set_proposal_to_draft",
        "description": "Remet un devis validé en brouillon pour modification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "integer", "description": "ID du devis"},
            },
            "required": ["proposal_id"],
        },
    },
]


async def _execute_dolibarr_tool(name: str, inputs: dict) -> str:
    """Exécute un tool Dolibarr et retourne le résultat sérialisé en JSON."""

    async def doli_get(path: str, params: dict | None = None):
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{_DOLIBARR_BASE}{path}",
                params=params or {},
                headers=_DOLI_HEADERS,
            )
            r.raise_for_status()
            return r.json()

    async def doli_patch(path: str, body: dict):
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.put(
                f"{_DOLIBARR_BASE}{path}",
                json=body,
                headers={**_DOLI_HEADERS, "Content-Type": "application/json"},
            )
            r.raise_for_status()
            return r.json()

    async def doli_post(path: str, body: dict):
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{_DOLIBARR_BASE}{path}",
                json=body,
                headers={**_DOLI_HEADERS, "Content-Type": "application/json"},
            )
            r.raise_for_status()
            return r.json()

    try:
        if name == "search_proposals":
            # sortfield non supporté sur cette instance Freshprocess — tri côté Python
            params = {"limit": inputs.get("limit", 20)}
            if "statut" in inputs:
                params["status"] = inputs["statut"]
            data = await doli_get("/proposals", params)
            if isinstance(data, list):
                data.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
            return json.dumps(data if isinstance(data, list) else [], ensure_ascii=False)

        if name == "get_proposal":
            if "ref" in inputs:
                data = await doli_get(f"/proposals/ref/{inputs['ref']}")
            else:
                data = await doli_get(f"/proposals/{inputs['id']}")
            return json.dumps(data, ensure_ascii=False)

        if name == "search_thirdparties":
            params = {"limit": inputs.get("limit", 20)}
            if "name" in inputs:
                safe = re.sub(r"['\";`]", "", inputs["name"])[:80]
                params["sqlfilters"] = f"(t.nom:like:'%{safe}%')"
            data = await doli_get("/thirdparties", params)
            if isinstance(data, list):
                data.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
            return json.dumps(data if isinstance(data, list) else [], ensure_ascii=False)

        if name == "get_thirdparty":
            data = await doli_get(f"/thirdparties/{inputs['id']}")
            return json.dumps(data, ensure_ascii=False)

        if name == "search_invoices":
            params = {"limit": inputs.get("limit", 20)}
            if "statut" in inputs:
                params["status"] = inputs["statut"]
            data = await doli_get("/invoices", params)
            if isinstance(data, list):
                data.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
            return json.dumps(data if isinstance(data, list) else [], ensure_ascii=False)

        if name == "search_orders":
            params = {"limit": inputs.get("limit", 20)}
            if "statut" in inputs:
                params["status"] = inputs["statut"]
            data = await doli_get("/orders", params)
            if isinstance(data, list):
                data.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
            return json.dumps(data if isinstance(data, list) else [], ensure_ascii=False)

        if name == "update_proposal":
            pid = inputs.pop("proposal_id")
            payload: dict = {}
            if "note_public"       in inputs: payload["note_public"]       = inputs["note_public"]
            if "note_private"      in inputs: payload["note_private"]      = inputs["note_private"]
            if "ref_client"        in inputs: payload["ref_client"]        = inputs["ref_client"]
            if "cond_reglement_id" in inputs: payload["cond_reglement_id"] = inputs["cond_reglement_id"]
            if "mode_reglement_id" in inputs: payload["mode_reglement_id"] = inputs["mode_reglement_id"]
            if "project_name"      in inputs:
                payload.setdefault("array_options", {})
                payload["array_options"]["options_fhp_project_name"] = inputs["project_name"]
            if "date_livraison"    in inputs:
                from datetime import datetime as _dt
                try:
                    payload["date_livraison"] = int(_dt.fromisoformat(inputs["date_livraison"]).timestamp())
                except ValueError:
                    return json.dumps({"error": f"date_livraison invalide : {inputs['date_livraison']!r}"})
            data = await doli_patch(f"/proposals/{pid}", payload)
            return json.dumps({"ok": True, "updated_fields": list(payload.keys()), "result": data},
                              ensure_ascii=False)

        if name == "update_proposal_line":
            pid  = inputs.pop("proposal_id")
            lid  = inputs.pop("line_id")
            payload = {k: v for k, v in inputs.items()
                       if k in ("desc", "qty", "subprice", "remise_percent", "tva_tx")}
            data = await doli_patch(f"/proposals/{pid}/lines/{lid}", payload)
            return json.dumps({"ok": True, "updated_fields": list(payload.keys()), "result": data},
                              ensure_ascii=False)

        if name == "validate_proposal":
            data = await doli_post(f"/proposals/{inputs['proposal_id']}/validate", {"notrigger": 0})
            return json.dumps({"ok": True, "ref": data if isinstance(data, str) else data}, ensure_ascii=False)

        if name == "set_proposal_to_draft":
            data = await doli_post(f"/proposals/{inputs['proposal_id']}/settodraft", {"notrigger": 0})
            return json.dumps({"ok": True, "result": data}, ensure_ascii=False)

        return json.dumps({"error": f"Tool inconnu : {name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


@app.post("/api/chat")
async def chat(request: Request):
    """Chat IA avec boucle agentique Dolibarr. Body: {messages: [{role, content}]}"""
    if not _ANTHROPIC_KEY:
        return JSONResponse(
            {"error": "ANTHROPIC_API_KEY manquante — ajoutez-la dans .env"},
            status_code=503,
        )

    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return JSONResponse(
            {"error": "Package anthropic manquant — pip install anthropic"},
            status_code=503,
        )

    body = await request.json()
    messages = body.get("messages", [])
    if not messages:
        return JSONResponse({"error": "messages vides"}, status_code=400)

    doli_ctx = await _fetch_dolibarr_context()
    system = _CHAT_SYSTEM + doli_ctx

    async def generate():
        client = AsyncAnthropic(api_key=_ANTHROPIC_KEY)
        current_messages = list(messages)
        max_iterations = 6  # garde-fou boucle infinie

        try:
            for _ in range(max_iterations):
                response = await client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2048,
                    system=system,
                    messages=current_messages,
                    tools=_DOLIBARR_TOOLS,
                )

                if response.stop_reason == "tool_use":
                    # Notifier le frontend des appels outils en cours
                    tool_results = []
                    assistant_content = [b.model_dump() for b in response.content]

                    for block in response.content:
                        if block.type == "tool_use":
                            yield f"data: {json.dumps({'tool_call': {'name': block.name, 'input': block.input}})}\n\n"
                            result_str = await _execute_dolibarr_tool(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            })

                    current_messages.append({"role": "assistant", "content": assistant_content})
                    current_messages.append({"role": "user", "content": tool_results})

                else:
                    # Réponse finale — streamer le texte
                    for block in response.content:
                        if hasattr(block, "text") and block.text:
                            yield f"data: {json.dumps({'text': block.text})}\n\n"
                    break

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no",
                                      "Cache-Control": "no-cache"})


# ── GO — Déclenchement manuel envoi email client ───────────────────────────

@app.get("/api/go/{devis_id}")
async def go_send_client_email(devis_id: int):
    """
    Endpoint déclenché par le bouton GO dans l'email interne.
    Charge le contexte sauvegardé, valide le devis dans Dolibarr, envoie l'email client.
    """
    import dataclasses
    from pathlib import Path as _Path
    from src.middleware.context import Context
    from src.steps.flux_a.steps import s13_send_email_client
    from src.connectors.dolibarr import DolibarrClient

    pending_path = ROOT / "runs" / "pending" / f"{devis_id}.json"
    done_dir = ROOT / "runs" / "done"

    if not pending_path.exists():
        # Vérifier si déjà traité
        done_path = done_dir / f"{devis_id}.json"
        if done_path.exists():
            return _html_go_response(
                "Déjà envoyé",
                f"L'email client pour le devis #{devis_id} a déjà été envoyé.",
                success=True,
            )
        raise HTTPException(status_code=404, detail=f"Aucun GO en attente pour devis {devis_id}")

    # ── Charger le contexte ──────────────────────────────────────────────
    ctx_data = json.loads(pending_path.read_text())
    ctx = Context(**ctx_data)

    # ── Vérifier que le devis est validé dans Dolibarr ──────────────────
    try:
        doli = DolibarrClient()
        proposal = await doli.get_proposal_by_ref(ctx.devis_ref)
        statut = int(proposal.get("statut", 0))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Impossible de vérifier le statut Dolibarr : {e}")

    if statut < 1:
        doli_web = _DOLI_WEB
        validate_link = f"{doli_web}/comm/propal/card.php?id={ctx.devis_id}&action=valid"
        return _html_go_response(
            "Devis encore en brouillon",
            f"Le devis {ctx.devis_ref} est encore en brouillon dans Dolibarr.<br>"
            f"<a href='{validate_link}' style='color:#f59e0b'>Cliquez ici pour le valider dans Dolibarr</a>, "
            f"puis revenez cliquer GO.",
            success=False,
        )

    # ── Envoyer l'email client (s13) ─────────────────────────────────────
    try:
        await s13_send_email_client(ctx)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec envoi email client : {e}")

    # ── Archiver le contexte dans runs/done/ ─────────────────────────────
    done_dir.mkdir(parents=True, exist_ok=True)
    import dataclasses as _dc
    (done_dir / f"{devis_id}.json").write_text(
        json.dumps(_dc.asdict(ctx), ensure_ascii=False, indent=2)
    )
    pending_path.unlink(missing_ok=True)

    status_txt = ctx.output_response.get("status", "unknown")
    return _html_go_response(
        "Email envoyé ✓",
        f"L'email CONFIG_CLIENT_v2026 a été envoyé à <b>{ctx.email_sender_address}</b> "
        f"pour le devis <b>{ctx.devis_ref}</b>.<br>Statut : {status_txt}",
        success=(status_txt == "sent"),
    )


def _html_go_response(title: str, message: str, success: bool) -> "HTMLResponse":
    from fastapi.responses import HTMLResponse
    color = "#059669" if success else "#dc2626"
    icon = "✅" if success else "⚠️"
    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — InPressco</title>
<style>body{{font-family:Arial,sans-serif;background:#1a1a2e;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}}
.card{{background:#fff;border-radius:12px;padding:40px 48px;max-width:480px;
text-align:center;box-shadow:0 4px 32px rgba(0,0,0,.4)}}
h2{{color:{color};margin:0 0 16px}}p{{color:#374151;line-height:1.6}}
a{{color:#1d4ed8}}.back{{margin-top:24px}}
.back a{{background:#f59e0b;color:#1a1a2e;padding:10px 24px;border-radius:6px;
text-decoration:none;font-weight:bold}}</style>
</head><body>
<div class="card">
  <div style="font-size:48px">{icon}</div>
  <h2>{title}</h2>
  <p>{message}</p>
  <div class="back"><a href="/">Retour au dashboard</a></div>
</div>
</body></html>"""
    return HTMLResponse(content=html)


# ── Entrypoint direct ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8080, reload=True)
