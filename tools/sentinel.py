"""tools/sentinel.py — Agent Sentinelle InPressco MWP.

Surveille en temps réel les modifications de fichiers Python et SKILL.md.
Vérifie automatiquement le câblage dans les modules système après chaque modification.

Checks déclenchés selon le fichier modifié :
  src/steps/**/*.py          → intégrité steps (s01→s12 présents)
  src/connectors/*.py        → connector importé dans le pipeline
  src/engine/dispatcher.py   → dispatcher couvre toutes les catégories
  .claude/skills/**/SKILL.md → skill référencé dans core/system_reference.py
  core/system_reference.py   → full verify complet requis

Plus : scan anti-patterns sur tout fichier .py modifié.
Plus : full verify périodique toutes les POLL_INTERVAL secondes (défaut 10 min).

Usage :
  python tools/sentinel.py                 # mode watch temps réel (watchdog)
  python tools/sentinel.py --poll 60       # mode polling toutes les 60s
  python tools/sentinel.py --once          # vérification unique puis exit
  python tools/sentinel.py --interval 300  # full verify périodique toutes les 5 min
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
LOG_FILE = REPORTS_DIR / "sentinel_log.json"
MAX_LOG_ENTRIES = 500
DEFAULT_FULL_VERIFY_INTERVAL = 600  # 10 minutes

# Chargement .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  SENTINEL  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sentinel")


# ── Types ─────────────────────────────────────────────────────────────────────

class SentinelAlert(NamedTuple):
    timestamp: str
    level: str      # "ok" | "warn" | "error"
    trigger: str    # chemin relatif du fichier modifié, ou "periodic"
    check: str      # nom du check
    detail: str


# ── Checks de câblage ─────────────────────────────────────────────────────────

def check_step_wiring(file: Path) -> list[str]:
    """Vérifie que tous les steps sont déclarés dans le fichier steps.py modifié."""
    violations: list[str] = []
    content = file.read_text(encoding="utf-8", errors="ignore")

    if "flux_a" in str(file):
        for i in range(1, 13):
            if f"s{i:02d}_" not in content:
                violations.append(f"flux_a/steps.py : step s{i:02d}_* manquant ou renommé")

    elif "flux_b" in str(file):
        for i in range(1, 4):
            if f"s{i:02d}_" not in content:
                violations.append(f"flux_b/steps.py : step s{i:02d}_* manquant ou renommé")

    return violations


def check_connector_wiring(file: Path) -> list[str]:
    """Vérifie qu'un connector modifié est importé quelque part dans src/."""
    violations: list[str] = []
    connector_name = file.stem  # ex: "dolibarr", "claude_client"

    src_dir = ROOT / "src"
    found = any(
        connector_name in py.read_text(encoding="utf-8", errors="ignore")
        for py in src_dir.rglob("*.py")
        if py != file
    )

    if not found:
        violations.append(
            f"connector '{connector_name}.py' non importé dans src/ — "
            "peut-être renommé ou déconnecté du pipeline"
        )
    return violations


def check_dispatcher_wiring() -> list[str]:
    """Vérifie que le dispatcher couvre les catégories de routing attendues."""
    dispatcher = ROOT / "src" / "engine" / "dispatcher.py"
    if not dispatcher.exists():
        return ["dispatcher.py introuvable"]

    content = dispatcher.read_text(encoding="utf-8", errors="ignore")
    expected = ["NEW_PROJECT", "PROJECT_UPDATE", "SUPPLIER_INVOICE", "SUPPLIER_QUOTE", "VISUAL_CREATION"]
    return [
        f"dispatcher.py : catégorie {cat!r} non couverte"
        for cat in expected
        if cat not in content
    ]


