"""tools/intent_tracker.py — Traçage et documentation des intentions InPressco.

Chaque interaction avec le système (pipeline, dashboard, Claude Code) enregistre
une intention structurée dans reports/intent_log.json.

Les intentions sont classées en 4 catégories :
  - technique     : modifications code, corrections, déploiements
  - commercial    : devis créés, emails envoyés, clients contactés
  - stratégique   : analyses, projections, décisions de direction
  - vision        : évolutions architecturales, principes, orientations

L'historique alimente la synthèse stratégique auto-générée.

Usage :
  from tools.intent_tracker import record_intent
  record_intent(action="created_devis", description="...", category="commercial")

  python tools/intent_tracker.py synthesize   # régénère la synthèse
  python tools/intent_tracker.py tail 20      # affiche les 20 dernières intentions
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT       = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
INTENT_LOG  = REPORTS_DIR / "intent_log.json"

IntentCategory = Literal["technique", "commercial", "stratégique", "vision"]

# Seuil : régénère la synthèse tous les N nouveaux enregistrements
_SYNTHESIS_THRESHOLD = 5


# ─────────────────────────────────────────────────────────────────────────────
# LOG I/O
# ─────────────────────────────────────────────────────────────────────────────

def _load_log() -> list[dict]:
    if not INTENT_LOG.exists():
        return []
    try:
        return json.loads(INTENT_LOG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_log(entries: list[dict]) -> None:
    """Écriture atomique pour éviter la corruption."""
    REPORTS_DIR.mkdir(exist_ok=True)
    tmp = INTENT_LOG.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    tmp.rename(INTENT_LOG)


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION AUTO
# ─────────────────────────────────────────────────────────────────────────────

_COMMERCIAL_VERBS = {
    "created_devis", "sent_email", "found_client", "created_client",
    "updated_devis", "signed_devis", "created_order", "sent_invoice",
    "replied_client", "created_proposal",
}
_STRATEGIQUE_VERBS = {
    "dso_calculated", "rfm_segment", "projection", "ca_analysis",
    "financial_report", "synthesis_generated", "pipeline_analysis",
    "kpi_computed", "conversion_rate",
}
_VISION_VERBS = {
    "architecture_change", "vision_update", "principle_updated",
    "skill_installed", "system_integrated", "layer_updated",
}


def auto_classify(action: str, context: dict | None = None) -> IntentCategory:
    action_lower = action.lower()
    if action_lower in _COMMERCIAL_VERBS:
        return "commercial"
    if action_lower in _STRATEGIQUE_VERBS:
        return "stratégique"
    if action_lower in _VISION_VERBS:
        return "vision"
    # Heuristiques secondaires
    if any(kw in action_lower for kw in ["devis", "client", "email", "cmd", "facture"]):
        return "commercial"
    if any(kw in action_lower for kw in ["analyse", "report", "kpi", "trend", "rfm"]):
        return "stratégique"
    if any(kw in action_lower for kw in ["install", "deploy", "config", "fix", "update"]):
        return "technique"
    return "technique"


# ─────────────────────────────────────────────────────────────────────────────
# ENREGISTREMENT
# ─────────────────────────────────────────────────────────────────────────────

def record_intent(
    action:      str,
    description: str,
    category:    IntentCategory | None = None,
    actor:       str = "pipeline",
    context:     dict | None = None,
    outcome:     str = "success",
    linked_ref:  str | None = None,
    tags:        list[str] | None = None,
    session_id:  str | None = None,
) -> str:
    """Enregistre une intention et retourne son id.

    RÈGLE ABSOLUE : cette fonction ne doit JAMAIS lever d'exception.
    Utiliser dans les steps pipeline comme :
        try:
            from tools.intent_tracker import record_intent
            record_intent(...)
        except Exception:
            pass
    """
    try:
        if category is None:
            category = auto_classify(action, context)

        entry = {
            "id":          str(uuid.uuid4()),
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "session_id":  session_id or os.environ.get("INPRESSCO_SESSION_ID", ""),
            "actor":       actor,
            "category":    category,
            "action":      action,
            "description": description,
            "context":     context or {},
            "outcome":     outcome,
            "linked_dolibarr_ref": linked_ref,
            "tags":        tags or [],
        }

        entries = _load_log()
        entries.append(entry)
        _save_log(entries)

        # Régénère la synthèse tous les N enregistrements
        if len(entries) % _SYNTHESIS_THRESHOLD == 0:
            _trigger_synthesis_async()

        return entry["id"]
    except Exception:
        return ""  # jamais de propagation


def _trigger_synthesis_async() -> None:
    """Lance la régénération de synthèse en arrière-plan (non bloquant)."""
    try:
        import subprocess, sys
        subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "intent_tracker.py"), "synthesize"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION DE LA SYNTHÈSE STRATÉGIQUE
# ─────────────────────────────────────────────────────────────────────────────

def _count_by(entries: list[dict], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for e in entries:
        v = e.get(field, "unknown")
        result[v] = result.get(v, 0) + 1
    return dict(sorted(result.items(), key=lambda x: -x[1]))


def generate_strategic_synthesis_md(entries: list[dict]) -> str:
    now = datetime.now(timezone.utc).isoformat()[:16].replace("T", " ")

    by_cat    = _count_by(entries, "category")
    by_actor  = _count_by(entries, "actor")
    by_outcome = _count_by(entries, "outcome")
    recent    = entries[-10:][::-1]

    # Stats commerciales 7 jours
    cutoff = datetime.now(timezone.utc).timestamp() - 7 * 86400
    recent_7d = [
        e for e in entries
        if datetime.fromisoformat(e.get("timestamp", "2000-01-01")).timestamp() > cutoff
    ]
    commercial_7d = [e for e in recent_7d if e.get("category") == "commercial"]
    devis_7d  = sum(1 for e in commercial_7d if "devis" in e.get("action", ""))
    emails_7d = sum(1 for e in commercial_7d if "email" in e.get("action", ""))

    # Signaux dette technique
    tech_failed = [
        e for e in entries
        if e.get("category") == "technique" and e.get("outcome") == "failed"
    ]

    # Dernière intention vision
    vision_entries = [e for e in entries if e.get("category") == "vision"]
    last_vision = vision_entries[-1]["timestamp"][:10] if vision_entries else "Aucune"

    # Tableau des catégories
    cat_table_rows = [
        [cat, str(count), f"{count / max(len(entries), 1) * 100:.0f}%"]
        for cat, count in by_cat.items()
    ]
    cat_table = "| Catégorie | Nb | % |\n|-----------|----|----|"
    for r in cat_table_rows:
        cat_table += f"\n| {r[0]} | {r[1]} | {r[2]} |"

    # Timeline des 10 derniers
    timeline = ""
    for e in recent:
        ts   = e.get("timestamp", "")[:16].replace("T", " ")
        cat  = e.get("category", "?")
        act  = e.get("action", "?")
        desc = (e.get("description") or "")[:60]
        ref  = f" `{e['linked_dolibarr_ref']}`" if e.get("linked_dolibarr_ref") else ""
        timeline += f"\n- `{ts}` [{cat}] **{act}**{ref} — {desc}"

    return f"""# SYNTHÈSE STRATÉGIQUE — InPressco

