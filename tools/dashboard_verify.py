"""tools/dashboard_verify.py — Autotest et correctifs du dashboard InPressco.

Teste tous les endpoints GET du dashboard en parallèle :
  - Disponibilité (HTTP 2xx)
  - Validité JSON
  - Présence des champs obligatoires
  - Latence (seuils par endpoint)
  - Cohérence des données (valeurs null, zéro suspect, structure manquante)

Génère :
  - reports/dashboard_report.json  — données brutes
  - reports/DASHBOARD_REPORT.md    — rapport lisible
  - Suggestions de correctifs inline (sans modifier le code)

Usage :
  python main.py --check-dashboard            # teste dashboard sur localhost:8080
  python tools/dashboard_verify.py            # idem, sortie verbose
  python tools/dashboard_verify.py --port 8080 --start-if-down
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

ROOT        = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

DEFAULT_PORT = 8080
DEFAULT_BASE = f"http://127.0.0.1:{DEFAULT_PORT}"


# ─────────────────────────────────────────────────────────────────────────────
# SPECS DES ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

class EndpointSpec(TypedDict):
    path:            str
    method:          str
    required_keys:   list[str]        # clés JSON obligatoires dans la réponse
    latency_warn_ms: int              # seuil avertissement
    latency_err_ms:  int              # seuil erreur
    nullable_ok:     list[str]        # champs autorisés à être null/vide
    critical:        bool             # si True → impact utilisateur direct


ENDPOINT_SPECS: list[EndpointSpec] = [
    {
        "path": "/api/status",
        "method": "GET",
        "required_keys": ["summary", "stages"],
        "latency_warn_ms": 500, "latency_err_ms": 2000,
        "nullable_ok": ["summary"],
        "critical": True,
    },
    {
        "path": "/api/log",
        "method": "GET",
        "required_keys": ["lines", "total"],
        "latency_warn_ms": 300, "latency_err_ms": 1000,
        "nullable_ok": [],
        "critical": False,
    },
    {
        "path": "/api/runs",
        "method": "GET",
        "required_keys": ["runs"],
        "latency_warn_ms": 500, "latency_err_ms": 2000,
        "nullable_ok": ["runs"],
        "critical": False,
    },
    {
        "path": "/api/kpis",
        "method": "GET",
        "required_keys": ["ca", "generated_at"],
        "latency_warn_ms": 8000, "latency_err_ms": 20000,
        "nullable_ok": [],
        "critical": True,
    },
    {
        "path": "/api/stats",
        "method": "GET",
        "required_keys": ["devis_semaine", "devis_brouillon"],
        "latency_warn_ms": 3000, "latency_err_ms": 8000,
        "nullable_ok": [],
        "critical": True,
    },
    {
        "path": "/api/daf",
        "method": "GET",
        "required_keys": ["dso_jours", "encours"],
        "latency_warn_ms": 5000, "latency_err_ms": 12000,
        "nullable_ok": ["dso_jours"],
        "critical": True,
    },
    {
        "path": "/api/ca-chart",
        "method": "GET",
        "required_keys": ["years", "current_year"],
        "latency_warn_ms": 5000, "latency_err_ms": 12000,
        "nullable_ok": [],
        "critical": False,
    },
    {
        "path": "/api/clients",
        "method": "GET",
        "required_keys": ["clients"],
        "latency_warn_ms": 5000, "latency_err_ms": 15000,
        "nullable_ok": [],
        "critical": False,
    },
    {
        "path": "/api/devis-suivre",
        "method": "GET",
        "required_keys": [],
        "latency_warn_ms": 3000, "latency_err_ms": 8000,
        "nullable_ok": [],
        "critical": False,
    },
    {
        "path": "/api/proposals-orders",
        "method": "GET",
        "required_keys": [],
        "latency_warn_ms": 5000, "latency_err_ms": 12000,
        "nullable_ok": [],
        "critical": False,
    },
    {
        "path": "/api/config",
        "method": "GET",
        "required_keys": ["dolibarr_url"],
        "latency_warn_ms": 200, "latency_err_ms": 500,
        "nullable_ok": ["dolibarr_url"],
        "critical": False,
    },
    {
        "path": "/api/health",
        "method": "GET",
        "required_keys": ["overall", "score", "checks"],
        "latency_warn_ms": 3000, "latency_err_ms": 8000,
        "nullable_ok": [],
        "critical": True,
    },
    {
        "path": "/api/synthesis",
        "method": "GET",
        "required_keys": ["health_score", "wellbeing", "ca_mois_ht"],
        "latency_warn_ms": 15000, "latency_err_ms": 30000,
        "nullable_ok": ["taux_conversion_pct"],
        "critical": False,
    },
    {
        "path": "/api/n8n/workflows",
        "method": "GET",
        "required_keys": ["workflows"],
        "latency_warn_ms": 3000, "latency_err_ms": 8000,
        "nullable_ok": ["workflows"],
        "critical": False,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# TYPES
# ─────────────────────────────────────────────────────────────────────────────

class EndpointResult(TypedDict):
    path:           str
    status:         str          # "ok" | "warn" | "error" | "skip"
    http_code:      int | None
    latency_ms:     float | None
    issues:         list[str]    # problèmes détectés
    fixes:          list[str]    # suggestions de correctifs
    data_preview:   str          # aperçu réponse (100 chars max)
    critical:       bool


class DashboardReport(TypedDict):
    generated_at:       str
    base_url:           str
    dashboard_running:  bool
    overall:            str      # "healthy" | "degraded" | "critical" | "offline"
    score:              int      # 0-100
    results:            list[EndpointResult]
    summary:            dict     # stats globales
    auto_fixes_applied: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# VÉRIFICATION DISPONIBILITÉ DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

async def is_dashboard_running(base: str) -> bool:
    """Vérifie si le dashboard répond sur base."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{base}/api/config")
            return r.status_code < 500
    except Exception:
        return False


