"""tools/system_report_generator.py — Génération des rapports système InPressco.

Produit deux artefacts depuis reports/health_report.json :
  - reports/SYSTEM_REPORT.md  : rapport texte complet
  - reports/SYSTEM_REPORT.svg : dashboard visuel (SVG pur, sans dépendances)

Usage :
  python main.py --report
  python tools/system_report_generator.py [--auto]

Le flag --auto est utilisé par le hook git post-commit (sortie silencieuse).
"""
from __future__ import annotations

import asyncio
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT        = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"

# Palette InPressco (mode sombre)
_PALETTE = {
    "bg":         "#0f172a",
    "surface":    "#1e293b",
    "border":     "#334155",
    "ok":         "#22c55e",
    "warn":       "#f59e0b",
    "error":      "#ef4444",
    "text":       "#f1f5f9",
    "text_dim":   "#94a3b8",
    "gold":       "#C9A96E",
}


# ─────────────────────────────────────────────────────────────────────────────
# MARKDOWN
# ─────────────────────────────────────────────────────────────────────────────

def _status_emoji(s: str) -> str:
    return {"ok": "✅", "warn": "⚠️", "error": "❌"}.get(s, "❓")


def _score_label(score: int) -> str:
    if score >= 70:
        return "🟢 HEALTHY"
    if score >= 40:
        return "🟡 DEGRADED"
    return "🔴 CRITICAL"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    head = "| " + " | ".join(headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in rows)
    return f"{head}\n{sep}\n{body}"


def generate_system_report_md(report: dict) -> str:
    now   = report.get("generated_at", datetime.now(timezone.utc).isoformat())
    score = report.get("score", 0)
    overall = report.get("overall", "unknown")
    checks  = report.get("checks", [])
    skill_cov   = report.get("skill_coverage", {})
    integrity   = report.get("pipeline_integrity", {})
    anti_pats   = report.get("anti_pattern_violations", [])

    # ── Connexions API ────────────────────────────────────────────────────
    conn_rows = []
    for c in checks:
        icon    = _status_emoji(c.get("status", "error"))
        latency = f"{c['latency_ms']:.0f}ms" if c.get("latency_ms") else "—"
        conn_rows.append([icon, c.get("name", "?"), c.get("detail", ""), latency])
    conn_table = _md_table(
        ["", "Service", "Détail", "Latence"],
        conn_rows,
    )

    # ── Intégrité pipeline ─────────────────────────────────────────────────
    p_ok   = "✅ OK" if integrity.get("ok") else "❌ Violations détectées"
    p_viol = integrity.get("violations", [])

    # ── Couverture skills ──────────────────────────────────────────────────
    sc_total = skill_cov.get("total", 0)
    sc_impl  = skill_cov.get("implemented", 0)
    sc_miss  = skill_cov.get("missing", [])

    # ── Actions recommandées ───────────────────────────────────────────────
    actions: list[str] = []
    for c in checks:
        if c.get("status") == "error":
            actions.append(f"**P0** — Corriger connexion `{c['name']}` : {c['detail']}")
        elif c.get("status") == "warn":
            actions.append(f"**P1** — Vérifier `{c['name']}` : {c['detail']}")
    for v in p_viol:
        actions.append(f"**P1** — Pipeline : {v}")
    for ap in anti_pats[:3]:
        actions.append(f"**P2** — Code : {ap}")

    actions_md = "\n".join(f"- {a}" for a in actions) if actions else "- Aucune action requise 🎉"

    return f"""# SYSTEM REPORT — InPressco MWP

> Généré le {now[:19].replace("T", " ")} UTC | Score : **{score}/100** {_score_label(score)}

---

## Connexions API

{conn_table}

---

## Intégrité Pipeline

**Statut global** : {p_ok}

{"**Violations :**" if p_viol else "Aucune violation détectée."}
{"" + chr(10).join(f"- `{v}`" for v in p_viol) if p_viol else ""}

---

## Couverture Skills

| Métrique | Valeur |
|----------|--------|
| Skills référencés | {sc_total} |
| Skills installés | {sc_impl} |
| Skills manquants | {len(sc_miss)} |

{"**Skills non trouvés dans ~/.claude/skills/ :**" if sc_miss else ""}
{"" + chr(10).join(f"- `{s}`" for s in sc_miss[:10]) if sc_miss else ""}

---

## Anti-patterns détectés dans src/

{chr(10).join(f"- {ap}" for ap in anti_pats) if anti_pats else "Aucun anti-pattern détecté. ✅"}

---

## Actions recommandées

{actions_md}

---

*Ce rapport est généré automatiquement par `tools/system_report_generator.py`.*
*Pour régénérer : `python main.py --report`*
"""


