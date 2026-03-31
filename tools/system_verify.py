"""tools/system_verify.py — Vérification masquée du système InPressco.

Lance une batterie de checks en parallèle :
  - Connexions API (Dolibarr, Claude/Anthropic, Outlook)
  - Intégrité du pipeline (steps, I/O, gates)
  - Couverture des skills vs référentiel
  - Détection d'anti-patterns dans le code src/

Usage :
  python main.py --verify                     # rapport JSON → reports/health_report.json
  python tools/system_verify.py --verbose     # affiche le rapport complet
  python tools/system_verify.py              # sortie silencieuse, exit 0/1
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"

# Chargement .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


# ── Types ──────────────────────────────────────────────────────────────────

class CheckResult(TypedDict):
    name:       str
    status:     str       # "ok" | "warn" | "error"
    detail:     str
    latency_ms: float | None


class HealthReport(TypedDict):
    generated_at:          str
    overall:               str    # "healthy" | "degraded" | "critical"
    score:                 int    # 0-100
    checks:                list[CheckResult]
    skill_coverage:        dict
    pipeline_integrity:    dict
    anti_pattern_violations: list[str]


# ── Checks API ─────────────────────────────────────────────────────────────

async def check_dolibarr() -> CheckResult:
    """GET /status sur Dolibarr — mesure latence."""
    base = os.environ.get("DOLIBARR_BASE_URL", "")
    key  = os.environ.get("DOLIBARR_API_KEY", "")
    if not base or not key:
        return CheckResult(name="dolibarr", status="warn",
                           detail="DOLIBARR_BASE_URL ou DOLIBARR_API_KEY manquant", latency_ms=None)
    try:
        import httpx
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{base}/status",
                headers={"DOLAPIKEY": key, "Accept": "application/json"},
            )
        latency = (time.monotonic() - t0) * 1000
        if r.status_code == 200:
            return CheckResult(name="dolibarr", status="ok",
                               detail=f"HTTP 200 en {latency:.0f}ms", latency_ms=latency)
        return CheckResult(name="dolibarr", status="error",
                           detail=f"HTTP {r.status_code}", latency_ms=latency)
    except Exception as e:
        return CheckResult(name="dolibarr", status="error",
                           detail=str(e)[:120], latency_ms=None)


async def check_claude_api() -> CheckResult:
    """Probe minimal Anthropic API — 1 token."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return CheckResult(name="claude_api", status="warn",
                           detail="ANTHROPIC_API_KEY manquant", latency_ms=None)
    try:
        import httpx
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         key,
                    "anthropic-version": "2023-06-01",
                    "content-type":      "application/json",
                },
                json={
                    "model":      "claude-haiku-4-5-20251001",
                    "max_tokens": 1,
                    "messages":   [{"role": "user", "content": "ping"}],
                },
            )
        latency = (time.monotonic() - t0) * 1000
        if r.status_code in (200, 201):
            return CheckResult(name="claude_api", status="ok",
                               detail=f"HTTP {r.status_code} en {latency:.0f}ms", latency_ms=latency)
        return CheckResult(name="claude_api", status="error",
                           detail=f"HTTP {r.status_code}: {r.text[:80]}", latency_ms=latency)
    except Exception as e:
        return CheckResult(name="claude_api", status="error",
                           detail=str(e)[:120], latency_ms=None)


async def check_outlook() -> CheckResult:
    """Vérifie la présence des credentials Azure AD (sans appel Graph)."""
    tenant = os.environ.get("OUTLOOK_TENANT_ID", "")
    client = os.environ.get("OUTLOOK_CLIENT_ID", "")
    secret = os.environ.get("OUTLOOK_CLIENT_SECRET", "")
    if not all([tenant, client, secret]):
        missing = [k for k, v in [
            ("TENANT_ID", tenant), ("CLIENT_ID", client), ("CLIENT_SECRET", secret)
        ] if not v]
        return CheckResult(name="outlook", status="warn",
                           detail=f"Azure AD credentials manquants : {', '.join(missing)}",
                           latency_ms=None)

    # Tente l'acquisition d'un token MSAL
    try:
        import httpx
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     client,
                    "client_secret": secret,
                    "scope":         "https://graph.microsoft.com/.default",
                },
            )
        latency = (time.monotonic() - t0) * 1000
        if r.status_code == 200:
            return CheckResult(name="outlook", status="ok",
                               detail=f"Token Azure OK en {latency:.0f}ms", latency_ms=latency)
        return CheckResult(name="outlook", status="error",
                           detail=f"Azure token HTTP {r.status_code}: {r.text[:80]}",
                           latency_ms=latency)
    except Exception as e:
        return CheckResult(name="outlook", status="error",
                           detail=str(e)[:120], latency_ms=None)


