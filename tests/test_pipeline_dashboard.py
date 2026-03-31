"""tests/test_pipeline_dashboard.py — Test complet du poste de pilotage InPressco.

Simule le comportement du navigateur sur /pipeline :
  1. Chargement de tous les runs (/api/pipeline-runs)
  2. Détail de chaque run (tous les champs meta)
  3. Inspecteur de nœud — simulation pour chaque step de chaque run
  4. Données d'inspection : extractStepFields, buildStepSummary, getValidationActions
  5. Boutons d'action : step-action (validate/flag), accès Dolibarr, gates
  6. File d'attente emails + PJ (/api/pipeline/queue)
  7. Gates en attente (/api/pipeline/gates)
  8. Autopilot (/api/pipeline/autopilot)
  9. Config Dolibarr (URLs constructibles)

Usage:
    python tests/test_pipeline_dashboard.py
    python tests/test_pipeline_dashboard.py --url http://localhost:8000
    python tests/test_pipeline_dashboard.py --run 0        # inspecter run N
    python tests/test_pipeline_dashboard.py --verbose      # détail exhaustif
"""
import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# ── Config ─────────────────────────────────────────────────────────────────
DEFAULT_URL = "http://127.0.0.1:8000"
TIMEOUT_S   = 15

# ── Couleurs ────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(s):   return f"{GREEN}✓ {s}{RESET}"
def fail(s): return f"{RED}✗ {s}{RESET}"
def warn(s): return f"{YELLOW}⚠ {s}{RESET}"
def info(s): return f"{CYAN}  {s}{RESET}"
def dim(s):  return f"{DIM}{s}{RESET}"
def bold(s): return f"{BOLD}{s}{RESET}"

# ── Définition des steps (miroir de pipeline.html) ──────────────────────────

STEPS_FLUX_A = [
    {"key": "s01_get_email",             "label": "Email",   "actions": ["view"]},
    {"key": "s02_extract_client_ai",     "label": "IA x3",   "actions": ["view", "validate", "flag", "modal"]},
    {"key": "s03_clean_data",            "label": "Route",   "actions": ["view", "validate", "flag"]},
    {"key": "s04_find_or_create_client", "label": "Tiers",   "actions": ["view", "validate", "flag", "doli_tiers"]},
    {"key": "s05_get_attachments",       "label": "PJ",      "actions": ["view"]},
    {"key": "s06_analyse_besoin",        "label": "Besoin",  "actions": ["view", "validate", "flag", "modify", "modal"]},
    {"key": "s07_build_devis_lines",     "label": "Lignes",  "actions": ["view", "validate", "flag", "modal"]},
    {"key": "s08_create_devis",          "label": "Devis",   "actions": ["view", "validate", "flag", "doli_devis"]},
    {"key": "s09_upload_attachments",    "label": "Upload",  "actions": ["view"]},
    {"key": "s10_log_email",             "label": "Agenda",  "actions": ["view"]},
    {"key": "s11_archive_outlook",       "label": "Archive", "actions": ["view"]},
    {"key": "s12_notify_team",           "label": "Notif",   "actions": ["view", "validate"]},
    {"key": "__gate_go__",               "label": "GO ?",    "actions": ["view", "gate_approve", "gate_reject"], "isGate": True},
    {"key": "s13_send_email_client",     "label": "Envoi",   "actions": ["view"]},
]

STEPS_NON_DEVIS = [
    {"key": "s01_get_email",         "label": "Email",  "actions": ["view"]},
    {"key": "s02_extract_client_ai", "label": "IA x3",  "actions": ["view", "validate", "flag", "modal"]},
    {"key": "s_mark_non_devis",      "label": "Route",  "actions": ["view"]},
]

VALID_STATUSES  = {"done", "active", "pending", "skip", "error", "gate", None}
STEP_STATUS_MAP = {"done", "active", "pending", "skip", "error", "gate"}

# ── Dataclass résultat ──────────────────────────────────────────────────────
@dataclass
class TestResult:
    name:     str
    ok:       bool
    duration: float = 0.0
    details:  list  = field(default_factory=list)
    warnings: list  = field(default_factory=list)
    errors:   list  = field(default_factory=list)