def check_skill_wiring(skill_file: Path) -> list[str]:
    """Vérifie qu'un SKILL.md modifié est référencé dans core/system_reference.py et CLAUDE.md.

    Normalise le nom : supprime le préfixe '_disabled_' avant la recherche
    (les skills désactivés restent enregistrés sans ce préfixe dans le référentiel).
    """
    violations: list[str] = []
    raw_name = skill_file.parent.name  # ex: "_disabled_notification-interne-inpressco"

    # Normalisation : supprime le préfixe _disabled_ si présent
    skill_name = raw_name.removeprefix("_disabled_")

    ref_file = ROOT / "core" / "system_reference.py"
    if ref_file.exists():
        content = ref_file.read_text(encoding="utf-8", errors="ignore")
        # Cherche nom normalisé OU nom brut
        if skill_name not in content and raw_name not in content:
            violations.append(
                f"skill '{skill_name}' absent de core/system_reference.py — "
                "SKILLS_REGISTRY à mettre à jour"
            )

    claude_md = ROOT / "CLAUDE.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8", errors="ignore")
        # Cherche nom normalisé OU nom brut (avec préfixe _disabled_)
        if skill_name not in content and raw_name not in content:
            violations.append(
                f"skill '{skill_name}' absent de CLAUDE.md — "
                "table des skills à mettre à jour"
            )

    return violations


def scan_anti_patterns_file(file: Path) -> list[str]:
    """Scanne un seul fichier .py pour les anti-patterns connus (grille architecte-ia)."""
    if not file.exists() or file.suffix != ".py":
        return []

    try:
        content = file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    rel = file.relative_to(ROOT) if file.is_relative_to(ROOT) else Path(file.name)
    patterns = [
        (r'sortfield=t\.rowid',            "P11 — sortfield Freshprocess non supporté"),
        (r'except\s*:\s*pass',             "P08 — except silencieux (données perdues)"),
        (r'DOLIBARR_API_KEY\s*=\s*["\']',  "P10 — secret Dolibarr hardcodé"),
        (r'ANTHROPIC_API_KEY\s*=\s*["\']', "P10 — secret Anthropic hardcodé"),
        (r'json\.loads\(response\)',        "P01 — json.loads sans try/except"),
    ]
    return [
        f"{desc} → {rel}"
        for regex, desc in patterns
        if re.search(regex, content)
    ]


# ── Dispatcher de checks par type de fichier ──────────────────────────────────

def run_wiring_checks(file: Path) -> list[SentinelAlert]:
    """Lance les checks pertinents selon la nature du fichier modifié."""
    alerts: list[SentinelAlert] = []
    now = datetime.now(timezone.utc).isoformat()
    rel = str(file.relative_to(ROOT)) if file.is_relative_to(ROOT) else str(file)

    def ok(check: str, detail: str) -> None:
        alerts.append(SentinelAlert(now, "ok", rel, check, detail))

    def warn(check: str, detail: str) -> None:
        alerts.append(SentinelAlert(now, "warn", rel, check, detail))

    def err(check: str, detail: str) -> None:
        alerts.append(SentinelAlert(now, "error", rel, check, detail))

    # Anti-patterns (tous les .py)
    if file.suffix == ".py":
        violations = scan_anti_patterns_file(file)
        if violations:
            for v in violations:
                err("anti_pattern", v)
        else:
            ok("anti_pattern", "Aucun anti-pattern détecté")

    # Steps flux_a ou flux_b
    if file.name == "steps.py" and "steps" in str(file):
        violations = check_step_wiring(file)
        if violations:
            for v in violations:
                err("step_wiring", v)
        else:
            ok("step_wiring", "Tous les steps sont déclarés")

    # Connectors
    if "connectors" in str(file) and file.suffix == ".py":
        violations = check_connector_wiring(file)
        if violations:
            for v in violations:
                warn("connector_wiring", v)
        else:
            ok("connector_wiring", f"Connector '{file.stem}' correctement importé")

    # Dispatcher
    if "dispatcher" in file.name and file.suffix == ".py":
        violations = check_dispatcher_wiring()
        if violations:
            for v in violations:
                warn("dispatcher_wiring", v)
        else:
            ok("dispatcher_wiring", "Dispatcher couvre toutes les catégories")

    # Dashboard : app.py ou index.html modifié → alerter pour re-vérifier les contrats widgets
    if file.name in ("app.py", "index.html") and "dashboard" in str(file):
        warn("dashboard_wiring_needed",
             f"{file.name} dashboard modifié → vérifier les contrats widgets : "
             "python tools/sentinel.py --check-dashboard ou --once")

    # SKILL.md
    if file.name == "SKILL.md":
        violations = check_skill_wiring(file)
        if violations:
            for v in violations:
                warn("skill_wiring", v)
        else:
            ok("skill_wiring", f"Skill '{file.parent.name}' correctement référencé")

    # system_reference.py modifié → full verify recommandé
    if "system_reference" in file.name:
        warn("full_verify_needed",
             "core/system_reference.py modifié → relancer python main.py --verify")

    return alerts