> Générée le {now} UTC | {len(entries)} intentions enregistrées

---

## Vue d'ensemble

{cat_table}

**Acteurs :** {" · ".join(f"{k} ({v})" for k, v in by_actor.items())}
**Résultats :** {" · ".join(f"{k} ({v})" for k, v in by_outcome.items())}

---

## Momentum commercial (7 derniers jours)

| Indicateur | Valeur |
|------------|--------|
| Intentions commerciales | {len(commercial_7d)} |
| Devis créés / modifiés | {devis_7d} |
| Emails clients | {emails_7d} |
| Taux succès global | {by_outcome.get("success", 0) / max(len(entries), 1) * 100:.0f}% |

---

## Signaux technique

{"⚠️  " + str(len(tech_failed)) + " actions techniques en échec — à investiguer" if tech_failed else "✅ Aucun échec technique enregistré"}

{chr(10).join(f"- `{e['action']}` : {e.get('description', '')[:60]}" for e in tech_failed[-3:]) if tech_failed else ""}

---

## Alignement vision

Dernière intention de type **vision** : `{last_vision}`
{("⚠️  Plus de 30 jours sans évolution vision" if last_vision != "Aucune" and (datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(last_vision + "T00:00:00+00:00").timestamp()) > 30 * 86400 else "")}

---

## Timeline — 10 dernières intentions
{timeline}

---