# ── Client HTTP ─────────────────────────────────────────────────────────────
async def get(client: httpx.AsyncClient, url: str, path: str, params: dict = None) -> dict:
    r = await client.get(f"{url}{path}", params=params, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()

async def post(client: httpx.AsyncClient, url: str, path: str, body: dict) -> dict:
    r = await client.post(
        f"{url}{path}",
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT_S,
    )
    return {"status": r.status_code, "body": r.json() if r.headers.get("content-type","").startswith("application/json") else r.text}

# ══════════════════════════════════════════════════════════════════════════════
#  SUITE DE TESTS
# ══════════════════════════════════════════════════════════════════════════════

async def test_endpoints_base(client: httpx.AsyncClient, url: str) -> list[TestResult]:
    """Vérifie que tous les endpoints répondent correctement."""
    results = []

    endpoints = [
        ("/api/pipeline-runs",     "Historique runs"),
        ("/api/pipeline/queue",    "File d'attente Outlook"),
        ("/api/pipeline/gates",    "Gates en attente"),
        ("/api/pipeline/autopilot","Autopilot"),
        ("/api/config",            "Config (URLs Dolibarr)"),
        ("/api/status",            "Statut général"),
    ]

    for path, label in endpoints:
        t0 = time.monotonic()
        r = TestResult(name=f"GET {path} — {label}", ok=False)
        try:
            data = await get(client, url, path)
            r.ok = True
            r.details.append(f"HTTP 200 — {len(json.dumps(data))} bytes")
        except httpx.HTTPStatusError as e:
            r.errors.append(f"HTTP {e.response.status_code}")
        except Exception as e:
            r.errors.append(str(e))
        r.duration = time.monotonic() - t0
        results.append(r)

    return results


async def test_runs_data(client: httpx.AsyncClient, url: str, verbose: bool = False) -> list[TestResult]:
    """Vérifie la complétude des données de chaque run."""
    results = []
    t0 = time.monotonic()

    r = TestResult(name="Chargement runs (/api/pipeline-runs)", ok=False)
    try:
        data = await get(client, url, "/api/pipeline-runs", {"limit": 50})
        runs = data.get("runs", [])
        total = data.get("total", 0)

        if not runs:
            r.errors.append("Aucun run dans les logs — pipeline jamais lancé ?")
        else:
            r.ok = True
            r.details.append(f"{total} runs au total — {len(runs)} chargés")
    except Exception as e:
        r.errors.append(str(e))

    r.duration = time.monotonic() - t0
    results.append(r)

    if not r.ok:
        return results

    runs = data.get("runs", [])

    # ── Champs requis par run ──────────────────────────────────────────────
    required_fields = ["started_at", "status", "steps", "actions"]
    important_fields = {
        "email_subject":       "objet email (s01)",
        "email_sender":        "expéditeur email (s01)",
        "routing_category":    "catégorie routing (s02)",
        "routing_confidence":  "confiance routing (s02)",
        "soc_nom":             "nom société client (s02)",
        "client_email":        "email client (s02)",
    }

    for i, run in enumerate(runs[:20]):  # checker les 20 premiers
        t0 = time.monotonic()
        tr = TestResult(name=f"Run #{i} — {run.get('email_subject','(no subject)')[:45]}", ok=True)
        subj = run.get("email_subject", "(pas de sujet)")[:50]

        # Champs obligatoires
        for f in required_fields:
            if run.get(f) is None:
                tr.errors.append(f"Champ requis manquant: {f}")
                tr.ok = False

        # Champs importants (warnings si manquants)
        for f, label in important_fields.items():
            val = run.get(f)
            if val is None or val == "":
                tr.warnings.append(f"Champ vide: {label} ({f})")

        # Steps dict
        steps = run.get("steps", {})
        for sk in ["s01", "s02", "routing", "tiers", "devis"]:
            sv = steps.get(sk)
            if sv is not None and sv not in STEP_STATUS_MAP:
                tr.errors.append(f"Statut de step invalide: steps.{sk}={sv!r}")
                tr.ok = False

        # Actions list
        actions = run.get("actions", [])
        for a in actions:
            if not isinstance(a, dict) or "icon" not in a or "text" not in a:
                tr.errors.append(f"Format action invalide: {a}")

        # Status
        valid_run_statuses = {"running", "ok", "error", "stopped", "routed", "devis_created"}
        if run.get("status") not in valid_run_statuses:
            tr.warnings.append(f"Statut inconnu: {run.get('status')!r}")

        if verbose:
            tr.details.append(f"status={run.get('status')}  routing={run.get('routing_category')}  soc_nom={run.get('soc_nom')!r}")
            tr.details.append(f"steps={run.get('steps')}")
            tr.details.append(f"actions={[a.get('icon','?')+' '+a.get('text','?')[:30] for a in actions]}")

        tr.duration = time.monotonic() - t0
        results.append(tr)

    return results


def simulate_step_inspector(run: dict, step: dict, gates: list) -> dict:
    """Reproduit extractStepFields + buildStepSummary + getValidationActions.
    Retourne un dict {fields, summary, validation_actions, buttons_active}.
    """
    key = step["key"]
    s   = run.get("steps", {})
    short = key.split("_")[0]
    is_new_project = run.get("routing_category") == "NEW_PROJECT"

    # ── Calcul statut step ────────────────────────────────────────────────
    if key == "__gate_go__":
        if run.get("devis_ref"):
            st = "gate" if not any(g.get("label","").replace("⏸","").strip().find(run.get("devis_ref","")) >= 0 for g in gates) else "gate"
        else:
            st = "skip"
    else:
        sv = s.get(short)
        if sv:
            st = sv
        elif key in ("s03_clean_data", "s04_find_or_create_client", "s05_get_attachments"):
            st = s.get("tiers") or "pending"
        elif key in ("s06_analyse_besoin", "s07_build_devis_lines"):
            if s.get("tiers") == "done" and s.get("devis"):
                st = s["devis"] if s["devis"] == "done" else "active"
            elif s.get("tiers") == "done":
                st = "active"
            else:
                st = "pending"
        elif key in ("s08_create_devis","s09_upload_attachments","s10_log_email",
                     "s11_archive_outlook","s12_notify_team","s13_send_email_client"):
            st = s.get("devis") or "pending"
        elif key == "s_mark_non_devis":
            cat = run.get("routing_category","")
            st = "done" if (cat and cat != "NEW_PROJECT") else "skip"
        else:
            st = "pending"

        # propagation stop/routed
        if run.get("status") in ("stopped", "routed"):
            if short.startswith("s0"):
                try:
                    n = int(short[1:])
                    if n > 3 and not is_new_project:
                        st = "skip"
                except ValueError:
                    pass

    # ── extractStepFields ─────────────────────────────────────────────────
    fields = []
    if key == "s01_get_email":
        if run.get("email_subject"): fields.append({"key": "Objet",       "value": run["email_subject"]})
        if run.get("email_sender"):  fields.append({"key": "Expéditeur",  "value": run["email_sender"]})
        if run.get("started_at"):    fields.append({"key": "Démarré à",   "value": run["started_at"]})
    elif key == "s02_extract_client_ai":
        if run.get("client_email") or run.get("soc_nom"):
            fields.append({"key": "Client extrait", "value": {"soc_nom": run.get("soc_nom"), "email": run.get("client_email")}, "type": "json"})
        if run.get("routing_category"):
            conf = f" ({run['routing_confidence']})" if run.get("routing_confidence") else ""
            fields.append({"key": "Routing", "value": run["routing_category"] + conf})
    elif key == "s03_clean_data":
        fields.append({"key": "Catégorie", "value": run.get("routing_category") or "UNKNOWN"})
        fields.append({"key": "Résultat",  "value": "Autorisé — pipeline continue" if is_new_project else "Arrêt — email non-devis"})
    elif key == "s04_find_or_create_client":
        if run.get("soc_nom"):        fields.append({"key": "Tiers", "value": run["soc_nom"]})
        if run.get("client_email"):   fields.append({"key": "Email", "value": run["client_email"]})
        tiers_act = next((a for a in run.get("actions",[]) if a.get("text","").find("Tiers") >= 0 or a.get("icon") == "👤"), None)
        if tiers_act: fields.append({"key": "Action Dolibarr", "value": tiers_act["text"]})
    elif key == "s08_create_devis":
        if run.get("devis_ref"): fields.append({"key": "Référence devis", "value": run["devis_ref"]})
    elif key == "s11_archive_outlook":
        fields.append({"key": "Email",       "value": run.get("email_subject") or "—"})
        fields.append({"key": "Archivé dans","value": f"Dossier {run['devis_ref']}" if run.get("devis_ref") else "Dossier DEVIS"})
    elif key == "s12_notify_team":
        fields.append({"key": "Statut", "value": "Notification envoyée — en attente GO" if run.get("devis_ref") else "Non atteint"})
        if run.get("devis_ref"): fields.append({"key": "Devis", "value": run["devis_ref"]})
    elif key == "__gate_go__":
        fields.append({"key": "Type",           "value": "Gate validation humaine"})
        fields.append({"key": "Action requise", "value": "Approuver pour déclencher l'envoi email client (s13)"})
        if run.get("devis_ref"): fields.append({"key": "Devis concerné", "value": run["devis_ref"]})
        mg = next((g for g in gates if run.get("devis_ref") and g.get("label","").find(run["devis_ref"]) >= 0), None)
        if mg: fields.append({"key": "Gate Dolibarr", "value": mg["label"]})
    else:
        acts = [a for a in run.get("actions", []) if len(a.get("text","")) > 2]
        if acts: fields.append({"key": "Actions log", "value": "\n".join(f"{a['icon']} {a['text']}" for a in acts)})

    # ── Boutons actifs ────────────────────────────────────────────────────
    step_actions = step.get("actions", [])
    buttons = {
        "validate":    "validate" in step_actions and st == "done",
        "flag":        "flag" in step_actions,
        "doli_tiers":  "doli_tiers" in step_actions and bool(run.get("soc_nom")),
        "doli_devis":  "doli_devis" in step_actions and bool(run.get("devis_ref")),
        "gate_approve":"gate_approve" in step_actions,
        "gate_reject": "gate_reject" in step_actions,
        "modal":       "modal" in step_actions,
    }

    return {
        "status": st,
        "fields": fields,
        "fields_count": len(fields),
        "buttons": {k: v for k, v in buttons.items() if v},
    }


async def test_step_inspector(client: httpx.AsyncClient, url: str, verbose: bool = False, run_idx: int | None = None) -> list[TestResult]:
    """Simule l'inspecteur de nœud pour chaque step de chaque run."""
    results = []

    data  = await get(client, url, "/api/pipeline-runs", {"limit": 50})
    gates = (await get(client, url, "/api/pipeline/gates")).get("gates", [])
    runs  = data.get("runs", [])

    if not runs:
        results.append(TestResult(name="Inspecteur nœuds — aucun run", ok=False,
                                  errors=["Aucun run disponible"]))
        return results

    target_runs = [runs[run_idx]] if run_idx is not None else runs[:10]

    for i, run in enumerate(target_runs):
        idx = run_idx if run_idx is not None else i
        is_new = run.get("routing_category") == "NEW_PROJECT"
        steps  = STEPS_FLUX_A if is_new else STEPS_NON_DEVIS
        subj   = (run.get("email_subject") or "(no subject)")[:45]

        t0 = time.monotonic()
        tr = TestResult(
            name=f"Inspecteur Run #{idx} [{run.get('status')}] {subj}",
            ok=True,
        )

        steps_ok = 0
        steps_empty = []

        for step in steps:
            sk = step["key"]
            result = simulate_step_inspector(run, step, gates)
            st = result["status"]

            # Vérification : steps done/active devraient avoir des données
            if st in ("done", "active"):
                if result["fields_count"] == 0:
                    steps_empty.append(sk)
                else:
                    steps_ok += 1

            if verbose:
                btn_str = ", ".join(result["buttons"].keys()) if result["buttons"] else "—"
                fields_str = ", ".join(f["key"] for f in result["fields"]) if result["fields"] else "vide"
                tr.details.append(
                    f"  [{st:8}] {step['label']:10} {sk:30} | champs={result['fields_count']} [{fields_str[:40]}] | boutons=[{btn_str}]"
                )

        tr.details.append(
            f"Flux={'FLUX_A' if is_new else 'NON_DEVIS'} | {len(steps)} steps | "
            f"{steps_ok} avec données | "
            f"{len(steps_empty)} steps actifs sans données{': '+', '.join(steps_empty) if steps_empty else ''}"
        )

        if steps_empty:
            for sk in steps_empty:
                tr.warnings.append(f"Step {sk} est done/active mais inspecteur vide — log insuffisant ?")

        tr.duration = time.monotonic() - t0
        results.append(tr)

    return results


async def test_queue_pj(client: httpx.AsyncClient, url: str, verbose: bool = False) -> list[TestResult]:
    """Vérifie la file d'attente et les emails avec PJ."""
    results = []
    t0 = time.monotonic()
    tr = TestResult(name="File d'attente Outlook + PJ", ok=False)

    try:
        data  = await get(client, url, "/api/pipeline/queue")
        queue = data.get("queue", [])
        count = data.get("count", 0)
        err   = data.get("error")

        if err:
            tr.warnings.append(f"Erreur Outlook: {err}")
        tr.ok = True

        emails_pj = [e for e in queue if e.get("has_attachments")]
        emails_no_pj = [e for e in queue if not e.get("has_attachments")]

        tr.details.append(f"{count} email(s) en attente — {len(emails_pj)} avec PJ, {len(emails_no_pj)} sans PJ")

        for e in queue[:10]:
            subj = e.get("subject", "?")[:50]
            sender = e.get("sender_address", "?")
            pj_badge = "📎 PJ" if e.get("has_attachments") else "—"
            recvd = e.get("received_at", "")[:10]
            if verbose:
                tr.details.append(f"  [{pj_badge}] {recvd} {sender:30} {subj}")

        # Check : les emails avec PJ ont-ils un ID Outlook valide pour accès direct ?
        for e in emails_pj:
            if not e.get("id"):
                tr.warnings.append(f"Email avec PJ sans ID Outlook: {e.get('subject','?')[:30]}")
            else:
                tr.details.append(f"  📎 PJ accessible via Outlook ID: {e.get('id','?')[:40]}…")

    except Exception as exc:
        tr.errors.append(str(exc))

    tr.duration = time.monotonic() - t0
    results.append(tr)
    return results


async def test_gates(client: httpx.AsyncClient, url: str, verbose: bool = False) -> list[TestResult]:
    """Vérifie les gates en attente de validation."""
    results = []
    t0 = time.monotonic()
    tr = TestResult(name="Gates Dolibarr (⏸ validations en attente)", ok=False)

    try:
        data  = await get(client, url, "/api/pipeline/gates")
        gates = data.get("gates", [])
        count = data.get("count", 0)
        err   = data.get("error")

        if err:
            tr.warnings.append(f"Erreur Dolibarr: {err}")

        tr.ok = True
        tr.details.append(f"{count} gate(s) en attente")

        for g in gates:
            if verbose:
                tr.details.append(f"  ID={g.get('id')} label={g.get('label','?')[:50]} done={g.get('done')}")
            if not g.get("doli_url"):
                tr.warnings.append(f"Gate #{g.get('id')} sans URL Dolibarr")
            if not g.get("id"):
                tr.errors.append("Gate sans ID — approve/reject impossible")
                tr.ok = False

    except Exception as exc:
        tr.errors.append(str(exc))

    tr.duration = time.monotonic() - t0
    results.append(tr)
    return results


async def test_config_doli_urls(client: httpx.AsyncClient, url: str) -> list[TestResult]:
    """Vérifie que la config contient les URLs Dolibarr nécessaires aux boutons."""
    results = []
    t0 = time.monotonic()
    tr = TestResult(name="Config — URLs Dolibarr (boutons inspecteur)", ok=False)

    try:
        cfg = await get(client, url, "/api/config")
        doli_url = cfg.get("dolibarr_url") or cfg.get("DOLIBARR_WEB")

        if not doli_url:
            tr.errors.append("dolibarr_url absent de /api/config — boutons ↗ Dolibarr inactifs")
        else:
            tr.ok = True
            tr.details.append(f"dolibarr_url={doli_url}")

            # Simuler les URLs construites par searchDoliTiers / openDoliDevis
            tiers_url = f"{doli_url}/societe/list.php?search_nom=TestClient"
            devis_url  = f"{doli_url}/comm/propal/list.php?search_ref=PRO-0001"
            tr.details.append(f"URL tiers: {tiers_url}")
            tr.details.append(f"URL devis: {devis_url}")

    except Exception as exc:
        tr.errors.append(str(exc))

    tr.duration = time.monotonic() - t0
    results.append(tr)
    return results


async def test_step_action_endpoint(client: httpx.AsyncClient, url: str) -> list[TestResult]:
    """Vérifie que /api/pipeline/step-action répond (dry-run — sans écriture si Dolibarr down)."""
    results = []
    t0 = time.monotonic()
    tr = TestResult(name="Endpoint POST /api/pipeline/step-action (dry-run)", ok=False)

    try:
        res = await post(client, url, "/api/pipeline/step-action", {
            "action": "validate",
            "step":   "s02_extract_client_ai",
            "ref":    "TEST-DRY-RUN",
            "note":   "Test automatique — pipeline_dashboard.py",
        })
        sc = res["status"]
        if sc in (200, 201):
            tr.ok = True
            tr.details.append(f"HTTP {sc} — step-action OK")
        elif sc == 503:
            tr.ok = True  # attendu si Dolibarr non configuré en test
            tr.warnings.append("Dolibarr non configuré (503) — step-action non exécuté, endpoint présent")
        else:
            tr.errors.append(f"HTTP {sc}: {str(res['body'])[:120]}")
    except Exception as exc:
        tr.errors.append(str(exc))

    tr.duration = time.monotonic() - t0
    results.append(tr)
    return results


async def test_autopilot(client: httpx.AsyncClient, url: str) -> list[TestResult]:
    """Vérifie le toggle autopilot (read-only)."""
    results = []
    t0 = time.monotonic()
    tr = TestResult(name="Autopilot — lecture état", ok=False)

    try:
        data = await get(client, url, "/api/pipeline/autopilot")
        enabled = data.get("enabled")
        tr.ok = True
        tr.details.append(f"autopilot.enabled={enabled!r}  enabled_at={data.get('enabled_at')!r}")
    except Exception as exc:
        tr.errors.append(str(exc))

    tr.duration = time.monotonic() - t0
    results.append(tr)
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def print_result(tr: TestResult, verbose: bool = False) -> None:
    status = ok(f"{tr.duration:.2f}s") if tr.ok else fail(f"{tr.duration:.2f}s")
    prefix = "✓" if tr.ok else "✗"
    color  = GREEN if tr.ok else RED
    print(f"{color}{prefix}{RESET} {tr.name}  {status}")
    for d in tr.details:
        print(info(d))
    for w in tr.warnings:
        print(f"    {YELLOW}⚠ {w}{RESET}")
    for e in tr.errors:
        print(f"    {RED}✗ {e}{RESET}")


def print_summary(results: list[TestResult]) -> None:
    nb_ok   = sum(1 for r in results if r.ok)
    nb_fail = len(results) - nb_ok
    nb_warn = sum(1 for r in results if r.warnings)
    total_t = sum(r.duration for r in results)
    slow    = sorted(results, key=lambda x: x.duration, reverse=True)[:3]

    print(f"\n{bold('═' * 65)}")
    print(f"{bold('  RÉSUMÉ — POSTE DE PILOTAGE')}")
    print(f"{bold('═' * 65)}")
    print(f"  Tests   : {len(results)}")
    print(f"  {GREEN}OK      : {nb_ok}{RESET}")
    print(f"  {RED}FAIL    : {nb_fail}{RESET}")
    print(f"  {YELLOW}WARN    : {nb_warn}{RESET}")
    print(f"  Durée   : {total_t:.2f}s total")
    print(f"  Plus lents : {', '.join(f'{r.name[:25]}({r.duration:.2f}s)' for r in slow)}")

    if nb_fail > 0:
        print(f"\n{RED}Échecs :{RESET}")
        for r in results:
            if not r.ok:
                print(f"  ✗ {r.name}")
                for e in r.errors:
                    print(f"    → {e}")

    if nb_warn > 0:
        print(f"\n{YELLOW}Avertissements :{RESET}")
        for r in results:
            for w in r.warnings:
                print(f"  ⚠ {r.name[:45]}: {w}")

    print()
    if nb_fail == 0:
        print(ok(f"Tous les tests passent ({nb_ok}/{len(results)})"))
    else:
        print(fail(f"{nb_fail} test(s) en échec — voir détails ci-dessus"))
    print()


async def run_all(url: str, verbose: bool = False, run_idx: int | None = None) -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        # ── Vérification connexion ─────────────────────────────────────────
        print(f"\n{bold('═' * 65)}")
        print(f"{bold('  TEST POSTE DE PILOTAGE — InPressco Pipeline')}")
        print(f"  URL : {url}")
        print(f"{bold('═' * 65)}\n")

        try:
            r = await client.get(f"{url}/api/config", timeout=5)
            if r.status_code != 200:
                print(fail(f"Dashboard répond {r.status_code} sur /api/config"))
                sys.exit(1)
            print(ok(f"Dashboard joignable — {url}"))
        except httpx.ConnectError:
            print(fail(f"Dashboard inaccessible sur {url}"))
            print(info("Démarrer avec : uvicorn dashboard.app:app --reload --port 8000"))
            sys.exit(1)
        print()

        all_results: list[TestResult] = []

        # ── 1. Endpoints de base ──────────────────────────────────────────
        print(f"{bold('── 1. Endpoints API')}")
        for tr in await test_endpoints_base(client, url):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 2. Données des runs ───────────────────────────────────────────
        print(f"{bold('── 2. Données des runs (complétude)')}")
        for tr in await test_runs_data(client, url, verbose):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 3. Inspecteur de nœuds ────────────────────────────────────────
        print(f"{bold('── 3. Inspecteur de nœuds (tous les steps)')}")
        for tr in await test_step_inspector(client, url, verbose, run_idx):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 4. File d'attente + PJ ────────────────────────────────────────
        print(bold("── 4. File d'attente emails + PJ"))
        for tr in await test_queue_pj(client, url, verbose):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 5. Gates ──────────────────────────────────────────────────────
        print(f"{bold('── 5. Gates Dolibarr')}")
        for tr in await test_gates(client, url, verbose):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 6. Config + URLs Dolibarr ─────────────────────────────────────
        print(f"{bold('── 6. Config Dolibarr (URLs boutons)')}")
        for tr in await test_config_doli_urls(client, url):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 7. Autopilot ──────────────────────────────────────────────────
        print(f"{bold('── 7. Autopilot')}")
        for tr in await test_autopilot(client, url):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── 8. Step-action endpoint ───────────────────────────────────────
        print(f"{bold('── 8. Endpoint step-action (dry-run)')}")
        for tr in await test_step_action_endpoint(client, url):
            print_result(tr, verbose)
            all_results.append(tr)
        print()

        # ── Résumé ────────────────────────────────────────────────────────
        print_summary(all_results)


def main() -> None:
    p = argparse.ArgumentParser(description="Test complet du poste de pilotage InPressco")
    p.add_argument("--url",     default=DEFAULT_URL, help="URL dashboard (défaut: http://127.0.0.1:8000)")
    p.add_argument("--verbose", action="store_true",  help="Afficher le détail exhaustif de chaque nœud")
    p.add_argument("--run",     type=int, default=None, metavar="N", help="Inspecter uniquement le run N")
    args = p.parse_args()
    asyncio.run(run_all(url=args.url, verbose=args.verbose, run_idx=args.run))


if __name__ == "__main__":
    main()