def start_dashboard(port: int = DEFAULT_PORT) -> subprocess.Popen | None:
    """Démarre le dashboard en arrière-plan. Retourne le process ou None."""
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn",
             "dashboard.app:app", "--port", str(port),
             "--host", "127.0.0.1", "--log-level", "warning"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE RÉPONSE — CORRECTIFS AUTO
# ─────────────────────────────────────────────────────────────────────────────

# Patterns d'erreur → suggestions de correctifs
_ERROR_PATTERNS: list[tuple[str, str]] = [
    ("DOLAPIKEY",         "Vérifier DOLIBARR_API_KEY dans .env"),
    ("ConnectionRefused", "Dolibarr inaccessible — vérifier DOLIBARR_BASE_URL"),
    ("timeout",           "Timeout Dolibarr — augmenter httpx timeout ou vérifier réseau"),
    ("NoneType",          "Variable None non gérée — ajouter guard `or []` / `or {}`"),
    ("KeyError",          "Clé manquante dans la réponse Dolibarr — vérifier le mapping"),
    ("sortfield",         "Anti-pattern P11 : sortfield non supporté — supprimer le paramètre"),
    ("503",               "Endpoint Dolibarr retourne 503 — souvent un sqlfilters invalide"),
    ("422",               "Paramètre invalide — vérifier la structure de la requête"),
    ("import",            "Import manquant — vérifier les dépendances dans requirements.txt"),
]


def _extract_fixes(issues: list[str], body_text: str) -> list[str]:
    """Génère des suggestions de correctifs depuis les issues et le body de réponse."""
    fixes: list[str] = []
    combined = " ".join(issues) + " " + body_text.lower()
    for pattern, fix in _ERROR_PATTERNS:
        if pattern.lower() in combined:
            fixes.append(fix)
    # Déduplication
    return list(dict.fromkeys(fixes))