# ── Log JSON ──────────────────────────────────────────────────────────────────

def append_to_log(alerts: list[SentinelAlert]) -> None:
    """Ajoute les alertes au sentinel_log.json (rotation à MAX_LOG_ENTRIES)."""
    REPORTS_DIR.mkdir(exist_ok=True)
    existing: list[dict] = []
    if LOG_FILE.exists():
        try:
            existing = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    for a in alerts:
        existing.append({
            "timestamp": a.timestamp,
            "level":     a.level,
            "trigger":   a.trigger,
            "check":     a.check,
            "detail":    a.detail,
        })

    if len(existing) > MAX_LOG_ENTRIES:
        existing = existing[-MAX_LOG_ENTRIES:]

    LOG_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_alerts(alerts: list[SentinelAlert], trigger: str = "") -> None:
    """Affiche les alertes dans la console avec icônes."""
    errors = [a for a in alerts if a.level == "error"]
    warns  = [a for a in alerts if a.level == "warn"]
    oks    = [a for a in alerts if a.level == "ok"]

    for a in errors:
        logger.error(f"❌ [{a.check}] {a.detail}")
    for a in warns:
        logger.warning(f"⚠️  [{a.check}] {a.detail}")
    if oks and not errors and not warns:
        checks_str = ", ".join(dict.fromkeys(a.check for a in oks))
        label = trigger or (oks[0].trigger if oks else "")
        logger.info(f"✅ {label} — OK ({checks_str})")


# ── Full verify périodique ────────────────────────────────────────────────────

async def periodic_full_verify(interval: int) -> None:
    """Lance system_verify toutes les `interval` secondes en tâche de fond."""
    sys.path.insert(0, str(ROOT))
    from tools.system_verify import run_verify  # import local pour éviter la circularité

    while True:
        await asyncio.sleep(interval)
        logger.info("⏱  Full verify périodique...")
        try:
            report = await run_verify()
            score   = report["score"]
            overall = report["overall"]
            icon    = "✅" if overall == "healthy" else "⚠️" if overall == "degraded" else "🔴"
            logger.info(f"{icon} Full verify — {overall.upper()} score {score}/100")

            if score < 70:
                now    = datetime.now(timezone.utc).isoformat()
                alerts = [SentinelAlert(
                    now, "error", "periodic", "full_verify",
                    f"Système {overall.upper()} — score {score}/100"
                )]
                for c in report["checks"]:
                    if c["status"] != "ok":
                        alerts.append(SentinelAlert(
                            now, c["status"], "periodic", c["name"], c["detail"]
                        ))
                append_to_log(alerts)
                print_alerts(alerts, trigger="periodic")

        except Exception as e:
            logger.error(f"Erreur full verify périodique : {e}")


# ── Contrats de câblage widgets dashboard ────────────────────────────────────
#
# Source de vérité : pour chaque endpoint, quels champs JSON le frontend consomme
# et quels champs sont retournés par le backend mais jamais affichés (orphelins).
# Mise à jour obligatoire dès que app.py ou index.html évolue.

