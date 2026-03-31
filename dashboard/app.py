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
import shutil
import subprocess
import sys

from src.utils.dolibarr_urls import build_links
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
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
_CLAUDE_BIN     = shutil.which("claude") or "/Users/nicolasbompois/.local/bin/claude"

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


@app.get("/devis")
async def devis_page():
    html_file = Path(__file__).parent / "devis.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="devis.html not found")
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


def _parse_log_runs_rich(lines: list[str]) -> list[dict]:
    """Parse le log et retourne des blocs enrichis (email, routing, steps, actions)."""
    from datetime import datetime as _dt

    runs: list[dict] = []
    current: dict | None = None

    for line in lines:
        ts_m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        ts = ts_m.group(1) if ts_m else None

        # ── Début de run ──────────────────────────────────────────────────────
        if "InPressco Pipeline — démarrage" in line:
            current = {
                "started_at": ts,
                "finished_at": None,
                "duration_s": None,
                "email_subject": None,
                "email_sender": None,
                "routing_category": None,
                "routing_confidence": None,
                "soc_nom": None,
                "client_email": None,
                "devis_ref": None,
                "stop_reason": None,
                "steps": {
                    "s01": None, "s02": None,
                    "routing": None, "tiers": None, "devis": None,
                },
                "actions": [],
                "status": "running",
            }
            continue

        if current is None:
            continue

        msg = re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s+\w+\s+[\w\.\-]+\s+—\s+", "", line)

        # ── Step markers ──────────────────────────────────────────────────────
        for step_key in ("s01_get_email", "s02_extract_client_ai"):
            short = step_key.split("_")[0]
            if f"→ {step_key}" in line:
                current["steps"][short] = "active"
            elif f"✓ {step_key}" in line:
                current["steps"][short] = "done"

        # s03+ → tiers
        for sname in ("s03_", "s04_", "s05_"):
            if f"✓ {sname}" in line and current["steps"].get("tiers") != "done":
                current["steps"]["tiers"] = "done"
            elif f"→ {sname}" in line and current["steps"].get("tiers") is None:
                current["steps"]["tiers"] = "active"

        # s08+→ devis
        for sname in ("s08_", "s09_", "s10_", "s11_"):
            if f"✓ {sname}" in line and current["steps"].get("devis") != "done":
                current["steps"]["devis"] = "done"
            elif f"→ {sname}" in line and current["steps"].get("devis") is None:
                current["steps"]["devis"] = "active"

        # ── Extraction email ──────────────────────────────────────────────────
        m = re.search(r"Email récupéré : '(.+)' de (.+)$", line)
        if m:
            current["email_subject"] = m.group(1)[:80]
            current["email_sender"] = m.group(2).strip()
            current["actions"].append({"icon": "📧", "text": f"de {m.group(2).strip()}"})

        # ── Extraction client ─────────────────────────────────────────────────
        m = re.search(r"Client extrait : soc_nom=(.+?), email='(.+)'", line)
        if m:
            raw_nom = m.group(1).strip("'")
            current["soc_nom"] = None if raw_nom == "None" else raw_nom
            current["client_email"] = m.group(2)

        # ── Sentiment ────────────────────────────────────────────────────────
        m = re.search(r"Sentiment : urgence='(.+)', profil='(.+)'", line)
        if m:
            current["actions"].append({"icon": "💭", "text": f"{m.group(2)}, urgence {m.group(1)}"})

        # ── Routing ───────────────────────────────────────────────────────────
        m = re.search(r"Routing : categorie='(.+)', confidence='(.+)'", line)
        if m:
            current["routing_category"] = m.group(1)
            current["routing_confidence"] = m.group(2)
            current["steps"]["routing"] = "done"
            current["actions"].append({"icon": "🔀", "text": m.group(1)})

        # ── Marquage Outlook ──────────────────────────────────────────────────
        m = re.search(r"Email marqué '(\[.+?\])", line)
        if m:
            current["actions"].append({"icon": "✓", "text": f"Outlook : {m.group(1)}"})

        # ── Tiers trouvé / créé ───────────────────────────────────────────────
        if "Tiers trouvé" in line or "Tiers créé" in line:
            m2 = re.search(r"(Tiers (?:trouvé|créé)[^—\n]*)", line)
            current["steps"]["tiers"] = "done"
            current["actions"].append({"icon": "👤", "text": m2.group(1)[:60] if m2 else "Tiers Dolibarr"})

        # ── Devis créé ────────────────────────────────────────────────────────
        m = re.search(r"devis créé : (\S+)", line)
        if m:
            current["devis_ref"] = m.group(1)
            current["steps"]["devis"] = "done"
            current["actions"].append({"icon": "📄", "text": f"Devis {m.group(1)}"})
            current["status"] = "devis_created"

        # ── Errors ───────────────────────────────────────────────────────────
        if "  ERROR  " in line or "  ERROR      " in line:
            current["status"] = "error"
            current["actions"].append({"icon": "🔴", "text": msg[:70]})

        # ── StopPipeline / pas d'email ────────────────────────────────────────
        if "StopPipeline" in line:
            m2 = re.search(r"StopPipeline[:\(\"\']+\s*(.+?)[\)\"\']*$", line)
            current["stop_reason"] = m2.group(1)[:80] if m2 else "Stop"
        if "Pas d'email non traité" in line or "Aucun email" in line:
            current["stop_reason"] = "Pas d'email à traiter"
            current["actions"].append({"icon": "💤", "text": "Pas d'email à traiter"})

        # ── Fin de run ────────────────────────────────────────────────────────
        if "Pipeline terminé" in line and ts:
            current["finished_at"] = ts
            if current["started_at"]:
                try:
                    t0 = _dt.strptime(current["started_at"], "%Y-%m-%d %H:%M:%S")
                    t1 = _dt.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    current["duration_s"] = int((t1 - t0).total_seconds())
                except Exception:
                    pass
            if current["status"] == "running":
                if current.get("stop_reason"):
                    current["status"] = "stopped"
                elif current.get("routing_category") and current["routing_category"] != "NEW_PROJECT":
                    current["status"] = "routed"
                elif current.get("devis_ref"):
                    current["status"] = "devis_created"
                else:
                    current["status"] = "ok"
            runs.append(current)
            current = None

    if current is not None:
        runs.append(current)

    return list(reversed(runs))