# ── Checks pipeline & skills ───────────────────────────────────────────────

def check_pipeline_integrity() -> dict:
    """Vérifie l'existence des fichiers steps et leur importabilité."""
    violations: list[str] = []

    steps_flux_a = ROOT / "src" / "steps" / "flux_a" / "steps.py"
    steps_flux_b = ROOT / "src" / "steps" / "flux_b" / "steps.py"
    dispatcher   = ROOT / "src" / "engine" / "dispatcher.py"
    pipeline_mw  = ROOT / "src" / "middleware" / "pipeline.py"
    context_mw   = ROOT / "src" / "middleware" / "context.py"

    required_files = {
        "steps/flux_a/steps.py":    steps_flux_a,
        "steps/flux_b/steps.py":    steps_flux_b,
        "engine/dispatcher.py":     dispatcher,
        "middleware/pipeline.py":   pipeline_mw,
        "middleware/context.py":    context_mw,
    }
    for label, path in required_files.items():
        if not path.exists():
            violations.append(f"FICHIER MANQUANT : {label}")

    # Vérifie que chaque step s01→s12 est déclaré dans flux_a/steps.py
    if steps_flux_a.exists():
        content = steps_flux_a.read_text(encoding="utf-8")
        for i in range(1, 13):
            fn = f"s{i:02d}_"
            if fn not in content:
                violations.append(f"Step flux_a manquant ou renommé : {fn}*")

    # Vérifie les connectors
    for connector in ["dolibarr.py", "outlook.py", "claude_client.py"]:
        path = ROOT / "src" / "connectors" / connector
        if not path.exists():
            violations.append(f"CONNECTOR MANQUANT : {connector}")

    return {
        "ok":         len(violations) == 0,
        "violations": violations,
    }


def check_skill_coverage() -> dict:
    """Compare les skills référencés dans core/ contre les fichiers .md installés."""
    try:
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        from core import SKILLS_REGISTRY
    except ImportError:
        return {"total": 0, "implemented": 0, "missing": ["core/ non importable"]}

    # Les skills Claude Code sont dans settings.json (clé "skills")
    # ou dans des répertoires .md selon la version
    home = Path.home()
    settings_file = home / ".claude" / "settings.json"
    installed_names: set[str] = set()

    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            skills_cfg = settings.get("skills", {})
            if isinstance(skills_cfg, dict):
                installed_names.update(skills_cfg.keys())
            elif isinstance(skills_cfg, list):
                installed_names.update(skills_cfg)
        except Exception:
            pass

    # Fallback : chercher dans les répertoires .md
    for candidate in [
        home / ".claude" / "skills",
        home / ".claude" / "user",
        ROOT / ".claude" / "skills",
    ]:
        if candidate.exists():
            for f in candidate.rglob("*.md"):
                installed_names.add(f.stem)

    reference_names = set(SKILLS_REGISTRY.keys())
    missing = sorted(reference_names - installed_names)

    return {
        "total":       len(reference_names),
        "implemented": len(reference_names) - len(missing),
        "missing":     missing,
        "source":      str(settings_file) if settings_file.exists() else "répertoires .md",
    }


def detect_anti_pattern_violations() -> list[str]:
    """Scanne src/ pour des signatures d'anti-patterns connus."""
    violations: list[str] = []
    src_dir = ROOT / "src"
    if not src_dir.exists():
        return ["src/ introuvable"]

    # Anti-patterns à détecter (pattern_regex, description)
    patterns = [
        (r'sortfield=t\.rowid',           "P11 — sortfield=t.rowid non supporté Freshprocess"),
        (r'except\s*:\s*pass',            "P08 — except silencieux (données perdues silencieusement)"),
        (r'DOLIBARR_API_KEY\s*=\s*["\']', "P10 — Secret hardcodé en dur"),
        (r'ANTHROPIC_API_KEY\s*=\s*["\']',"P10 — Secret hardcodé en dur"),
        (r'json\.loads\(response\)',       "P01 — json.loads direct sans try/except"),
    ]

    for py_file in src_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for regex, desc in patterns:
            if re.search(regex, content):
                rel = py_file.relative_to(ROOT)
                violations.append(f"{desc} → {rel}")

    return violations