WIDGET_CONTRACTS: list[dict] = [
    {
        "widget":       "Stats opérationnelles",
        "endpoint":     "/api/stats",
        "js_consumes":  {
            "devis_semaine":   ["nb", "total_ht"],
            "devis_brouillon": ["nb", "total_ht"],
            "cmds_semaine":    ["nb", "total_ht"],
            "cmds_bloque":     ["nb", "total_ht"],
            "cmds_fichiers":   ["nb", "total_ht"],
            "cmds_en_prod":    ["nb"],
            "cmds_bat":        ["nb", "total_ht"],
            "doli_web":        [],
        },
        "backend_orphans": [],
    },
    {
        "widget":      "KPIs Financiers",
        "endpoint":    "/api/kpis",
        "js_consumes": {
            "ca":                   ["mois_en_cours_ht", "mois_precedent_ht", "evolution_pct"],
            "taux_transfo":         ["pct", "nb_signes", "nb_total"],
            "rentabilite":          ["ht", "ca_ht", "cout_four_ht"],
            "impayes_clients":      ["total_ht", "nb"],
            "impayes_fournisseurs": ["total_ht", "nb"],
            "doli_web":             [],
        },
        # cmds_non_facturees et devis_ouverts sont retournés mais jamais lus par le JS KPIs
        # (cmds_non_facturees est lu depuis /api/daf ; devis_ouverts non affiché)
        "backend_orphans": ["cmds_non_facturees", "devis_ouverts"],
    },
    {
        "widget":      "DAF",
        "endpoint":    "/api/daf",
        "js_consumes": {
            "ca_annee_ht":       [],
            "dso_jours":         [],
            "previsionnel_30j":  [],
            "top_clients":       [],
            "top_produits":      [],
            "cmds_non_facturees": ["nb", "total_ht"],
            "encours":           ["courant", "retard_30j", "retard_60j", "retard_90j_plus"],
            "generated_at":      [],
        },
        "backend_orphans": [],
    },
    {
        "widget":      "Graphique CA mensuel",
        "endpoint":    "/api/ca-chart",
        "js_consumes": {
            "years":        [],
            "current_year": [],
            "generated_at": [],
        },
        "backend_orphans": [],
    },
    {
        "widget":      "Devis à suivre",
        "endpoint":    "/api/devis-suivre",
        "js_consumes": {
            "devis":        [],
            "nb":           [],
            "doli_web":     [],
            "generated_at": [],
        },
        "backend_orphans": [],
        # devis[].jours_ecoul, url, pdf_url, project_name, montant, client, ref vérifiés en live
        "devis_item_fields": ["ref", "client", "project_name", "montant", "date_ts",
                              "jours_ecoul", "url", "pdf_url"],
    },
    {
        "widget":      "Pipeline Queue",
        "endpoint":    "/api/pipeline-runs",
        "js_consumes": {
            "runs":  [],
            "total": [],
        },
        "backend_orphans": [],
        "run_item_fields": ["status", "email_subject", "email_sender", "routing_category",
                            "duration_s", "steps", "actions", "stop_reason"],
    },
    {
        "widget":      "Sélecteur upload assets",
        "endpoint":    "/api/proposals-orders",
        "js_consumes": {
            "devis":     [],
            "commandes": [],
        },
        "backend_orphans": [],
    },
]