*Ce document est généré automatiquement par `tools/intent_tracker.py`.*
*Pour régénérer : `python tools/intent_tracker.py synthesize`*
"""


def generate_strategic_synthesis_svg(entries: list[dict]) -> str:
    """SVG 4-quadrants proportionnel au volume par catégorie."""
    from xml.etree.ElementTree import Element, SubElement, tostring, indent

    by_cat = _count_by(entries, "category")
    total  = max(len(entries), 1)
    cats   = ["technique", "commercial", "stratégique", "vision"]
    colors = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7"]
    labels_fr = ["Technique", "Commercial", "Stratégique", "Vision"]

    W, H = 800, 500
    svg = Element("svg",
                  xmlns="http://www.w3.org/2000/svg",
                  width=str(W), height=str(H),
                  viewBox=f"0 0 {W} {H}")

    # Fond
    SubElement(svg, "rect", x="0", y="0", width=str(W), height=str(H), fill="#0f172a")

    # Titre
    t = SubElement(svg, "text", x="400", y="36",
                   fill="#C9A96E", **{"font-size": "15", "font-weight": "700",
                                     "text-anchor": "middle",
                                     "font-family": "Inter, sans-serif"})
    t.text = "SYNTHÈSE STRATÉGIQUE — InPressco"

    t2 = SubElement(svg, "text", x="400", y="56",
                    fill="#94a3b8", **{"font-size": "12", "text-anchor": "middle",
                                      "font-family": "Inter, sans-serif"})
    t2.text = f"{total} intentions enregistrées"

    # 4 quadrants
    positions = [(60, 80), (420, 80), (60, 290), (420, 290)]
    qW, qH = 320, 190

    for i, (cat, color, label) in enumerate(zip(cats, colors, labels_fr)):
        qx, qy = positions[i]
        count  = by_cat.get(cat, 0)
        pct    = count / total * 100

        # Cadre
        SubElement(svg, "rect",
                   x=str(qx), y=str(qy), width=str(qW), height=str(qH),
                   fill="#1e293b", rx="10",
                   stroke=color, **{"stroke-width": "1"})

        # Titre quadrant
        tl = SubElement(svg, "text",
                        x=str(qx + 16), y=str(qy + 28),
                        fill=color, **{"font-size": "14", "font-weight": "700",
                                       "font-family": "Inter, sans-serif"})
        tl.text = label

        # Compteur
        tc = SubElement(svg, "text",
                        x=str(qx + qW - 16), y=str(qy + 28),
                        fill="#f1f5f9",
                        **{"font-size": "22", "font-weight": "700",
                           "text-anchor": "end", "font-family": "Inter, sans-serif"})
        tc.text = str(count)

        # Barre de progression
        bar_y   = qy + 50
        bar_h   = 12
        bar_w   = qW - 32
        fill_w  = int(bar_w * pct / 100)
        SubElement(svg, "rect",
                   x=str(qx + 16), y=str(bar_y),
                   width=str(bar_w), height=str(bar_h),
                   fill="#334155", rx="6")
        if fill_w > 0:
            SubElement(svg, "rect",
                       x=str(qx + 16), y=str(bar_y),
                       width=str(fill_w), height=str(bar_h),
                       fill=color, rx="6")
        # %
        tp = SubElement(svg, "text",
                        x=str(qx + 16), y=str(bar_y + 28),
                        fill="#94a3b8",
                        **{"font-size": "12", "font-family": "Inter, sans-serif"})
        tp.text = f"{pct:.0f}% des intentions"

    # Pied de page
    now_str = datetime.now(timezone.utc).isoformat()[:16].replace("T", " ")
    tf = SubElement(svg, "text",
                    x="400", y=str(H - 12),
                    fill="#475569",
                    **{"font-size": "11", "text-anchor": "middle",
                       "font-family": "Inter, sans-serif"})
    tf.text = f"Généré le {now_str} UTC • tools/intent_tracker.py"

    indent(svg, space="  ")
    return ET.tostring(svg, encoding="unicode") if False else \
        __import__("xml.etree.ElementTree", fromlist=["tostring"]).tostring(svg, encoding="unicode")


# ─────────────────────────────────────────────────────────────────────────────
# RÉGÉNÉRATION DE LA SYNTHÈSE
# ─────────────────────────────────────────────────────────────────────────────

def regenerate_synthesis() -> None:
    """Lit intent_log.json et écrit STRATEGIC_SYNTHESIS.md + .svg."""
    REPORTS_DIR.mkdir(exist_ok=True)
    entries = _load_log()

    md = generate_strategic_synthesis_md(entries)
    (REPORTS_DIR / "STRATEGIC_SYNTHESIS.md").write_text(md, encoding="utf-8")

    try:
        svg_str = generate_strategic_synthesis_svg(entries)
        (REPORTS_DIR / "STRATEGIC_SYNTHESIS.svg").write_text(svg_str, encoding="utf-8")
    except Exception:
        pass  # SVG optionnel


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "synthesize":
        regenerate_synthesis()
        print(f"✅ Synthèse régénérée → {REPORTS_DIR}/STRATEGIC_SYNTHESIS.md")

    elif cmd == "tail":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        entries = _load_log()
        for e in entries[-n:][::-1]:
            ts  = e.get("timestamp", "")[:16].replace("T", " ")
            cat = e.get("category", "?")
            act = e.get("action", "?")
            out = e.get("outcome", "?")
            ref = f" [{e['linked_dolibarr_ref']}]" if e.get("linked_dolibarr_ref") else ""
            print(f"{ts} [{cat:12s}] {act:25s} {out}{ref}")
            print(f"           {e.get('description', '')[:70]}")

    elif cmd == "record":
        # CLI rapide : python tools/intent_tracker.py record "action" "description" commercial
        if len(sys.argv) < 4:
            print("Usage: intent_tracker.py record <action> <description> [category]")
            sys.exit(1)
        entry_id = record_intent(
            action=sys.argv[2],
            description=sys.argv[3],
            category=sys.argv[4] if len(sys.argv) > 4 else None,
            actor="user",
        )
        print(f"✅ Intention enregistrée : {entry_id}")

    elif cmd == "stats":
        entries = _load_log()
        by_cat = _count_by(entries, "category")
        print(f"📊 {len(entries)} intentions totales")
        for cat, count in by_cat.items():
            print(f"   {cat:15s} {count:4d} ({count/max(len(entries),1)*100:.0f}%)")

    else:
        print("Usage: intent_tracker.py [synthesize|tail N|record <action> <desc> [cat]|stats]")


# Fix pour le SVG (import circulaire évité)
import xml.etree.ElementTree as ET