def _check_data_coherence(spec: EndpointSpec, data: dict | list) -> list[str]:
    """Vérifie la cohérence des données (valeurs suspectes, champs vides)."""
    issues: list[str] = []
    if not isinstance(data, dict):
        return issues

    # Champs requis
    for key in spec["required_keys"]:
        if key not in data:
            issues.append(f"Champ manquant : `{key}`")
        elif data[key] is None and key not in spec["nullable_ok"]:
            issues.append(f"Champ null inattendu : `{key}`")
        elif isinstance(data[key], (list, dict)) and not data[key] and key not in spec["nullable_ok"]:
            issues.append(f"Champ vide inattendu : `{key}` = {type(data[key]).__name__}()")

    # Checks spécifiques par endpoint
    path = spec["path"]
    if path == "/api/kpis":
        if data.get("devis_semaine", {}).get("nb", -1) < 0:
            issues.append("kpis: nb devis semaine négatif — problème de parsing date")
    if path == "/api/daf":
        dso = data.get("dso_jours")
        if dso is not None and float(dso or 0) > 90:
            issues.append(f"⚠️  DSO critique : {dso:.0f} jours (seuil alerte 45j)")
    if path == "/api/health":
        score = data.get("score", 100)
        if score < 70:
            issues.append(f"Score santé dégradé : {score}/100")
    if path == "/api/synthesis":
        imp = data.get("impayes_total_ht", 0) or 0
        if float(imp) > 50000:
            issues.append(f"⚠️  Impayés élevés : {imp:,.0f} € HT")

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# TEST D'UN ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