async def check_dashboard_widget_wiring(
    dashboard_base: str = "http://127.0.0.1:8080",
) -> list[SentinelAlert]:
    """Vérifie le câblage de chaque widget : appelle l'endpoint, valide la structure JSON.

    Pour chaque contrat WIDGET_CONTRACTS :
      1. Appel HTTP live de l'endpoint
      2. Vérification que chaque clé js_consumes est présente dans la réponse
      3. Pour les clés imbriquées, vérification des sous-champs
      4. Signalement des orphelins backend (retournés mais non consommés par le JS)
    """
    try:
        import httpx as _httpx
    except ImportError:
        return [SentinelAlert(
            datetime.now(timezone.utc).isoformat(), "warn",
            "dashboard_wiring", "import", "httpx non disponible — check ignoré"
        )]

    alerts: list[SentinelAlert] = []
    now = datetime.now(timezone.utc).isoformat()

    # Vérifier d'abord que le dashboard répond
    try:
        async with _httpx.AsyncClient(timeout=5) as c:
            probe = await c.get(f"{dashboard_base}/api/config")
        if probe.status_code != 200:
            return [SentinelAlert(now, "warn", "dashboard_wiring", "connectivity",
                                  f"Dashboard non joignable sur {dashboard_base} — check ignoré")]
    except Exception:
        return [SentinelAlert(now, "warn", "dashboard_wiring", "connectivity",
                              f"Dashboard non démarré sur {dashboard_base} — check ignoré")]

    # Endpoints lourds (pagination Dolibarr) peuvent dépasser 30s
    _ENDPOINT_TIMEOUTS = {"/api/kpis": 60, "/api/daf": 60, "/api/ca-chart": 30}

    async def _get(path: str):
        timeout = _ENDPOINT_TIMEOUTS.get(path, 15)
        try:
            async with _httpx.AsyncClient(timeout=timeout) as c:
                r = await c.get(f"{dashboard_base}{path}")
                if r.status_code == 200:
                    return r.json()
                return None
        except Exception:
            return None

    def _check_fields(data: dict, fields: list[str], prefix: str) -> list[str]:
        """Vérifie que les sous-champs sont présents dans un objet."""
        missing = []
        for f in fields:
            if f not in data:
                missing.append(f"{prefix}.{f}")
        return missing

    for contract in WIDGET_CONTRACTS:
        endpoint = contract["endpoint"]
        widget   = contract["widget"]
        trigger  = f"{widget} ({endpoint})"

        data = await _get(endpoint)
        if data is None:
            alerts.append(SentinelAlert(now, "warn", trigger, "endpoint",
                                        f"Endpoint {endpoint} ne répond pas ou retourne une erreur"))
            continue

        # Vérifier les champs de premier niveau
        for key, subfields in contract["js_consumes"].items():
            if key not in data:
                alerts.append(SentinelAlert(now, "error", trigger, "field_missing",
                                            f"Champ '{key}' attendu par le JS absent de la réponse"))
                continue

            # Vérifier les sous-champs si spécifiés
            if subfields and isinstance(data[key], dict):
                missing = _check_fields(data[key], subfields, key)
                for m in missing:
                    alerts.append(SentinelAlert(now, "error", trigger, "subfield_missing",
                                                f"Sous-champ '{m}' attendu par le JS absent"))

        # Vérifier les orphelins backend (retournés mais non utilisés par JS)
        for orphan in contract.get("backend_orphans", []):
            if orphan in data:
                alerts.append(SentinelAlert(now, "warn", trigger, "backend_orphan",
                                            f"'{orphan}' retourné par {endpoint} mais jamais consommé par le JS"))

        # Vérifier les champs d'un item de liste (devis, runs)
        if "devis_item_fields" in contract:
            devis_list = data.get("devis") or []
            if devis_list and isinstance(devis_list[0], dict):
                missing = _check_fields(devis_list[0], contract["devis_item_fields"], "devis[0]")
                for m in missing:
                    alerts.append(SentinelAlert(now, "error", trigger, "item_field_missing",
                                                f"Champ '{m}' attendu dans chaque devis absent"))

        if "run_item_fields" in contract:
            runs = data.get("runs") or []
            if runs and isinstance(runs[0], dict):
                missing = _check_fields(runs[0], contract["run_item_fields"], "runs[0]")
                for m in missing:
                    alerts.append(SentinelAlert(now, "error", trigger, "item_field_missing",
                                                f"Champ '{m}' attendu dans chaque run absent"))

        if not any(a.trigger == trigger and a.level in ("error", "warn") for a in alerts):
            alerts.append(SentinelAlert(now, "ok", trigger, "widget_wiring",
                                        f"Widget '{widget}' — câblage JSON vérifié"))

    return alerts


# ── Filtrage des fichiers surveillés ─────────────────────────────────────────

_IGNORE_PATTERNS = [
    "__pycache__", ".pyc", ".DS_Store",
    "sentinel_log", "health_report", "DASHBOARD_REPORT",
    "SYSTEM_REPORT", "STRATEGIC_SYNTHESIS", "intent_log",
    ".git/",
]

_WATCH_DIRS = ["src", "tools", "core", ".claude/skills", "dashboard"]


def _is_relevant(file: Path) -> bool:
    rel = str(file)
    if any(p in rel for p in _IGNORE_PATTERNS):
        return False
    is_py_in_scope = (
        file.suffix == ".py"
        and any(d in rel for d in ["/src/", "/tools/", "/core/", "/dashboard/"])
    )
    is_skill_md   = file.name == "SKILL.md"
    is_dashboard_html = file.name == "index.html" and "dashboard" in rel
    return is_py_in_scope or is_skill_md or is_dashboard_html