@app.get("/api/pipeline-runs")
async def get_pipeline_runs(limit: int = 20):
    """Historique des runs enrichi : email, routing, steps, actions."""
    log_lines = _read_log_lines(3000)
    runs = _parse_log_runs_rich(log_lines)
    return JSONResponse({"runs": runs[:limit], "total": len(runs)})


@app.post("/api/pipeline/archive-email")
async def pipeline_archive_email(request: Request):
    """Marque un email comme [Traité] dans Outlook (depuis le dashboard).
    Body JSON : { subject, sender }
    """
    data = await request.json()
    subject: str = data.get("subject", "")
    sender: str  = data.get("sender", "")
    if not subject or not sender:
        raise HTTPException(400, "subject et sender requis")

    try:
        from src.connectors.outlook import OutlookClient
        from src import config
        import re as _re

        outlook = OutlookClient()
        # Recherche par expéditeur (plus fiable que OData sur le sujet avec accents)
        emails = await outlook.get_emails(
            folder_id=config.OUTLOOK_FOLDER_DEVIS,
            odata_filter=f"from/emailAddress/address eq '{sender}'",
            top=20,
            select=["id", "subject", "sender"],
        )
        # Trouver l'email dont le sujet contient la racine (après suppression des préfixes)
        clean_target = _re.sub(r"^\[(?:Traité|Routé-[^\]]+)\]\s*", "", subject).strip()[:40]
        target = next(
            (e for e in emails if clean_target.lower() in e.get("subject", "").lower()),
            None,
        )
        if not target:
            raise HTTPException(404, f"Email introuvable pour {sender!r} / {clean_target!r}")

        orig = target["subject"]
        clean = _re.sub(r"^\[(?:Traité|Routé-[^\]]+)\]\s*", "", orig).strip()
        await outlook.update_message_subject(target["id"], f"[Traité] {clean}")
        return JSONResponse({"ok": True, "archived": f"[Traité] {clean}"})

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/pipeline/unroute-email")
async def pipeline_unroute_email(request: Request):
    """Retire le préfixe [Routé-*] d'un email pour le remettre dans la file.
    Body JSON : { subject, sender }
    Après cela, l'email sera repris au prochain lancement du pipeline.
    """
    data = await request.json()
    subject: str = data.get("subject", "")
    sender: str  = data.get("sender", "")
    if not subject or not sender:
        raise HTTPException(400, "subject et sender requis")

    try:
        from src.connectors.outlook import OutlookClient
        from src import config
        import re as _re

        outlook = OutlookClient()
        emails = await outlook.get_emails(
            folder_id=config.OUTLOOK_FOLDER_DEVIS,
            odata_filter=f"from/emailAddress/address eq '{sender}'",
            top=20,
            select=["id", "subject", "sender"],
        )
        clean_target = _re.sub(r"^\[(?:Traité|Routé-[^\]]+)\]\s*", "", subject).strip()[:40]
        target = next(
            (e for e in emails if clean_target.lower() in e.get("subject", "").lower()),
            None,
        )
        if not target:
            raise HTTPException(404, f"Email introuvable pour {sender!r}")

        orig = target["subject"]
        clean = _re.sub(r"^\[(?:Traité|Routé-[^\]]+)\]\s*", "", orig).strip()
        await outlook.update_message_subject(target["id"], clean)
        return JSONResponse({"ok": True, "restored": clean})

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


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

    async def doli_get_all_invoices() -> list:
        """Pagine toutes les factures — triées par date DESC (plus récentes en premier)."""
        all_inv: list = []
        for page in range(0, 10):
            batch = await doli_get("/invoices", {
                "limit": 500, "page": page, "type": 0,
                "sortfield": "t.rowid", "sortorder": "DESC",
            })
            if not isinstance(batch, list):
                break
            all_inv.extend(batch)
            if len(batch) < 500:
                break
        return all_inv

    # Requêtes parallèles (supplier_invoices avec fallback type=1 si 501)
    invoices_raw, proposals_raw, orders_raw = await asyncio.gather(
        doli_get_all_invoices(),
        doli_get("/proposals", {"limit": 500, "sortorder": "DESC", "sortfield": "t.rowid"}),
        doli_get("/orders",    {"limit": 500, "sortorder": "DESC", "sortfield": "t.rowid"}),
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

    # ── Factures récentes (toutes, triées par date desc, 20 dernières)
    factures_recentes = [
        {
            "ref":      f.get("ref"),
            "client":   _client(f),
            "montant":  round(float(f.get("total_ht") or 0), 2),
            "date":     f.get("date"),
            "statut":   int(f.get("statut") or 0),
            **build_links(f, "facture", _DOLI_WEB),
        }
        for f in invoices
        if int(f.get("statut") or 0) in (1, 2)   # validée ou payée
    ][:20]

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
            "total_ht": total_devis,
            "nb":       len(devis_ouverts),
            "detail":   devis_ouverts[:10],
        },
        "cmds_non_facturees": {
            "nb":       len(cmds_non_facturees),
            "total_ht": cmds_non_fact_ht,
        },
        "factures_recentes": {
            "nb":     len(factures_recentes),
            "detail": factures_recentes,
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
        doli_get("/proposals", {"limit": 500, "sortorder": "DESC", "sortfield": "t.rowid"}),
        doli_get("/orders",    {"limit": 500, "sortorder": "DESC", "sortfield": "t.rowid"}),
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

    async def doli_get_all_invoices() -> list:
        all_inv: list = []
        for page in range(0, 10):
            batch = await doli_get("/invoices", {"limit": 500, "page": page, "type": 0})
            if not isinstance(batch, list):
                break
            all_inv.extend(batch)
            if len(batch) < 500:
                break
        return all_inv

    invoices_raw, orders_raw = await asyncio.gather(
        doli_get_all_invoices(),
        doli_get("/orders", {"limit": 500, "sortorder": "DESC", "sortfield": "t.rowid"}),
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

    invoices: list = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for _page in range(0, 20):
                r = await client.get(
                    f"{_DOLIBARR_BASE}/invoices",
                    params={"limit": 500, "page": _page, "type": 0},
                    headers=_DOLI_HEADERS,
                )
                if r.status_code != 200:
                    break
                batch = r.json()
                if not isinstance(batch, list):
                    break
                invoices.extend(batch)
                if len(batch) < 500:
                    break
    except Exception:
        pass

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
    """Devis validés (statut=1) créés dans les 21 derniers jours, triés par montant décroissant, max 10."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"error": "Dolibarr non configuré"}, status_code=503)

    now = datetime.now(timezone.utc)
    cutoff = int((now - timedelta(days=21)).timestamp())
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

    proposals_raw = await doli_get("/proposals", {"limit": 500, "sortorder": "DESC", "sortfield": "t.rowid"})
    proposals = proposals_raw if isinstance(proposals_raw, list) else []

    # Filtrer : validé (statut=1), créé dans les 3 dernières semaines
    a_suivre = [
        p for p in proposals
        if int(p.get("statut") or 0) == 1
        and int(p.get("date") or p.get("date_creation") or 0) >= cutoff
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

    # Trier par montant décroissant (les plus importants en premier), limiter à 10
    a_suivre.sort(key=lambda p: float(p.get("total_ht") or 0), reverse=True)
    a_suivre = a_suivre[:10]

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
        doli_get("/proposals",    {"limit": 200, "sortorder": "DESC", "sortfield": "t.rowid"}),
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
        doli_get("/proposals", {"limit": 100, "sortorder": "DESC", "sortfield": "t.rowid"}),
        doli_get("/orders",    {"limit": 100, "sortorder": "DESC", "sortfield": "t.rowid"}),
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


@app.get("/api/chat/skills")
async def get_chat_skills(q: str = ""):
    """Debug : liste les skills disponibles et ceux qui seraient sélectionnés pour un message donné."""
    _load_skills_once()
    all_skills = sorted(_skills_cache.keys())
    selected: list[str] = []
    if q:
        selected = _select_skills([{"role": "user", "content": q}])
    return JSONResponse({
        "skills_loaded": len(all_skills),
        "skills_available": all_skills,
        "selected_for_query": selected,
        "max_per_turn": _MAX_SKILLS,
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


# ── Page Pipeline ──────────────────────────────────────────────────────────

@app.get("/pipeline")
async def pipeline_page():
    html_file = Path(__file__).parent / "pipeline.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="pipeline.html not found")
    return FileResponse(html_file)


# ── Autopilot ───────────────────────────────────────────────────────────────

_AUTOPILOT_FILE = ROOT / "_config" / "autopilot.json"


def _read_autopilot() -> dict:
    try:
        if _AUTOPILOT_FILE.exists():
            return json.loads(_AUTOPILOT_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"enabled": False, "enabled_at": None}


def _write_autopilot(state: dict) -> None:
    _AUTOPILOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTOPILOT_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


@app.get("/api/pipeline/autopilot")
async def get_autopilot():
    return JSONResponse(_read_autopilot())


@app.post("/api/pipeline/autopilot")
async def set_autopilot(request: Request):
    data = await request.json()
    enabled = bool(data.get("enabled", False))
    state = {
        "enabled": enabled,
        "enabled_at": datetime.now(timezone.utc).isoformat() if enabled else None,
    }
    _write_autopilot(state)
    return JSONResponse(state)


# ── File d'attente Outlook ──────────────────────────────────────────────────

@app.get("/api/pipeline/queue")
async def get_pipeline_queue():
    """Emails en attente dans le dossier DEVIS Outlook (non traités, non routés)."""
    try:
        from src.connectors.outlook import OutlookClient
        from src import config as _cfg
        outlook = OutlookClient()
        _ODATA_FILTER = (
            "not(startswith(subject,'[Traité]'))"
            " and not(startswith(subject,'[Routé-'))"
        )
        emails = await outlook.get_emails(
            folder_id=_cfg.OUTLOOK_FOLDER_DEVIS,
            odata_filter=_ODATA_FILTER,
            top=20,
            select=["id", "subject", "sender", "receivedDateTime", "bodyPreview", "hasAttachments"],
        )
        items = [
            {
                "id":             e["id"],
                "subject":        e.get("subject", ""),
                "sender_name":    e.get("sender", {}).get("emailAddress", {}).get("name", ""),
                "sender_address": e.get("sender", {}).get("emailAddress", {}).get("address", ""),
                "received_at":    e.get("receivedDateTime", ""),
                "preview":        e.get("bodyPreview", "")[:150],
                "has_attachments": e.get("hasAttachments", False),
            }
            for e in (emails or [])
        ]
        return JSONResponse({"queue": items, "count": len(items)})
    except Exception as exc:
        return JSONResponse({"queue": [], "count": 0, "error": str(exc)})


# ── Gates Dolibarr ─────────────────────────────────────────────────────────

@app.get("/api/pipeline/gates")
async def get_pipeline_gates():
    """Gates en attente : agendaevents Dolibarr done=0 avec label ⏸."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        return JSONResponse({"gates": [], "count": 0, "error": "Dolibarr non configuré"})
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{_DOLIBARR_BASE}/agendaevents",
                params={"limit": 50, "sqlfilters": "(t.done:=:0)"},
                headers=_DOLI_HEADERS,
                timeout=10,
            )
        events = r.json() if r.status_code == 200 else []
        gates = [
            {
                "id":       e.get("id"),
                "label":    e.get("label", ""),
                "note":     (e.get("note") or ""),
                "datep":    e.get("datep"),
                "done":     int(e.get("done") or 0),
                "doli_url": f"{_DOLI_WEB}/comm/action/card.php?id={e.get('id')}",
            }
            for e in (events if isinstance(events, list) else [])
            if str(e.get("label", "")).startswith("⏸")
        ]
        return JSONResponse({"gates": gates, "count": len(gates)})
    except Exception as exc:
        return JSONResponse({"gates": [], "count": 0, "error": str(exc)})


@app.post("/api/pipeline/gate/{event_id}/approve")
async def approve_gate(event_id: int):
    """Valide une gate : done=1."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        raise HTTPException(503, "Dolibarr non configuré")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.put(
                f"{_DOLIBARR_BASE}/agendaevents/{event_id}",
                json={"done": 1},
                headers={**_DOLI_HEADERS, "Content-Type": "application/json"},
                timeout=10,
            )
        if r.status_code not in (200, 201):
            raise HTTPException(r.status_code, r.text[:200])
        return JSONResponse({"ok": True, "event_id": event_id, "action": "approved"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/pipeline/step-action")
async def pipeline_step_action(request: Request):
    """Enregistre une action sur un step (validate / flag) via un agenda Dolibarr.
    Body JSON : { action: 'validate'|'flag', step: str, ref: str, note: str }
    """
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        raise HTTPException(503, "Dolibarr non configuré")
    data = await request.json()
    action = data.get("action", "validate")   # validate | flag
    step   = data.get("step", "")
    ref    = data.get("ref", "")
    note   = data.get("note", "")
    icon   = "✓" if action == "validate" else "⚑"
    label  = f"{icon} {step} — {ref}".strip(" —") if ref else f"{icon} {step}"
    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "label":  label,
        "note":   note,
        "done":   1 if action == "validate" else 0,
        "datep":  now_ts,
        "datep2": now_ts,
        "type_id": "4",
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_DOLIBARR_BASE}/agendaevents",
                json=payload,
                headers={**_DOLI_HEADERS, "Content-Type": "application/json"},
                timeout=10,
            )
        return JSONResponse({"ok": True, "label": label, "status": r.status_code})
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/pipeline/gate/{event_id}/reject")
async def reject_gate(event_id: int, request: Request):
    """Refuse une gate : label ❌ + done=1. Body JSON optionnel : {note}."""
    if not _DOLIBARR_BASE or not _DOLIBARR_KEY:
        raise HTTPException(503, "Dolibarr non configuré")
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        extra_note = body.get("note", "")
        async with httpx.AsyncClient() as client:
            r_get = await client.get(
                f"{_DOLIBARR_BASE}/agendaevents/{event_id}",
                headers=_DOLI_HEADERS,
                timeout=10,
            )
            ev = r_get.json() if r_get.status_code == 200 else {}
            current_label = ev.get("label", "")
            new_label = current_label.replace("⏸", "❌", 1)
            existing_note = ev.get("note") or ""
            new_note = f"{existing_note}\n[REFUSÉ] {extra_note}".strip() if extra_note else f"{existing_note}\n[REFUSÉ]".strip()
            r_put = await client.put(
                f"{_DOLIBARR_BASE}/agendaevents/{event_id}",
                json={"done": 1, "label": new_label, "note": new_note},
                headers={**_DOLI_HEADERS, "Content-Type": "application/json"},
                timeout=10,
            )
        if r_put.status_code not in (200, 201):
            raise HTTPException(r_put.status_code, r_put.text[:200])
        return JSONResponse({"ok": True, "event_id": event_id, "action": "rejected"})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Skills dynamiques ───────────────────────────────────────────────────────

_SKILLS_DIR = ROOT / ".claude" / "skills"
_skills_cache: dict[str, str] = {}   # skill-name → contenu SKILL.md complet
_SKILL_MAX_CHARS  = 4_000            # tronquer chaque skill injecté à 4000 chars
_MAX_SKILLS       = 4                # max skills injectés par tour


def _load_skills_once() -> None:
    """Charge tous les SKILL.md non-désactivés une seule fois (lazy)."""
    if _skills_cache:
        return
    if not _SKILLS_DIR.exists():
        return
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_disabled"):
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            try:
                _skills_cache[skill_dir.name] = skill_file.read_text(encoding="utf-8")
            except Exception:
                pass


# Mapping trigger-keywords → skill-name  (ordre = priorité si quota atteint)
_SKILL_TRIGGERS: list[tuple[str, list[str]]] = [
    # — Sécurité & fondation —
    ("gestion-erreurs-inpressco",
     ["erreur", "error", "ça ne marche", "problème", "échec", "bug", "plantage",
      "api ne répond", "timeout", "401", "403", "500"]),
    ("validation-qc-inpressco",
     ["vérifie", "valide", "contrôle", "avant d'envoyer", "avant envoi", "est-ce que c'est bon",
      "qualité", "relecture", "check"]),
    # — Client & mémoire —
    ("memoire-client-inpressco",
     ["client", "société", "tiers", "historique", "fiche client", "qui est", "c'est qui",
      "commande souvent", "mémoire", "profil"]),
    # — Email & routing —
    ("mail-routing-inpressco",
     ["email entrant", "mail reçu", "catégorise", "classe cet email", "quel type", "routing",
      "new_project", "routage"]),
    ("analyse-sentiment-email",
     ["sentiment", "analyse cet email", "urgence", "ton du client", "profil expéditeur",
      "réponse miroir", "intention"]),
    # — Commerce & devis —
    ("inpressco-commerce",
     ["brief", "budget", "finition", "papier", "grammage", "format", "impression", "matière",
      "pelliculage", "dorure", "gaufrage", "vernis", "devis impression", "propose"]),
    ("reponse-client-inpressco",
     ["réponds", "rédige", "envoie", "mail pour", "réponse client", "confirme au client",
      "email de réponse", "config_client", "paola"]),
    ("agent-acheteur-inpressco",
     ["fournisseur", "sous-traitant", "façonnier", "papetier", "rfq", "demande de prix",
      "consulte le", "appel d'offre", "tarif fournisseur"]),
    # — Production & suivi —
    ("suivi-commande-inpressco",
     ["commande", "production", "bat", "statut commande", "livraison", "suivi", "en cours",
      "bloqué", "retard"]),
    ("agenda-inpressco",
     ["rdv", "rendez-vous", "agenda", "rappel", "relance dans", "calendrier", "planning",
      "réunion", "échéance", "bloque"]),
    # — Documents & archivage —
    ("generation-pdf-inpressco",
     ["pdf", "génère le pdf", "document client", "mettre en pdf", "bon de commande"]),
    ("archiveur-inpressco",
     ["archive", "range", "classe", "pj", "pièce jointe", "bat archiver", "dépôt"]),
    ("bdd-images-query-inpressco",
     ["visuel", "logo", "image", "bat de référence", "assets", "on a déjà", "template"]),
    # — Finance & analyse —
    ("controleur-gestion-inpressco",
     ["tréso", "chiffre d'affaires", "impayé", "marge", "rentabilité", "reporting",
      "financ", "dso", "encours", "pipe commercial"]),
    ("analyse-transversale-inpressco",
     ["tendance", "analyse globale", "rfm", "anomalie", "bilan", "qui relancer",
      "mix produit", "saisonnalité", "délai moyen"]),
    # — Workflow complexe —
    ("orchestrateur-inpressco",
     ["plusieurs étapes", "enchaîne", "workflow complet", "traite cet email",
      "de bout en bout", "pipeline"]),
    # — Autres —
    ("projets-artefacts-inpressco",
     ["sauvegarde", "retrouve", "reprends", "où est le devis", "on avait préparé", "artefact"]),
    ("charte-graphique-inpressco",
     ["charte", "couleurs", "police", "typographie", "identité visuelle", "brand"]),
    ("veille-prix-inpressco",
     ["exaprint", "onlineprinters", "pixartprinting", "concurrent", "benchmark",
      "compare nos prix"]),
    ("chat-to-db-inpressco",
     ["enregistre", "note ça", "retiens", "persiste", "mets à jour dans dolibarr",
      "sauvegarde cette info"]),
]


def _select_skills(messages: list[dict]) -> list[str]:
    """Retourne les noms des skills pertinents basés sur les derniers messages utilisateur."""
    user_texts: list[str] = []
    for m in messages[-6:]:
        if m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    user_texts.append(block.get("text", "").lower())
        elif isinstance(content, str):
            user_texts.append(content.lower())
    corpus = " ".join(user_texts)

    selected: list[str] = []
    for skill_name, keywords in _SKILL_TRIGGERS:
        if len(selected) >= _MAX_SKILLS:
            break
        if skill_name not in _skills_cache:
            continue
        if any(kw in corpus for kw in keywords):
            selected.append(skill_name)
    return selected


def _build_skills_context(skill_names: list[str]) -> str:
    """Construit le bloc skills à injecter dans le system prompt."""
    if not skill_names:
        return ""
    blocks: list[str] = []
    for name in skill_names:
        content = _skills_cache.get(name, "")
        if not content:
            continue
        if len(content) > _SKILL_MAX_CHARS:
            content = content[:_SKILL_MAX_CHARS] + "\n... [skill tronqué]"
        blocks.append(f"## SKILL ACTIF : {name}\n\n{content}")
    if not blocks:
        return ""
    return (
        "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  SKILLS SYSTÈME INPRESSCO ACTIVÉS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Les skills suivants sont actifs pour cette requête. "
        "Applique leurs règles, workflows et formats de sortie.\n\n"
        + "\n\n---\n\n".join(blocks)
        + "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )






@app.post("/api/chat")
async def chat(request: Request):
    """Chat IA via claude CLI (subprocess). Body: {messages: [{role, content}], session_id?: str}"""
    if not _CLAUDE_BIN or not Path(_CLAUDE_BIN).exists():
        return JSONResponse({"error": "claude CLI introuvable — vérifiez l'installation"}, status_code=503)

    body = await request.json()
    messages = body.get("messages", [])
    session_id = body.get("session_id")  # fourni par le frontend pour continuer une conversation
    if not messages:
        return JSONResponse({"error": "messages vides"}, status_code=400)

    # Dernier message utilisateur → prompt envoyé à claude
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        None
    )
    if not last_user:
        return JSONResponse({"error": "aucun message utilisateur"}, status_code=400)

    # Construire le prompt texte (images ignorées en mode CLI)
    if isinstance(last_user, list):
        prompt = " ".join(
            block.get("text", "") for block in last_user if block.get("type") == "text"
        ).strip()
    else:
        prompt = str(last_user).strip()

    if not prompt:
        return JSONResponse({"error": "prompt vide (contenu image uniquement non supporté via CLI)"}, status_code=400)

    # Guardrail : restreindre le chat au rôle d'assistant CRM lecture seule.
    # Ne pas modifier les fichiers source, ne pas écrire de code, ne pas exécuter de commandes.
    _CHAT_SCOPE = (
        "Tu es l'assistant opérationnel du dashboard InPressco. "
        "Ton rôle : consulter et présenter les données (Dolibarr, emails, pipeline, KPIs). "
        "Interdictions absolues dans ce contexte : modifier des fichiers source Python, "
        "écrire ou supprimer du code, exécuter des commandes shell non liées à la lecture de données. "
        "Si une action de modification du système est demandée, demande une confirmation explicite "
        "avant d'agir."
    )
    cmd = [_CLAUDE_BIN, "--print", "--output-format", "stream-json", "--verbose",
           "--permission-mode", "bypassPermissions",
           "--append-system-prompt", _CHAT_SCOPE]
    if session_id:
        cmd += ["--resume", session_id]
    cmd += ["--", prompt]

    async def generate():
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(ROOT),
            )
            session_sent = False
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type", "")

                # Envoyer session_id au frontend dès qu'on le reçoit (init ou result)
                if not session_sent and obj.get("session_id"):
                    yield f"data: {json.dumps({'session_id': obj['session_id']})}\n\n"
                    session_sent = True

                if t == "assistant":
                    for block in obj.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            yield f"data: {json.dumps({'text': block['text']})}\n\n"
                elif t == "tool_use":
                    yield f"data: {json.dumps({'tool_call': {'name': obj.get('name', '')}})}\n\n"
                # "system", "result", "rate_limit_event" → ignorés côté texte

            await proc.wait()
            if proc.returncode != 0:
                err_out = (await proc.stderr.read()).decode("utf-8", errors="replace")[:400]
                yield f"data: {json.dumps({'error': f'claude CLI erreur (code {proc.returncode}): {err_out}'})}\n\n"

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


def _html_go_response(title: str, message: str, success: bool) -> HTMLResponse:
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


# ── Outils système — /api/health et /api/synthesis ─────────────────────────

@app.get("/api/health")
async def get_health():
    """Rapport de santé système — connexions, pipeline, skills, anti-patterns.

    Retourne le dernier rapport depuis reports/health_report.json.
    Si le rapport a plus de 5 minutes, déclenche un refresh en arrière-plan.
    """
    health_file = ROOT / "reports" / "health_report.json"
    if not health_file.exists():
        return JSONResponse(
            {"error": "Rapport absent. Exécuter : python main.py --verify"},
            status_code=503,
        )
    try:
        data = json.loads(health_file.read_text(encoding="utf-8"))
    except Exception as e:
        return JSONResponse({"error": f"Lecture rapport échouée : {e}"}, status_code=500)

    age_s = int(
        datetime.now(timezone.utc).timestamp()
        - datetime.fromisoformat(data.get("generated_at", "2000-01-01")).timestamp()
    )
    if age_s > 300:
        asyncio.create_task(_refresh_health_bg())

    return JSONResponse({**data, "age_seconds": age_s})


async def _refresh_health_bg() -> None:
    """Refresh silencieux du rapport de santé (fire-and-forget)."""
    try:
        sys.path.insert(0, str(ROOT))
        from tools.system_verify import run_verify
        await run_verify(ROOT / "reports" / "health_report.json")
    except Exception:
        pass


@app.get("/api/connections")
async def get_connections():
    """Statut des connexions basé sur les variables d'env + dernière vérification si disponible."""
    connectors = [
        {
            "id":     "dolibarr",
            "name":   "Dolibarr",
            "ok":     bool(_DOLIBARR_BASE and _DOLIBARR_KEY),
            "detail": _DOLI_WEB or "Non configuré",
        },
        {
            "id":     "anthropic",
            "name":   "Claude API",
            "ok":     bool(_ANTHROPIC_KEY),
            "detail": "Clé présente" if _ANTHROPIC_KEY else "Non configuré",
        },
        {
            "id":     "outlook",
            "name":   "Outlook",
            "ok":     bool(os.environ.get("OUTLOOK_TENANT_ID") and os.environ.get("OUTLOOK_CLIENT_ID")),
            "detail": "Azure AD configuré" if os.environ.get("OUTLOOK_TENANT_ID") else "Non configuré",
        },
    ]

    # Enrichir avec la latence du dernier health report si frais (<30min)
    health_file = ROOT / "reports" / "health_report.json"
    last_check = None
    if health_file.exists():
        try:
            data = json.loads(health_file.read_text(encoding="utf-8"))
            age_s = int(
                datetime.now(timezone.utc).timestamp()
                - datetime.fromisoformat(data.get("generated_at", "2000-01-01")).timestamp()
            )
            if age_s < 1800 and data.get("checks"):
                latency_map = {c["name"]: c.get("latency_ms") for c in data["checks"]}
                for conn in connectors:
                    conn["latency_ms"] = latency_map.get(conn["id"])
                last_check = data.get("generated_at")
        except Exception:
            pass

    return JSONResponse({
        "connectors": connectors,
        "last_check": last_check,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/synthesis")
async def get_synthesis():
    """Synthèse stratégique live depuis Dolibarr : CA, DSO, RFM, projections, wellbeing.

    Calcule en temps réel — prévoir ~2-3s de latence.
    Pour un cache : appeler --synthesis en cron et lire reports/STRATEGIC_SYNTHESIS.md.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from tools.strategic_synthesis import run_synthesis
        snap = await run_synthesis(
            output_dir=ROOT / "reports",
            trigger_report=False,   # pas d'écriture fichier sur chaque appel API
        )
        return JSONResponse(snap)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Envoi email sortant ────────────────────────────────────────────────────

@app.post("/api/send-email")
async def send_email(request: Request):
    """Envoie un email via Microsoft Graph (boîte contact@in-pressco.com).

    Body JSON :
        to_email            : str   — destinataire principal (requis)
        subject             : str   — objet (requis)
        body_html           : str   — corps HTML (requis)
        cc_emails           : list  — destinataires CC (optionnel)
        reply_to_message_id : str   — ID Outlook pour conserver le thread (optionnel)
        agenda_event_id     : int   — ID Dolibarr ⏸ à marquer done=1 (optionnel)
        devis_folder_id     : str   — ID dossier Outlook devis pour classer l'envoi (optionnel)

    Retourne :
        { "status": "sent", "message_id": "...", "to": "...", "subject": "..." }
    """
    data = await request.json()
    to_email: str = data.get("to_email", "").strip()
    subject: str = data.get("subject", "").strip()
    body_html: str = data.get("body_html", "").strip()
    cc_emails: list = data.get("cc_emails") or []
    reply_to_message_id: str | None = data.get("reply_to_message_id") or None
    agenda_event_id: int | None = data.get("agenda_event_id") or None
    devis_folder_id: str | None = data.get("devis_folder_id") or None

    if not to_email or not subject or not body_html:
        raise HTTPException(400, "to_email, subject et body_html sont requis")

    # ── 1. Envoi via Microsoft Graph (retourne message_id) ────────────────
    try:
        from src.connectors.outlook import OutlookClient
        outlook = OutlookClient()
        message_id = await outlook.send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            cc_emails=cc_emails or None,
            reply_to_message_id=reply_to_message_id,
        )
    except Exception as exc:
        raise HTTPException(502, f"Erreur envoi Outlook : {exc}")

    # ── 2. Classer l'email envoyé dans le dossier devis si fourni ─────────
    if devis_folder_id and message_id:
        try:
            await outlook.move_message(message_id, devis_folder_id)
        except Exception:
            pass  # Non bloquant

    # ── 3. Marquer l'événement Dolibarr ⏸ comme done=1 si fourni ─────────
    if agenda_event_id:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.put(
                    f"{_DOLIBARR_BASE}/agendaevents/{agenda_event_id}",
                    headers=_DOLI_HEADERS,
                    json={"done": 1},
                )
        except Exception:
            pass  # Non bloquant

    return JSONResponse({
        "status": "sent",
        "message_id": message_id,
        "to": to_email,
        "subject": subject,
        "cc": cc_emails,
        "classified_in_folder": devis_folder_id is not None,
        "agenda_event_closed": agenda_event_id is not None,
    })


# ── Arborescence Outlook par devis ─────────────────────────────────────────

async def _ensure_root_folders() -> tuple[str, str]:
    """Retourner (dossiers_devis_id, archives_id) en créant si besoin.

    Lit d'abord les env vars OUTLOOK_FOLDER_DOSSIERS_DEVIS et OUTLOOK_FOLDER_ARCHIVES.
    Si vides, crée les dossiers à la racine de la boîte et logue les IDs.
    """
    from src.connectors.outlook import OutlookClient
    from src import config as _cfg

    dossiers_id = _cfg.OUTLOOK_FOLDER_DOSSIERS_DEVIS
    archives_id = _cfg.OUTLOOK_FOLDER_ARCHIVES

    if dossiers_id and archives_id:
        return dossiers_id, archives_id

    outlook = OutlookClient()
    token = await outlook._get_token()

    # Récupérer les dossiers racine
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{outlook.GRAPH_BASE}/mailFolders",
            headers=outlook._headers(token),
            params={"$top": 50, "$select": "id,displayName"},
        )
        resp.raise_for_status()
        root_folders = {f["displayName"]: f["id"] for f in resp.json().get("value", [])}

    if not dossiers_id:
        name = ">> DOSSIERS-DEVIS"
        dossiers_id = root_folders.get(name) or (
            await outlook.create_folder("msgfolderroot", name)
        )["id"]

    if not archives_id:
        name = ">> ARCHIVES-FACTURES"
        archives_id = root_folders.get(name) or (
            await outlook.create_folder("msgfolderroot", name)
        )["id"]

    return dossiers_id, archives_id


@app.post("/api/outlook/folders/create-devis")
async def outlook_create_devis_folder(request: Request):
    """Créer un sous-dossier Outlook pour un devis Dolibarr.

    Appelé automatiquement à la création d'un devis dans Dolibarr.
    Idempotent : retourne l'ID existant si le dossier existe déjà.

    Body JSON :
        devis_ref  : str — ex: "DEV-2026-089" (requis)
        tiers_nom  : str — nom du client, tronqué à 25 chars (optionnel)
        projet_nom : str — nom du projet, tronqué à 25 chars (optionnel)

    Retourne :
        { "folder_id": "...", "folder_name": "...", "created": true|false }
    """
    data = await request.json()
    devis_ref: str = data.get("devis_ref", "").strip()
    tiers_nom: str = (data.get("tiers_nom") or "")[:25].strip()
    projet_nom: str = (data.get("projet_nom") or "")[:25].strip()

    if not devis_ref:
        raise HTTPException(400, "devis_ref est requis")

    parts = [devis_ref]
    if tiers_nom:
        parts.append(tiers_nom)
    if projet_nom:
        parts.append(projet_nom)
    folder_name = " — ".join(parts)

    try:
        from src.connectors.outlook import OutlookClient
        dossiers_id, _ = await _ensure_root_folders()
        outlook = OutlookClient()

        # Vérifier si le dossier existe déjà
        existing = await outlook.get_folders(dossiers_id)
        for f in existing:
            if f.get("displayName", "").startswith(devis_ref):
                return JSONResponse({"folder_id": f["id"], "folder_name": f["displayName"], "created": False})

        folder_id = await outlook.get_or_create_folder(dossiers_id, folder_name)
        return JSONResponse({"folder_id": folder_id, "folder_name": folder_name, "created": True})

    except Exception as exc:
        raise HTTPException(502, f"Erreur création dossier Outlook : {exc}")


@app.post("/api/outlook/folders/move-email")
async def outlook_move_email(request: Request):
    """Déplacer un email (entrant ou envoyé) vers le dossier de son devis.

    Body JSON :
        message_id    : str — ID Graph du message à déplacer (requis)
        devis_folder_id : str — ID du dossier Outlook cible (requis)

    Retourne :
        { "status": "moved", "message_id": "..." }
    """
    data = await request.json()
    message_id: str = data.get("message_id", "").strip()
    folder_id: str = data.get("devis_folder_id", "").strip()

    if not message_id or not folder_id:
        raise HTTPException(400, "message_id et devis_folder_id sont requis")

    try:
        from src.connectors.outlook import OutlookClient
        outlook = OutlookClient()
        await outlook.move_message(message_id, folder_id)
        return JSONResponse({"status": "moved", "message_id": message_id})
    except Exception as exc:
        raise HTTPException(502, f"Erreur déplacement email : {exc}")


@app.post("/api/outlook/folders/archive-devis")
async def outlook_archive_devis(request: Request):
    """Archiver le dossier Outlook d'un devis une fois la facture créée dans Dolibarr.

    Déplace le dossier de >> DOSSIERS-DEVIS vers >> ARCHIVES-FACTURES
    et le renomme pour y ajouter la référence facture.

    Body JSON :
        devis_ref    : str — ex: "DEV-2026-089" (requis)
        facture_ref  : str — ex: "FA-2026-042" (optionnel, ajouté au nom du dossier)

    Retourne :
        { "status": "archived", "folder_id": "...", "new_name": "..." }
    """
    data = await request.json()
    devis_ref: str = data.get("devis_ref", "").strip()
    facture_ref: str = (data.get("facture_ref") or "").strip()

    if not devis_ref:
        raise HTTPException(400, "devis_ref est requis")

    try:
        from src.connectors.outlook import OutlookClient
        dossiers_id, archives_id = await _ensure_root_folders()
        outlook = OutlookClient()

        # Trouver le dossier devis
        folders = await outlook.get_folders(dossiers_id)
        target = next((f for f in folders if f.get("displayName", "").startswith(devis_ref)), None)
        if not target:
            raise HTTPException(404, f"Dossier Outlook introuvable pour {devis_ref}")

        folder_id = target["id"]
        current_name = target["displayName"]

        # Renommer avec référence facture si fournie
        new_name = f"[ARCHIVÉ] {current_name}"
        if facture_ref:
            new_name = f"[ARCHIVÉ] {facture_ref} — {current_name}"

        await outlook.rename_folder(folder_id, new_name)
        await outlook.move_folder(folder_id, archives_id)

        return JSONResponse({"status": "archived", "folder_id": folder_id, "new_name": new_name})

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Erreur archivage dossier Outlook : {exc}")


@app.get("/api/outlook/folders")
async def outlook_list_folders(archived: bool = False):
    """Lister les dossiers Outlook devis (actifs ou archivés).

    Query params :
        archived : bool — false = dossiers actifs, true = archives (défaut: false)

    Retourne :
        { "folders": [{ "id": "...", "name": "...", "devis_ref": "..." }] }
    """
    try:
        from src.connectors.outlook import OutlookClient
        dossiers_id, archives_id = await _ensure_root_folders()
        outlook = OutlookClient()
        parent_id = archives_id if archived else dossiers_id
        folders = await outlook.get_folders(parent_id)
        return JSONResponse({
            "folders": [
                {
                    "id": f["id"],
                    "name": f["displayName"],
                    "devis_ref": f["displayName"].split(" — ")[0].replace("[ARCHIVÉ] ", "").strip(),
                    "total_emails": f.get("totalItemCount", 0),
                    "unread": f.get("unreadItemCount", 0),
                }
                for f in folders
            ]
        })
    except Exception as exc:
        raise HTTPException(502, f"Erreur lecture dossiers Outlook : {exc}")


# ── Webhook Dolibarr — archivage automatique dossier Outlook à la facturation ──

@app.post("/api/dolibarr/webhook")
async def dolibarr_webhook(request: Request):
    """Webhook appelé par Dolibarr lors d'un changement de statut ou d'une création d'objet.

    Déclenche l'archivage Outlook automatiquement quand un devis passe en statut
    facturé (statut=4) ou quand une facture est créée depuis un devis.

    Configuration côté Dolibarr :
        Admin > Configuration > Interfaces > Webhooks
        URL : {DASHBOARD_URL}/api/dolibarr/webhook
        Événements : propal (close/invoice) OU facture (create)

    Body attendu (format Dolibarr webhook) :
        {
          "trigger": "PROPAL_CLOSE" | "BILL_CREATE" | ...,
          "object_type": "propal" | "facture",
          "object_id": 123,
          "fk_propal": 123          // présent si object_type=facture
        }

    L'endpoint est aussi appelable manuellement avec :
        { "devis_ref": "DEV-2026-089", "facture_ref": "FA-2026-042" }
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(400, "Body JSON invalide")

    trigger      = data.get("trigger", "")
    object_type  = data.get("object_type", "")
    object_id    = data.get("object_id")
    devis_ref    = data.get("devis_ref", "").strip()   # appel manuel direct
    facture_ref  = data.get("facture_ref", "").strip()

    # ── Appel manuel direct (devis_ref fourni explicitement) ───────────────
    if devis_ref:
        pass  # on saute la résolution Dolibarr — devis_ref et facture_ref déjà connus

    # ── Résolution automatique depuis l'event Dolibarr ────────────────────
    elif object_type == "facture" and object_id:
        # Récupérer la facture pour remonter au devis lié
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{_DOLIBARR_BASE}/invoices/{object_id}",
                    headers=_DOLI_HEADERS,
                )
                if r.is_success:
                    inv = r.json()
                    facture_ref = inv.get("ref", "")
                    propal_id   = inv.get("fk_propal") or data.get("fk_propal")
                    if propal_id:
                        rp = await client.get(
                            f"{_DOLIBARR_BASE}/proposals/{propal_id}",
                            headers=_DOLI_HEADERS,
                        )
                        if rp.is_success:
                            devis_ref = rp.json().get("ref", "")
        except Exception as e:
            raise HTTPException(502, f"Impossible de résoudre devis/facture depuis l'event : {e}")

    elif object_type == "propal" and object_id:
        # Le devis lui-même a changé de statut
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                rp = await client.get(
                    f"{_DOLIBARR_BASE}/proposals/{object_id}",
                    headers=_DOLI_HEADERS,
                )
                if rp.is_success:
                    prop = rp.json()
                    devis_ref = prop.get("ref", "")
                    statut    = int(prop.get("statut", 0))
                    if statut != 4:  # 4 = facturé
                        return JSONResponse({"status": "ignored", "reason": f"statut={statut}, pas encore facturé"})
        except Exception as e:
            raise HTTPException(502, f"Impossible de lire le devis : {e}")

    if not devis_ref:
        return JSONResponse({"status": "ignored", "reason": "devis_ref non résolu"})

    # ── Archiver le dossier Outlook ────────────────────────────────────────
    try:
        from src.connectors.outlook import OutlookClient
        dossiers_id, archives_id = await _ensure_root_folders()
        outlook = OutlookClient()

        folders = await outlook.get_folders(dossiers_id)
        target = next(
            (f for f in folders if f.get("displayName", "").startswith(devis_ref)),
            None,
        )
        if not target:
            return JSONResponse({"status": "skipped", "reason": f"Aucun dossier Outlook pour {devis_ref}"})

        folder_id    = target["id"]
        current_name = target["displayName"]
        new_name     = f"[ARCHIVÉ] {facture_ref} — {current_name}" if facture_ref else f"[ARCHIVÉ] {current_name}"

        await outlook.rename_folder(folder_id, new_name)
        await outlook.move_folder(folder_id, archives_id)

        return JSONResponse({
            "status": "archived",
            "devis_ref": devis_ref,
            "facture_ref": facture_ref,
            "folder_id": folder_id,
            "new_name": new_name,
        })

    except Exception as exc:
        raise HTTPException(502, f"Erreur archivage webhook : {exc}")


# ── Entrypoint direct ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8080, reload=True)