# ── Score & rapport ────────────────────────────────────────────────────────

def _compute_score(checks: list[CheckResult], integrity: dict, anti_patterns: list[str]) -> int:
    base = 100
    for c in checks:
        if c["status"] == "error":
            base -= 20
        elif c["status"] == "warn":
            base -= 5
    base -= len(integrity.get("violations", [])) * 10
    base -= len(anti_patterns) * 3
    return max(0, min(100, base))


def _overall(score: int) -> str:
    if score >= 70:
        return "healthy"
    if score >= 40:
        return "degraded"
    return "critical"


# ── Check dashboard (optionnel) ────────────────────────────────────────────

async def check_dashboard_health(base: str = "http://127.0.0.1:8080") -> CheckResult:
    """Teste la disponibilité du dashboard et retourne un CheckResult."""
    try:
        import httpx
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base}/api/config")
        latency = (time.monotonic() - t0) * 1000
        if r.status_code == 200:
            return CheckResult(name="dashboard", status="ok",
                               detail=f"HTTP 200 en {latency:.0f}ms", latency_ms=latency)
        return CheckResult(name="dashboard", status="warn",
                           detail=f"HTTP {r.status_code}", latency_ms=latency)
    except Exception as e:
        return CheckResult(name="dashboard", status="warn",
                           detail=f"Dashboard non démarré ({str(e)[:60]})", latency_ms=None)


# ── Point d'entrée principal ───────────────────────────────────────────────

async def run_verify(
    output_path: Path | None = None,
    check_dashboard: bool = False,
    dashboard_base: str = "http://127.0.0.1:8080",
) -> HealthReport:
    """Lance tous les checks en parallèle et produit un HealthReport."""
    REPORTS_DIR.mkdir(exist_ok=True)
    if output_path is None:
        output_path = REPORTS_DIR / "health_report.json"

    # Checks API en parallèle (dashboard optionnel)
    coros = [check_dolibarr(), check_claude_api(), check_outlook()]
    if check_dashboard:
        coros.append(check_dashboard_health(dashboard_base))

    api_results = await asyncio.gather(*coros, return_exceptions=True)
    checks: list[CheckResult] = []
    for r in api_results:
        if isinstance(r, Exception):
            checks.append(CheckResult(name="unknown", status="error",
                                      detail=str(r)[:120], latency_ms=None))
        else:
            checks.append(r)

    # Checks synchrones
    integrity     = check_pipeline_integrity()
    skill_cov     = check_skill_coverage()
    anti_patterns = detect_anti_pattern_violations()

    score   = _compute_score(checks, integrity, anti_patterns)
    overall = _overall(score)

    report = HealthReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        overall=overall,
        score=score,
        checks=checks,
        skill_coverage=skill_cov,
        pipeline_integrity=integrity,
        anti_pattern_violations=anti_patterns,
    )

    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return report


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vérification système InPressco")
    parser.add_argument("--output",  default=str(REPORTS_DIR / "health_report.json"))
    parser.add_argument("--verbose", action="store_true", help="Affiche le rapport complet")
    args = parser.parse_args()

    report = asyncio.run(run_verify(Path(args.output)))

    if args.verbose:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        score   = report["score"]
        overall = report["overall"]
        emoji   = "✅" if overall == "healthy" else "⚠️" if overall == "degraded" else "🔴"
        print(f"{emoji} Système {overall.upper()} — score {score}/100 → {args.output}")
        for c in report["checks"]:
            icon = "✅" if c["status"] == "ok" else "⚠️" if c["status"] == "warn" else "❌"
            print(f"   {icon} {c['name']:15s} {c['detail']}")
        viol = report["anti_pattern_violations"]
        if viol:
            print(f"\n⚠️  Anti-patterns détectés ({len(viol)}) :")
            for v in viol:
                print(f"   · {v}")

    sys.exit(0 if report["overall"] == "healthy" else 1)