def _process_changed_file(file_path: str) -> None:
    """Point d'entrée commun pour watchdog et polling."""
    file = Path(file_path)
    if not _is_relevant(file):
        return

    rel = str(file.relative_to(ROOT)) if file.is_relative_to(ROOT) else file.name
    logger.info(f"📁 Modification : {rel}")

    alerts = run_wiring_checks(file)
    print_alerts(alerts, trigger=rel)
    append_to_log(alerts)


# ── Mode watchdog ─────────────────────────────────────────────────────────────

def run_watchdog_mode(full_verify_interval: int) -> None:
    """Mode watchdog temps réel — utilise la bibliothèque watchdog."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory:
                    _process_changed_file(event.src_path)
            def on_created(self, event):
                if not event.is_directory:
                    _process_changed_file(event.src_path)

        observer = Observer()
        for d in _WATCH_DIRS:
            watch_path = ROOT / d
            if watch_path.exists():
                observer.schedule(_Handler(), str(watch_path), recursive=True)
                logger.info(f"  Surveillance → {d}/")

        observer.start()
        logger.info("✅ Watchdog démarré — Ctrl+C pour arrêter")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(periodic_full_verify(full_verify_interval))
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            loop.close()

    except ImportError:
        logger.warning("watchdog non installé → pip install watchdog")
        logger.warning("Passage en mode polling (60s)...")
        run_polling_mode(interval=60, full_verify_interval=full_verify_interval)


# ── Mode polling ─────────────────────────────────────────────────────────────

def run_polling_mode(interval: int, full_verify_interval: int = DEFAULT_FULL_VERIFY_INTERVAL) -> None:
    """Mode polling — re-vérifie les mtimes toutes les `interval` secondes."""
    logger.info(f"✅ Mode polling — vérification toutes les {interval}s")

    def _snapshot() -> dict[Path, float]:
        snap: dict[Path, float] = {}
        for d in _WATCH_DIRS:
            watch_path = ROOT / d
            if not watch_path.exists():
                continue
            for f in watch_path.rglob("*"):
                if f.is_file() and (f.suffix == ".py" or f.name == "SKILL.md"
                                    or (f.name == "index.html" and "dashboard" in str(f))):
                    try:
                        snap[f] = f.stat().st_mtime
                    except Exception:
                        pass
        return snap

    watched = _snapshot()
    logger.info(f"  {len(watched)} fichiers surveillés")

    last_full_verify = time.monotonic()

    try:
        while True:
            time.sleep(interval)

            new_snap = _snapshot()
            for f, mtime in new_snap.items():
                if f not in watched or watched[f] != mtime:
                    _process_changed_file(str(f))
            watched = new_snap

            # Full verify périodique
            elapsed = time.monotonic() - last_full_verify
            if elapsed >= full_verify_interval:
                logger.info("⏱  Full verify périodique...")
                try:
                    sys.path.insert(0, str(ROOT))
                    from tools.system_verify import run_verify
                    report = asyncio.run(run_verify())
                    score   = report["score"]
                    overall = report["overall"]
                    icon    = "✅" if overall == "healthy" else "⚠️" if overall == "degraded" else "🔴"
                    logger.info(f"{icon} Full verify — {overall.upper()} score {score}/100")
                except Exception as e:
                    logger.error(f"Erreur full verify : {e}")
                last_full_verify = time.monotonic()

    except KeyboardInterrupt:
        logger.info("Sentinel arrêté.")


# ── Mode once ─────────────────────────────────────────────────────────────────

async def run_once_mode() -> None:
    """Vérification complète unique : system_verify + câblage de tous les skills."""
    sys.path.insert(0, str(ROOT))
    from tools.system_verify import run_verify

    logger.info("Mode --once : vérification complète du câblage système...")

    report = await run_verify()
    score   = report["score"]
    overall = report["overall"]
    icon    = "✅" if overall == "healthy" else "⚠️" if overall == "degraded" else "🔴"

    print(f"\n{icon} Système {overall.upper()} — score {score}/100")
    for c in report["checks"]:
        ci = "✅" if c["status"] == "ok" else "⚠️" if c["status"] == "warn" else "❌"
        print(f"   {ci} {c['name']:20s} {c['detail']}")

    # Vérification câblage de tous les skills installés
    skills_dir = ROOT / ".claude" / "skills"
    skill_alerts: list[SentinelAlert] = []
    skill_count = 0
    if skills_dir.exists():
        for skill_md in skills_dir.glob("*/SKILL.md"):
            skill_count += 1
            for v in check_skill_wiring(skill_md):
                now = datetime.now(timezone.utc).isoformat()
                skill_alerts.append(SentinelAlert(
                    now, "warn", skill_md.parent.name, "skill_wiring", v
                ))

    if skill_alerts:
        print(f"\n⚠️  Skills non câblés ({len(skill_alerts)} / {skill_count}) :")
        for a in skill_alerts:
            print(f"   · [{a.trigger}] {a.detail}")
    elif skill_count > 0:
        print(f"\n✅ {skill_count} skills vérifiés — câblage OK")

    # Anti-patterns
    anti_patterns = report.get("anti_pattern_violations", [])
    if anti_patterns:
        print(f"\n❌ Anti-patterns ({len(anti_patterns)}) :")
        for v in anti_patterns:
            print(f"   · {v}")

    # Pipeline integrity
    integrity = report.get("pipeline_integrity", {})
    if not integrity.get("ok"):
        print(f"\n❌ Intégrité pipeline :")
        for v in integrity.get("violations", []):
            print(f"   · {v}")

    # Vérification câblage widgets dashboard (si dashboard démarré)
    dashboard_base = "http://127.0.0.1:8080"
    widget_alerts = await check_dashboard_widget_wiring(dashboard_base)
    w_errors  = [a for a in widget_alerts if a.level == "error"]
    w_warns   = [a for a in widget_alerts if a.level == "warn" and "non démarré" not in a.detail and "non joignable" not in a.detail]
    w_oks     = [a for a in widget_alerts if a.level == "ok"]
    w_skipped = any("non démarré" in a.detail or "non joignable" in a.detail for a in widget_alerts)

    if w_skipped:
        print("\n⏸  Dashboard non démarré — check widgets ignoré (démarrer avec uvicorn)")
    elif w_errors:
        print(f"\n❌ Widgets dashboard — {len(w_errors)} incohérence(s) :")
        for a in w_errors:
            print(f"   · [{a.trigger}] {a.detail}")
    elif w_warns:
        print(f"\n⚠️  Widgets dashboard — {len(w_warns)} avertissement(s) :")
        for a in w_warns:
            print(f"   · [{a.trigger}] {a.detail}")
    else:
        print(f"\n✅ {len(w_oks)} widgets dashboard vérifiés — câblage JSON OK")

    print()
    sys.exit(0 if overall == "healthy" and not skill_alerts and not w_errors else 1)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent Sentinelle InPressco — surveillance et câblage système",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python tools/sentinel.py                  # watch temps réel (nécessite watchdog)\n"
            "  python tools/sentinel.py --poll 60        # polling toutes les 60s\n"
            "  python tools/sentinel.py --once           # vérification unique puis exit\n"
            "  python tools/sentinel.py --interval 300   # full verify périodique toutes les 5 min\n"
        ),
    )
    parser.add_argument("--once",     action="store_true",
                        help="Vérification unique puis exit (idéal pre-commit ou CI)")
    parser.add_argument("--poll",     type=int, metavar="SEC",
                        help="Mode polling manuel — intervalle en secondes")
    parser.add_argument("--interval", type=int, default=DEFAULT_FULL_VERIFY_INTERVAL,
                        help=f"Intervalle full verify périodique en secondes (défaut: {DEFAULT_FULL_VERIFY_INTERVAL})")
    args = parser.parse_args()

    REPORTS_DIR.mkdir(exist_ok=True)
    sys.path.insert(0, str(ROOT))

    logger.info("═" * 55)
    logger.info("  Agent Sentinelle InPressco MWP")
    logger.info(f"  Root    : {ROOT}")
    logger.info(f"  Log     : reports/sentinel_log.json")
    logger.info(f"  Surveille : {', '.join(_WATCH_DIRS)}")
    logger.info("═" * 55)

    if args.once:
        asyncio.run(run_once_mode())
    elif args.poll:
        run_polling_mode(interval=args.poll, full_verify_interval=args.interval)
    else:
        run_watchdog_mode(full_verify_interval=args.interval)