async def test_endpoint(spec: EndpointSpec, base: str) -> EndpointResult:
    """Teste un endpoint et retourne son résultat."""
    import httpx

    url = f"{base}{spec['path']}"
    issues: list[str] = []
    http_code = None
    latency_ms = None
    data_preview = ""

    try:
        timeout = spec["latency_err_ms"] / 1000 + 2
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url)
        latency_ms = (time.monotonic() - t0) * 1000
        http_code  = r.status_code

        # Statut HTTP
        if r.status_code >= 500:
            issues.append(f"HTTP {r.status_code} — erreur serveur")
            body_text = r.text[:500]
            data_preview = body_text[:100]
        elif r.status_code >= 400:
            issues.append(f"HTTP {r.status_code} — erreur client")
            body_text = r.text[:200]
            data_preview = body_text[:100]
        else:
            body_text = r.text
            # Parse JSON
            try:
                data = r.json()
                data_preview = str(data)[:100]
                issues.extend(_check_data_coherence(spec, data))
            except Exception:
                issues.append("Réponse non-JSON")
                body_text = r.text[:200]
                data_preview = r.text[:100]

        # Latence
        if latency_ms > spec["latency_err_ms"]:
            issues.append(f"Latence critique : {latency_ms:.0f}ms (seuil {spec['latency_err_ms']}ms)")
        elif latency_ms > spec["latency_warn_ms"]:
            issues.append(f"Latence élevée : {latency_ms:.0f}ms (seuil {spec['latency_warn_ms']}ms)")

    except asyncio.TimeoutError:
        issues.append(f"Timeout après {spec['latency_err_ms']+2000}ms")
        body_text = "timeout"
    except Exception as e:
        issues.append(f"Erreur connexion : {str(e)[:80]}")
        body_text = str(e)

    fixes = _extract_fixes(issues, body_text if "body_text" in dir() else "")

    # Statut global
    critical_issue = any(
        "HTTP 5" in i or "Timeout" in i or "connexion" in i or "manquant" in i
        for i in issues
    )
    warn_issue = bool(issues)

    if critical_issue:
        status = "error"
    elif warn_issue:
        status = "warn"
    else:
        status = "ok"

    return EndpointResult(
        path=spec["path"],
        status=status,
        http_code=http_code,
        latency_ms=round(latency_ms, 1) if latency_ms else None,
        issues=issues,
        fixes=fixes,
        data_preview=data_preview,
        critical=spec["critical"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCORE & RAPPORT
# ─────────────────────────────────────────────────────────────────────────────

def _compute_score(results: list[EndpointResult]) -> int:
    base = 100
    for r in results:
        if r["status"] == "error":
            base -= 15 if r["critical"] else 5
        elif r["status"] == "warn":
            base -= 5 if r["critical"] else 2
    return max(0, min(100, base))


def _overall_status(running: bool, score: int) -> str:
    if not running:
        return "offline"
    if score >= 75:
        return "healthy"
    if score >= 45:
        return "degraded"
    return "critical"


def generate_dashboard_report_md(report: DashboardReport) -> str:
    now   = report["generated_at"][:16].replace("T", " ")
    score = report["score"]
    overall = report["overall"]
    running = report["dashboard_running"]

    icon_map = {"healthy": "🟢", "degraded": "🟡", "critical": "🔴", "offline": "⚫"}
    status_icon = icon_map.get(overall, "❓")

    # Résumé
    summary = report["summary"]
    nb_ok   = summary.get("ok", 0)
    nb_warn = summary.get("warn", 0)
    nb_err  = summary.get("error", 0)
    nb_skip = summary.get("skip", 0)

    # Tableau résultats
    rows = []
    for r in report["results"]:
        icon    = {"ok": "✅", "warn": "⚠️", "error": "❌", "skip": "⏭"}.get(r["status"], "❓")
        lat     = f"{r['latency_ms']:.0f}ms" if r["latency_ms"] else "—"
        crit    = "🔴" if r["critical"] else ""
        issues  = "; ".join(r["issues"])[:60] or "—"
        rows.append([icon + crit, r["path"], str(r.get("http_code") or "—"), lat, issues])

    table_header = "| | Endpoint | HTTP | Latence | Observations |"
    table_sep    = "|---|----------|------|---------|-------------|"
    table_rows   = "\n".join("| " + " | ".join(row) + " |" for row in rows)

    # Correctifs suggérés
    all_fixes: list[str] = []
    for r in report["results"]:
        for f in r["fixes"]:
            label = f"[`{r['path']}`] {f}"
            if label not in all_fixes:
                all_fixes.append(label)

    fixes_md = ("\n".join(f"- {f}" for f in all_fixes)
                if all_fixes else "- Aucun correctif suggéré ✅")

    # Endpoints critiques en erreur
    critical_errors = [r for r in report["results"] if r["status"] == "error" and r["critical"]]
    critical_md = ""
    if critical_errors:
        critical_md = "\n### 🔴 Endpoints critiques en erreur\n"
        for r in critical_errors:
            critical_md += f"\n**`{r['path']}`** — {'; '.join(r['issues'])}"
            if r["fixes"]:
                critical_md += "\n" + "\n".join(f"> {fix}" for fix in r["fixes"])

    running_str = "✅ En ligne" if running else "❌ **Hors ligne** — `uvicorn dashboard.app:app --reload --port 8080`"

    return f"""# DASHBOARD REPORT — InPressco

> Généré le {now} UTC | Score : **{score}/100** {status_icon} {overall.upper()}

---

## État général

| Métrique | Valeur |
|----------|--------|
| Dashboard | {running_str} |
| URL testée | `{report['base_url']}` |
| Endpoints testés | {len(report['results'])} |
| OK | {nb_ok} |
| Avertissements | {nb_warn} |
| Erreurs | {nb_err} |
| Ignorés | {nb_skip} |

{critical_md}

---

## Résultats par endpoint

{table_header}
{table_sep}
{table_rows}

---

## Correctifs suggérés

{fixes_md}

---

## Correctifs appliqués automatiquement

{chr(10).join(f"- {f}" for f in report['auto_fixes_applied']) if report['auto_fixes_applied'] else "- Aucun correctif automatique appliqué"}

---

*Pour relancer : `python main.py --check-dashboard`*
"""


# ─────────────────────────────────────────────────────────────────────────────
# CORRECTIFS AUTOMATIQUES
# ─────────────────────────────────────────────────────────────────────────────

def apply_auto_fixes(results: list[EndpointResult]) -> list[str]:
    """Applique les correctifs qui peuvent l'être sans intervention humaine.

    Actuellement : aucun correctif ne modifie le code source.
    Les correctifs automatiques sont limités aux actions safe :
    - Régénérer health_report.json si /api/health retourne 503
    - Régénérer STRATEGIC_SYNTHESIS si /api/synthesis échoue sur fichier manquant
    """
    applied: list[str] = []

    for r in results:
        # Si /api/health retourne 503 (fichier manquant) → régénérer le rapport
        if r["path"] == "/api/health" and r["http_code"] == 503:
            try:
                health_file = REPORTS_DIR / "health_report.json"
                if not health_file.exists():
                    import subprocess as sp
                    sp.run(
                        [sys.executable, str(ROOT / "tools" / "system_verify.py")],
                        cwd=str(ROOT), timeout=30,
                        capture_output=True,
                    )
                    applied.append("/api/health : health_report.json régénéré automatiquement")
            except Exception:
                pass

    return applied


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

async def run_dashboard_verify(
    base:          str = DEFAULT_BASE,
    start_if_down: bool = False,
    skip_slow:     bool = False,
    output_path:   Path | None = None,
) -> DashboardReport:
    """Teste tous les endpoints et produit un DashboardReport.

    Args:
        base:          URL de base du dashboard (ex: http://127.0.0.1:8080)
        start_if_down: Lance le dashboard automatiquement s'il est éteint
        skip_slow:     Ignore les endpoints lents (/api/synthesis, /api/clients)
        output_path:   Chemin du rapport JSON (défaut: reports/dashboard_report.json)
    """
    REPORTS_DIR.mkdir(exist_ok=True)
    if output_path is None:
        output_path = REPORTS_DIR / "dashboard_report.json"

    # 1. Vérifier si le dashboard tourne
    running = await is_dashboard_running(base)
    _proc   = None

    if not running and start_if_down:
        port = int(base.split(":")[-1]) if ":" in base else DEFAULT_PORT
        print(f"  ⚡ Dashboard éteint — démarrage sur port {port}...")
        _proc = start_dashboard(port)
        await asyncio.sleep(3)  # laisser le temps de démarrer
        running = await is_dashboard_running(base)

    if not running:
        report = DashboardReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            base_url=base,
            dashboard_running=False,
            overall="offline",
            score=0,
            results=[],
            summary={"ok": 0, "warn": 0, "error": 0, "skip": len(ENDPOINT_SPECS)},
            auto_fixes_applied=[],
        )
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return report

    # 2. Sélectionner les endpoints à tester
    SLOW_PATHS = {"/api/synthesis", "/api/clients", "/api/ca-chart", "/api/proposals-orders"}
    specs_to_test = [
        s for s in ENDPOINT_SPECS
        if not (skip_slow and s["path"] in SLOW_PATHS)
    ]

    # 3. Tests en parallèle (par lots pour éviter de saturer le dashboard)
    BATCH_SIZE = 5
    results: list[EndpointResult] = []

    for i in range(0, len(specs_to_test), BATCH_SIZE):
        batch = specs_to_test[i:i + BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[test_endpoint(spec, base) for spec in batch],
            return_exceptions=True,
        )
        for spec, r in zip(batch, batch_results):
            if isinstance(r, Exception):
                results.append(EndpointResult(
                    path=spec["path"], status="error",
                    http_code=None, latency_ms=None,
                    issues=[f"Exception inattendue : {r}"],
                    fixes=[], data_preview="", critical=spec["critical"],
                ))
            else:
                results.append(r)

    # 4. Correctifs automatiques
    auto_fixes = apply_auto_fixes(results)

    # 5. Score et statut global
    score   = _compute_score(results)
    overall = _overall_status(running, score)

    summary = {
        s: sum(1 for r in results if r["status"] == s)
        for s in ("ok", "warn", "error", "skip")
    }
    summary["skip"] += len(ENDPOINT_SPECS) - len(specs_to_test)

    report = DashboardReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        base_url=base,
        dashboard_running=running,
        overall=overall,
        score=score,
        results=results,
        summary=summary,
        auto_fixes_applied=auto_fixes,
    )

    # 6. Écriture JSON
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    # 7. Rapport Markdown
    md = generate_dashboard_report_md(report)
    (REPORTS_DIR / "DASHBOARD_REPORT.md").write_text(md, encoding="utf-8")

    # 8. Enregistrement intention
    try:
        from tools.intent_tracker import record_intent
        record_intent(
            action="dashboard_verified",
            description=(
                f"Autotest dashboard — score {score}/100 ({overall}) — "
                f"{summary['ok']} OK / {summary['warn']} warn / {summary['error']} erreurs"
            ),
            category="technique",
            actor="tools",
            outcome="success" if score >= 75 else "partial",
        )
    except Exception:
        pass

    return report


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Autotest dashboard InPressco",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python tools/dashboard_verify.py                  # test rapide\n"
            "  python tools/dashboard_verify.py --start-if-down  # démarre si éteint\n"
            "  python tools/dashboard_verify.py --skip-slow       # ignore /synthesis etc.\n"
            "  python tools/dashboard_verify.py --port 9000       # port custom\n"
        ),
    )
    parser.add_argument("--port",          type=int, default=DEFAULT_PORT)
    parser.add_argument("--start-if-down", action="store_true",
                        help="Démarre le dashboard s'il est éteint")
    parser.add_argument("--skip-slow",     action="store_true",
                        help="Ignore les endpoints lents (>5s attendus)")
    parser.add_argument("--json",          action="store_true",
                        help="Sortie JSON brute")
    args = parser.parse_args()

    base   = f"http://127.0.0.1:{args.port}"
    report = asyncio.run(run_dashboard_verify(
        base=base,
        start_if_down=args.start_if_down,
        skip_slow=args.skip_slow,
    ))

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        sys.exit(0)

    # Sortie console
    icon_map = {"healthy": "✅", "degraded": "⚠️", "critical": "🔴", "offline": "⚫"}
    overall_icon = icon_map.get(report["overall"], "❓")

    if not report["dashboard_running"]:
        print(f"⚫ Dashboard OFFLINE sur {base}")
        print(f"   → Démarrer : uvicorn dashboard.app:app --reload --port {args.port}")
        sys.exit(1)

    print(f"\n{overall_icon} Dashboard {report['overall'].upper()} — score {report['score']}/100")
    print(f"   {report['summary']['ok']} OK · "
          f"{report['summary']['warn']} warn · "
          f"{report['summary']['error']} erreurs")
    print()

    # Affiche les problèmes seulement
    problems = [r for r in report["results"] if r["status"] != "ok"]
    if problems:
        for r in problems:
            icon  = "⚠️ " if r["status"] == "warn" else "❌"
            crit  = " [CRITIQUE]" if r["critical"] else ""
            lat   = f" {r['latency_ms']:.0f}ms" if r["latency_ms"] else ""
            print(f"  {icon} {r['path']}{crit}{lat}")
            for issue in r["issues"]:
                print(f"       · {issue}")
            for fix in r["fixes"]:
                print(f"       → {fix}")
    else:
        print("  Tous les endpoints répondent correctement. ✅")

    if report["auto_fixes_applied"]:
        print(f"\n  ⚙️  Correctifs appliqués automatiquement :")
        for f in report["auto_fixes_applied"]:
            print(f"     · {f}")

    print(f"\n  📄 {REPORTS_DIR}/DASHBOARD_REPORT.md")
    print()

    sys.exit(0 if report["overall"] in ("healthy",) else 1)
