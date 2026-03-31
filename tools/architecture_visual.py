"""tools/architecture_visual.py — Visuel d'architecture InPressco MWP.

Génère reports/ARCHITECTURE.svg : vue complète du système en mode sombre.

Usage :
    python tools/architecture_visual.py
    python main.py --archi
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT        = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"

# ── Palette ────────────────────────────────────────────────────────────────────
P = {
    "bg":        "#0d0f1a",
    "surface":   "#131929",
    "card":      "#1a2235",
    "border":    "#253047",
    "gold":      "#C9A96E",
    "gold_dim":  "#8a6d3b",
    "text":      "#e8edf5",
    "dim":       "#6b7a99",
    "ok":        "#34d399",
    "warn":      "#f59e0b",
    "err":       "#f87171",
    "blue":      "#60a5fa",
    "purple":    "#a78bfa",
    "pink":      "#f472b6",
    "teal":      "#2dd4bf",
    "orange":    "#fb923c",
    "green":     "#4ade80",
}

W   = 1280
H   = 2120
PAD = 32

# ── Helpers ────────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;")

class SVG:
    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.lines: list[str] = []
        self.lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">')

    def rect(self, x, y, w, h, fill=P["card"], rx=10, stroke="", sw=1, opacity=1.0):
        s = f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" rx="{rx}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        if opacity < 1.0:
            s += f' opacity="{opacity}"'
        s += '/>'
        self.lines.append(s)

    def text(self, x, y, content, fill=P["text"], size=13, weight="normal", anchor="start", opacity=1.0):
        s = (f'  <text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
             f'font-family="Inter, -apple-system, sans-serif" font-weight="{weight}" '
             f'text-anchor="{anchor}"')
        if opacity < 1.0:
            s += f' opacity="{opacity}"'
        s += f'>{_esc(content)}</text>'
        self.lines.append(s)

    def line(self, x1, y1, x2, y2, stroke=P["border"], sw=1.5, dash=""):
        s = f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"'
        if dash:
            s += f' stroke-dasharray="{dash}"'
        s += '/>'
        self.lines.append(s)

    def arrow(self, x1, y1, x2, y2, color=P["dim"], sw=1.5):
        """Horizontal arrow with arrowhead."""
        self.line(x1, y1, x2, y2, stroke=color, sw=sw)
        # arrowhead
        self.lines.append(
            f'  <polygon points="{x2},{y2} {x2-8},{y2-4} {x2-8},{y2+4}" fill="{color}"/>'
        )

    def section_label(self, x, y, label, color=P["gold"]):
        self.text(x, y, label, fill=color, size=11, weight="600")

    def finish(self) -> str:
        self.lines.append('</svg>')
        return "\n".join(self.lines)


def _card(svg: SVG, x, y, w, h, title, subtitle="", accent=P["border"], title_color=P["text"]):
    svg.rect(x, y, w, h, fill=P["card"], stroke=accent, sw=1)
    svg.text(x + 12, y + 18, title, fill=title_color, size=12, weight="600")
    if subtitle:
        svg.text(x + 12, y + 32, subtitle, fill=P["dim"], size=10)


def _step_box(svg: SVG, x, y, w, h, code, label, color=P["blue"]):
    svg.rect(x, y, w, h, fill=P["card"], stroke=color, sw=1, rx=8)
    svg.text(x + w//2, y + 14, code, fill=color, size=10, weight="700", anchor="middle")
    # word-wrap label over 2 lines
    words = label.split()
    if len(words) <= 2:
        svg.text(x + w//2, y + 26, label, fill=P["text"], size=9, anchor="middle")
    else:
        mid = len(words) // 2
        svg.text(x + w//2, y + 26, " ".join(words[:mid]), fill=P["text"], size=9, anchor="middle")
        svg.text(x + w//2, y + 36, " ".join(words[mid:]), fill=P["text"], size=9, anchor="middle")


def _pill(svg: SVG, x, y, w, h, label, bg, fg=P["bg"]):
    svg.rect(x, y, w, h, fill=bg, rx=h//2)
    svg.text(x + w//2, y + h//2 + 4, label, fill=fg, size=9, weight="600", anchor="middle")


# ── Build ──────────────────────────────────────────────────────────────────────

def build() -> str:
    svg = SVG(W, H)

    # ── Background ──────────────────────────────────────────────────────────
    svg.rect(0, 0, W, H, fill=P["bg"], rx=0)

    # ── HEADER ──────────────────────────────────────────────────────────────
    svg.rect(0, 0, W, 70, fill=P["surface"], rx=0)
    svg.line(0, 70, W, 70, stroke=P["gold_dim"], sw=1)
    svg.text(PAD, 28, "INPRESSCO", fill=P["gold"], size=12, weight="700")
    svg.text(PAD, 50, "ARCHITECTURE MWP", fill=P["text"], size=22, weight="700")
    svg.text(W - PAD, 28, f"28 mars 2026 · v1.0", fill=P["dim"], size=11, anchor="end")
    svg.text(W - PAD, 50, "inpressco-mwp", fill=P["dim"], size=12, anchor="end")

    y = 90

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — PIPELINE FLUX A
    # ══════════════════════════════════════════════════════════════════════════
    svg.section_label(PAD, y + 14, "01 — PIPELINE FLUX A  ·  email entrant → devis → réponse client")
    y += 24

    # Entry arrow
    svg.rect(PAD, y + 6, 80, 34, fill=P["surface"], stroke=P["dim"], sw=1, rx=6)
    svg.text(PAD + 40, y + 18, "email", fill=P["dim"], size=9, anchor="middle")
    svg.text(PAD + 40, y + 30, "entrant", fill=P["dim"], size=9, anchor="middle")
    svg.arrow(PAD + 80, y + 22, PAD + 96, y + 22, color=P["dim"])

    step_w = 82
    step_h = 46
    step_gap = 4
    steps = [
        ("s01", "Récup.\nOutlook", P["blue"]),
        ("s02", "Extraction\nIA ×3", P["purple"]),
        ("s03", "Routing\nNEW_PROJECT", P["purple"]),
        ("s04", "Tiers\nDolibarr", P["teal"]),
        ("s05", "Pièces\njointes", P["blue"]),
        ("s06", "Analyse\nimpression", P["orange"]),
        ("s07", "Lignes\ndevis", P["gold"]),
        ("s08", "Création\ndevis", P["teal"]),
        ("s09", "Upload\nPJ", P["teal"]),
        ("s10", "Agenda\nDolibarr", P["teal"]),
        ("s11", "Archivage\nOutlook", P["blue"]),
        ("s12", "Email\nréponse", P["ok"]),
    ]

    total_w = len(steps) * (step_w + step_gap) - step_gap
    sx = PAD + 97
    for i, (code, label, color) in enumerate(steps):
        bx = sx + i * (step_w + step_gap)
        svg.rect(bx, y, step_w, step_h, fill=P["card"], stroke=color, sw=1, rx=7)
        svg.text(bx + step_w//2, y + 13, code, fill=color, size=10, weight="700", anchor="middle")
        for j, part in enumerate(label.split("\n")):
            svg.text(bx + step_w//2, y + 25 + j * 12, part, fill=P["text"], size=9, anchor="middle")
        # arrow between steps
        if i < len(steps) - 1:
            ax = bx + step_w + 1
            svg.arrow(ax, y + step_h//2, ax + step_gap + 2, y + step_h//2, color=P["border"])

    # s03 gate annotation
    s3x = sx + 2 * (step_w + step_gap)
    svg.rect(s3x + 2, y + step_h + 4, step_w - 4, 16, fill="#1c1528", stroke=P["err"], sw=1, rx=4)
    svg.text(s3x + step_w//2, y + step_h + 14, "gate : NEW_PROJECT", fill=P["err"], size=8, anchor="middle")

    # s08 anti-doublon annotation
    s8x = sx + 7 * (step_w + step_gap)
    svg.rect(s8x + 2, y + step_h + 4, step_w - 4, 16, fill="#0f1c14", stroke=P["ok"], sw=1, rx=4)
    svg.text(s8x + step_w//2, y + step_h + 14, "anti-doublon marker", fill=P["ok"], size=8, anchor="middle")

    y += step_h + 40

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — CODE LAYERS (gauche) + MWP LAYERS (droite)
    # ══════════════════════════════════════════════════════════════════════════
    col_w = (W - PAD * 3) // 2
    lx = PAD
    rx = PAD * 2 + col_w

    svg.section_label(lx, y + 14, "02 — COUCHES CODE  ·  L0 → L7")
    svg.section_label(rx, y + 14, "03 — COUCHES CONTEXTE MWP  ·  L0 → L4")
    y += 24

    # Code layers
    code_layers = [
        ("L0", "Identité workspace", "CLAUDE.md · CONTEXT.md · CARNET.md", P["gold"]),
        ("L1", "Config & secrets", ".env · _config/*.md · src/config.py", P["warn"]),
        ("L2", "Connecteurs externes", "claude_client.py · dolibarr.py · outlook.py", P["purple"]),
        ("L3", "Middleware / Context", "context.py · pipeline.py", P["blue"]),
        ("L4", "Steps pipeline", "flux_a/steps.py · flux_b/steps.py", P["blue"]),
        ("L5", "Utils métier", "imposition.py · devis_builder.py · html_cleaner.py", P["teal"]),
        ("L6", "Engine & routing", "dispatcher.py · main.py", P["orange"]),
        ("L7", "Dashboard & API", "dashboard/app.py · index.html", P["ok"]),
    ]
    lh = 36
    lg = 4
    for i, (layer, title, files, color) in enumerate(code_layers):
        ly2 = y + i * (lh + lg)
        svg.rect(lx, ly2, col_w, lh, fill=P["card"], stroke=color, sw=1, rx=6)
        svg.rect(lx, ly2, 32, lh, fill=color, rx=6, opacity=0.15)
        svg.text(lx + 16, ly2 + lh//2 + 4, layer, fill=color, size=10, weight="700", anchor="middle")
        svg.text(lx + 40, ly2 + 14, title, fill=P["text"], size=11, weight="600")
        svg.text(lx + 40, ly2 + 27, files, fill=P["dim"], size=9)

    # MWP layers
    mwp_layers = [
        ("L0", "Identité", "Prompt système · nom du skill actif", P["gold"]),
        ("L1", "Routing tâches", "Description frontmatter · orchestrateur-inpressco", P["orange"]),
        ("L2", "Contrat d'étape", "Inputs · Process · Outputs · Verify · Gates", P["purple"]),
        ("L3", "Référentiels stables", "references/*.md · conventions Dolibarr · règles métier", P["blue"]),
        ("L4", "Artefacts du run", "Email entrant · données Dolibarr live · ctx.*", P["teal"]),
    ]
    mh = 56
    mg = 6
    for i, (layer, title, desc, color) in enumerate(mwp_layers):
        my2 = y + i * (mh + mg)
        svg.rect(rx, my2, col_w, mh, fill=P["card"], stroke=color, sw=1, rx=6)
        svg.rect(rx, my2, 32, mh, fill=color, rx=6, opacity=0.12)
        svg.text(rx + 16, my2 + mh//2 + 4, layer, fill=color, size=10, weight="700", anchor="middle")
        svg.text(rx + 40, my2 + 18, title, fill=P["text"], size=12, weight="600")
        svg.text(rx + 40, my2 + 34, desc, fill=P["dim"], size=10)

    section_h = max(len(code_layers) * (lh + lg), len(mwp_layers) * (mh + mg))
    y += section_h + 32

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — SKILLS ECOSYSTEM (30 skills)
    # ══════════════════════════════════════════════════════════════════════════
    svg.section_label(PAD, y + 14, "04 — SKILLS CLAUDE  ·  31 skills installés dans .claude/skills/")
    y += 24

    skill_categories = [
        ("SÉCURITÉ & QUALITÉ", P["err"], [
            ("droits-profils", "Porte d'entrée — profil CLIENT/TEAM/ADMIN"),
            ("validation-qc", "QC avant toute action irréversible"),
            ("gestion-erreurs", "Filet sécurité — retry, mode dégradé, log"),
            ("bdd-images-query", "Anti-doublon visuels — lecture seule assets"),
        ]),
        ("COMMERCE & CLIENT", P["orange"], [
            ("inpressco-commerce", "Expert imprimeur — devis, brief, finitions"),
            ("reponse-client", "Rédaction & envoi emails clients"),
            ("mail-routing", "8 catégories — NEW_PROJECT, SUPPLIER, ..."),
            ("analyse-sentiment", "Profil expéditeur — urgence, intention"),
            ("memoire-client", "CRM live — historique, préférences, alerts"),
            ("suivi-commande", "Statut commande — mise à jour & relance"),
        ]),
        ("DOLIBARR & DATA", P["teal"], [
            ("dolibarr-query", "CRUD Dolibarr — tiers, devis, factures, PJ"),
            ("controleur-gestion", "DAF — CA, tréso, impayés, marges, DSO"),
            ("analyse-transversale", "RFM, tendances, anomalies, mix produit"),
            ("chat-to-db", "Persistance conversations → Dolibarr"),
            ("agenda", "RDV, relances — Dolibarr ↔ Outlook 365"),
        ]),
        ("PRODUCTION & DOCS", P["blue"], [
            ("archiveur", "Nommage & dépôt — BAT, PJ, visuels, PDF"),
            ("generation-pdf", "PDF devis/factures — API Dolibarr + reportlab"),
            ("projets-artefacts", "Mémoire cross-sessions des productions"),
            ("charte-graphique", "Extraction & mémo charte client"),
        ]),
        ("IA & ARCHITECTURE", P["purple"], [
            ("orchestrateur", "Chef d'orchestre multi-skills"),
            ("architecte-ia", "CTO virtuel — review L0-L7 + MWP, correctifs"),
            ("ux-inpressco", "Composants React/HTML dashboard"),
            ("planche-archi", "Prompts Nanobanana — planches produit"),
            ("agent-acheteur", "RFQ fournisseurs — email par métier"),
            ("veille-prix", "Benchmark Exaprint / Pixartprinting"),
        ]),
    ]

    cat_w = (W - PAD * 2 - 16 * (len(skill_categories) - 1)) // len(skill_categories)
    pill_h = 38
    pill_gap = 5
    cat_pad = 10

    for ci, (cat_title, cat_color, skills) in enumerate(skill_categories):
        cx = PAD + ci * (cat_w + 16)
        cat_h = cat_pad * 2 + 24 + len(skills) * (pill_h + pill_gap)
        svg.rect(cx, y, cat_w, cat_h, fill=P["surface"], stroke=cat_color, sw=1, rx=10)
        svg.rect(cx, y, cat_w, 28, fill=cat_color, rx=10, opacity=0.18)
        svg.text(cx + cat_w//2, y + 17, cat_title, fill=cat_color, size=10, weight="700", anchor="middle")

        for si, (skill_name, skill_desc) in enumerate(skills):
            sy2 = y + 28 + cat_pad + si * (pill_h + pill_gap)
            svg.rect(cx + 8, sy2, cat_w - 16, pill_h, fill=P["card"], stroke=cat_color, sw=1, rx=6, opacity=0.8)
            svg.text(cx + 16, sy2 + 14, skill_name, fill=cat_color, size=10, weight="600")
            # wrap desc
            if len(skill_desc) > 32:
                half = skill_desc[:32].rfind(" ")
                if half == -1:
                    half = 32
                svg.text(cx + 16, sy2 + 27, skill_desc[:half], fill=P["dim"], size=8)
                svg.text(cx + 16, sy2 + 37, skill_desc[half+1:], fill=P["dim"], size=8)
            else:
                svg.text(cx + 16, sy2 + 27, skill_desc, fill=P["dim"], size=8)

    # Calculate max skill category height
    max_skills = max(len(s) for _, _, s in skill_categories)
    skills_h = cat_pad * 2 + 24 + max_skills * (pill_h + pill_gap)
    y += skills_h + 32

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — INTÉGRATIONS EXTERNES
    # ══════════════════════════════════════════════════════════════════════════
    svg.section_label(PAD, y + 14, "05 — INTÉGRATIONS EXTERNES")
    y += 24

    integrations = [
        ("Dolibarr CRM", "API REST · prod.in-pressco.com", "Tiers · Devis · Commandes · Factures · Agenda · PJ", P["teal"]),
        ("Claude API", "Anthropic · claude-opus-4-6 / haiku-4-5", "Extraction · Routing · Sentiment · Emails · Synthèses", P["purple"]),
        ("Outlook 365", "Microsoft Graph API · Azure AD", "Lecture emails · Envoi · Archivage · Dossiers Outlook", P["blue"]),
        ("n8n Workflows", "srv1196537.hstgr.cloud · 10 workflows", "WF3 SOLARIS · WF5 Tiers · WF7 Synchro · WF_DOLI Devis", P["orange"]),
        ("Dashboard", "FastAPI · uvicorn · port 8080", "14 endpoints · KPIs live · Chat IA · Upload assets", P["ok"]),
    ]

    int_w = (W - PAD * 2 - 12 * (len(integrations) - 1)) // len(integrations)
    int_h = 90

    for ii, (name, sub, detail, color) in enumerate(integrations):
        ix = PAD + ii * (int_w + 12)
        svg.rect(ix, y, int_w, int_h, fill=P["card"], stroke=color, sw=1, rx=8)
        svg.rect(ix, y, int_w, 26, fill=color, rx=8, opacity=0.16)
        svg.text(ix + int_w//2, y + 16, name, fill=color, size=12, weight="700", anchor="middle")
        svg.text(ix + 10, y + 38, sub, fill=P["dim"], size=9)
        # detail over 2 lines
        parts = detail.split(" · ")
        line1 = " · ".join(parts[:2])
        line2 = " · ".join(parts[2:])
        svg.text(ix + 10, y + 54, line1, fill=P["text"], size=9)
        if line2:
            svg.text(ix + 10, y + 67, line2, fill=P["text"], size=9)

    y += int_h + 32

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5 — PRINCIPES NON NÉGOCIABLES
    # ══════════════════════════════════════════════════════════════════════════
    svg.section_label(PAD, y + 14, "06 — PRINCIPES NON NÉGOCIABLES")
    y += 24

    principes = [
        ("Transparence", "Chaque action du système\nest lisible et traçable", P["blue"]),
        ("Sobriété", "Faire moins,\nmais le faire vraiment bien", P["teal"]),
        ("Humanité", "L'IA exécute.\nL'humain décide et pilote.", P["gold"]),
        ("Sécurité prod", "Dolibarr en prod — jamais\nde données test sans cleanup", P["err"]),
        ("Python pur", "Imposition calculée en Python,\njamais dans un prompt IA", P["orange"]),
    ]

    pr_w = (W - PAD * 2 - 12 * (len(principes) - 1)) // len(principes)
    pr_h = 72

    for pi, (title, desc, color) in enumerate(principes):
        px = PAD + pi * (pr_w + 12)
        svg.rect(px, y, pr_w, pr_h, fill=P["surface"], stroke=color, sw=1, rx=8)
        svg.rect(px, y, pr_w, 22, fill=color, rx=8, opacity=0.18)
        svg.text(px + pr_w//2, y + 14, title, fill=color, size=11, weight="700", anchor="middle")
        for di, part in enumerate(desc.split("\n")):
            svg.text(px + pr_w//2, y + 36 + di * 14, part, fill=P["dim"], size=9, anchor="middle")

    y += pr_h + 24

    # ── FOOTER ──────────────────────────────────────────────────────────────
    svg.line(0, y, W, y, stroke=P["border"], sw=1)
    y += 16
    svg.text(PAD, y + 12,
             "InPressco MWP — Architecture v1.0 — Généré le 28/03/2026 · tools/architecture_visual.py",
             fill=P["dim"], size=10)
    svg.text(W - PAD, y + 12,
             "Transparence · Sobriété · Humanité",
             fill=P["gold_dim"], size=10, anchor="end")

    return svg.finish()


def main():
    REPORTS_DIR.mkdir(exist_ok=True)
    svg_content = build()
    out = REPORTS_DIR / "ARCHITECTURE.svg"
    out.write_text(svg_content, encoding="utf-8")
    print(f"✅ Visuel architecture généré")
    print(f"   🖼  {out}")


if __name__ == "__main__":
    main()