# ─────────────────────────────────────────────────────────────────────────────
# SVG DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

def _svg_rect(parent: ET.Element, x: int, y: int, w: int, h: int,
              fill: str, rx: int = 8, stroke: str = "", stroke_w: int = 0) -> ET.Element:
    attrs = dict(x=str(x), y=str(y), width=str(w), height=str(h),
                 fill=fill, rx=str(rx))
    if stroke:
        attrs["stroke"] = stroke
        attrs["stroke-width"] = str(stroke_w)
    el = ET.SubElement(parent, "rect", **attrs)
    return el


def _svg_text(parent: ET.Element, x: int, y: int, text: str,
              fill: str = "#f1f5f9", font_size: int = 14,
              font_weight: str = "normal", anchor: str = "start") -> ET.Element:
    el = ET.SubElement(parent, "text",
                       x=str(x), y=str(y),
                       fill=fill,
                       **{"font-size": str(font_size),
                          "font-family": "Inter, -apple-system, sans-serif",
                          "font-weight": font_weight,
                          "text-anchor": anchor})
    el.text = text
    return el


def _status_color(status: str) -> str:
    return {"ok": _PALETTE["ok"], "warn": _PALETTE["warn"],
            "error": _PALETTE["error"]}.get(status, "#64748b")


def generate_system_report_svg(report: dict) -> str:
    """Génère un SVG dashboard 800×480 sans dépendances externes."""
    score   = report.get("score", 0)
    overall = report.get("overall", "unknown")
    checks  = report.get("checks", [])
    now     = report.get("generated_at", "")[:16].replace("T", " ")

    W, H = 800, 480
    svg = ET.Element("svg",
                     xmlns="http://www.w3.org/2000/svg",
                     width=str(W), height=str(H),
                     viewBox=f"0 0 {W} {H}")

    # ── Fond ──────────────────────────────────────────────────────────────
    _svg_rect(svg, 0, 0, W, H, _PALETTE["bg"], rx=0)

    # ── En-tête ───────────────────────────────────────────────────────────
    _svg_rect(svg, 0, 0, W, 60, _PALETTE["surface"], rx=0)
    _svg_text(svg, 24, 26, "INPRESSCO", fill=_PALETTE["gold"],
              font_size=13, font_weight="600")
    _svg_text(svg, 24, 44, "SYSTEM REPORT", fill=_PALETTE["text"],
              font_size=18, font_weight="700")
    _svg_text(svg, W - 20, 26, f"Score {score}/100", fill=_PALETTE["text_dim"],
              font_size=13, anchor="end")
    overall_color = _PALETTE["ok"] if score >= 70 else _PALETTE["warn"] if score >= 40 else _PALETTE["error"]
    _svg_text(svg, W - 20, 44, overall.upper(), fill=overall_color,
              font_size=14, font_weight="700", anchor="end")

    # ── Jauge score ───────────────────────────────────────────────────────
    # Arc SVG simple : fond gris + arc coloré
    cx, cy, r_arc = W // 2, 170, 60
    circumference = int(2 * 3.14159 * r_arc)
    filled = int(circumference * score / 100)

    # Cercle fond
    ET.SubElement(svg, "circle",
                  cx=str(cx), cy=str(cy), r=str(r_arc),
                  fill="none", stroke=_PALETTE["border"],
                  **{"stroke-width": "12"})
    # Arc score
    ET.SubElement(svg, "circle",
                  cx=str(cx), cy=str(cy), r=str(r_arc),
                  fill="none", stroke=overall_color,
                  **{"stroke-width": "12",
                     "stroke-dasharray": f"{filled} {circumference}",
                     "stroke-dashoffset": str(circumference // 4),
                     "stroke-linecap": "round"})
    _svg_text(svg, cx, cy + 8, str(score), fill=_PALETTE["text"],
              font_size=28, font_weight="700", anchor="middle")
    _svg_text(svg, cx, cy + 26, "/100", fill=_PALETTE["text_dim"],
              font_size=13, anchor="middle")

    # ── Cartes connexions ─────────────────────────────────────────────────
    card_w, card_h = 200, 90
    card_y = 240
    card_labels = {"dolibarr": "Dolibarr CRM", "claude_api": "Claude API", "outlook": "Outlook 365"}
    check_map = {c["name"]: c for c in checks}
    positions = [40, 300, 560]

    for i, (name, label) in enumerate(card_labels.items()):
        cx_card = positions[i]
        c = check_map.get(name, {"status": "warn", "detail": "Non vérifié", "latency_ms": None})
        color  = _status_color(c.get("status", "warn"))
        detail = (c.get("detail") or "")[:30]

        _svg_rect(svg, cx_card, card_y, card_w, card_h, _PALETTE["surface"],
                  rx=10, stroke=color, stroke_w=1)
        _svg_text(svg, cx_card + 12, card_y + 22, label,
                  fill=_PALETTE["text"], font_size=13, font_weight="600")
        _svg_text(svg, cx_card + 12, card_y + 42,
                  c.get("status", "?").upper(), fill=color, font_size=12, font_weight="700")
        _svg_text(svg, cx_card + 12, card_y + 60, detail,
                  fill=_PALETTE["text_dim"], font_size=11)
        if c.get("latency_ms"):
            _svg_text(svg, cx_card + 12, card_y + 76,
                      f"{c['latency_ms']:.0f}ms", fill=_PALETTE["text_dim"], font_size=11)

    # ── Pipeline intégrité ────────────────────────────────────────────────
    integrity = report.get("pipeline_integrity", {})
    p_ok      = integrity.get("ok", False)
    p_viol    = integrity.get("violations", [])
    p_color   = _PALETTE["ok"] if p_ok else _PALETTE["error"]
    p_label   = "Pipeline OK" if p_ok else f"Pipeline — {len(p_viol)} violation(s)"
    _svg_rect(svg, 40, 360, 720, 50, _PALETTE["surface"], rx=8,
              stroke=p_color, stroke_w=1)
    _svg_text(svg, 60, 382, "🔗 " + p_label, fill=p_color,
              font_size=13, font_weight="600")
    if p_viol:
        _svg_text(svg, 60, 400, p_viol[0][:80],
                  fill=_PALETTE["text_dim"], font_size=11)

    # ── Pied de page ──────────────────────────────────────────────────────
    _svg_text(svg, W // 2, H - 14, f"Généré le {now} UTC • tools/system_report_generator.py",
              fill=_PALETTE["text_dim"], font_size=11, anchor="middle")

    ET.indent(svg, space="  ")
    return ET.tostring(svg, encoding="unicode", xml_declaration=False)


# ─────────────────────────────────────────────────────────────────────────────
# HOOK GIT
# ─────────────────────────────────────────────────────────────────────────────

def install_post_run_hook() -> bool:
    """Installe un hook git post-commit qui régénère les rapports."""
    git_dir = ROOT / ".git"
    if not git_dir.is_dir():
        return False
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "post-commit"

    script = (
        "#!/bin/sh\n"
        "# InPressco — régénération auto des rapports système\n"
        f'cd "{ROOT}" && python tools/system_report_generator.py --auto 2>/dev/null &\n'
    )

    if hook_path.exists():
        existing = hook_path.read_text()
        if "system_report_generator" in existing:
            return True  # déjà installé
        # Append au hook existant
        hook_path.write_text(existing.rstrip() + "\n" + script)
    else:
        hook_path.write_text(script)
        hook_path.chmod(0o755)

    return True


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────────────────────

async def generate_all(auto: bool = False) -> None:
    """Génère SYSTEM_REPORT.md + SYSTEM_REPORT.svg depuis health_report.json."""
    REPORTS_DIR.mkdir(exist_ok=True)

    health_file = REPORTS_DIR / "health_report.json"
    if not health_file.exists():
        if not auto:
            print("⚠️  health_report.json absent — lancement de la vérification...")
        from tools.system_verify import run_verify
        await run_verify(health_file)

    report = json.loads(health_file.read_text(encoding="utf-8"))

    # Markdown
    md = generate_system_report_md(report)
    md_path = REPORTS_DIR / "SYSTEM_REPORT.md"
    md_path.write_text(md, encoding="utf-8")

    # SVG
    svg = generate_system_report_svg(report)
    svg_path = REPORTS_DIR / "SYSTEM_REPORT.svg"
    svg_path.write_text(svg, encoding="utf-8")

    if not auto:
        score   = report.get("score", 0)
        overall = report.get("overall", "?")
        print(f"✅ Rapports générés — score {score}/100 ({overall})")
        print(f"   📄 {md_path}")
        print(f"   🖼  {svg_path}")

    # Installe le hook git si pas encore fait
    install_post_run_hook()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true",
                        help="Mode silencieux — appelé par git hook")
    args = parser.parse_args()
    asyncio.run(generate_all(auto=args.auto))
