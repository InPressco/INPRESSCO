"""tools/strategic_synthesis.py — Intelligence stratégique InPressco.

Interroge Dolibarr en lecture seule, calcule les KPIs financiers et produit
une synthèse décisionnelle pour les dirigeants.

Sorties :
  - reports/STRATEGIC_SYNTHESIS.md   (rapport Markdown)
  - reports/STRATEGIC_SYNTHESIS.svg  (dashboard visuel)
  - FinancialSnapshot (dict) retourné par run_synthesis()

Usage :
  python main.py --synthesis
  python tools/strategic_synthesis.py [--no-files]

Principe : toujours retourner quelque chose, même en cas d'erreur Dolibarr.
          Jamais d'exception propagée. Mode dégradé explicite.
"""
from __future__ import annotations

import asyncio
import json
import os
import xml.etree.ElementTree as ET
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


# ─────────────────────────────────────────────────────────────────────────────
# TYPES
# ─────────────────────────────────────────────────────────────────────────────

class RFMSegment(TypedDict):
    socid:        int
    name:         str
    recency_days: int
    frequency:    int
    monetary_ht:  float
    segment:      str


class Projection(TypedDict):
    scenario:    str
    ca_90j_ht:   float
    hypotheses:  list[str]


class WellbeingStatus(TypedDict):
    status:   str   # "tout va bien" | "attention" | "vigilance"
    message:  str
    alerts:   list[str]
    color:    str


class FinancialSnapshot(TypedDict):
    generated_at:      str
    mode:              str   # "live" | "degraded"
    ca_mois_ht:        float
    ca_mois_prec_ht:   float
    evolution_pct:     float | None
    impayes_total_ht:  float
    impayes_count:     int
    dso_days:          float
    health_score:      int
    pipe_ht:           float
    pipe_count:        int
    taux_conversion_pct: float | None
    projections:       list[Projection]
    rfm_segments:      list[RFMSegment]
    wellbeing:         WellbeingStatus
    top_clients:       list[dict]


# ─────────────────────────────────────────────────────────────────────────────
# DOLIBARR — FETCH (lecture seule, tolérant aux erreurs)
# ─────────────────────────────────────────────────────────────────────────────

_BASE = os.environ.get("DOLIBARR_BASE_URL", "")
_KEY  = os.environ.get("DOLIBARR_API_KEY", "")
_HEADERS = {"DOLAPIKEY": _KEY, "Accept": "application/json"}


async def _doli_get(path: str, params: dict | None = None) -> list | dict:
    """GET Dolibarr — retourne [] ou {} en cas d'erreur, jamais d'exception."""
    if not _BASE or not _KEY:
        return []
    try:
        import httpx
        url = f"{_BASE}{path}"
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=_HEADERS, params=params or {})
        if r.status_code == 200:
            return r.json()
        return []
    except Exception:
        return []


async def _fetch_all_invoices() -> list:
    """Pagine /invoices jusqu'à épuisement (tolérant aux erreurs)."""
    all_inv: list[dict] = []
    for page in range(0, 10):  # max 10 pages = 5000 factures
        batch = await _doli_get("/invoices", {"limit": 500, "page": page})
        if not isinstance(batch, list) or not batch:
            break
        all_inv.extend(batch)
        if len(batch) < 500:
            break  # dernière page
    return all_inv


async def _fetch_all() -> dict:
    """Fetch parallèle : factures (paginées), devis, commandes."""
    invoices_task = _fetch_all_invoices()
    proposals_task = _doli_get("/proposals", {"limit": 500})
    orders_task    = _doli_get("/orders",    {"limit": 500})

    invoices, proposals, orders = await asyncio.gather(
        invoices_task, proposals_task, orders_task,
        return_exceptions=True,
    )
    return {
        "invoices":  invoices if isinstance(invoices, list) else [],
        "proposals": proposals if isinstance(proposals, list) else [],
        "orders":    orders if isinstance(orders, list) else [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

def _ts(epoch_str) -> float:
    """Convertit un timestamp Dolibarr (int/str) en float."""
    try:
        return float(epoch_str)
    except (TypeError, ValueError):
        return 0.0


def _this_month_bounds() -> tuple[float, float]:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month_end = start.timestamp() - 1
    if now.month == 1:
        prev_start = now.replace(year=now.year - 1, month=12, day=1,
                                 hour=0, minute=0, second=0, microsecond=0)
    else:
        prev_start = now.replace(month=now.month - 1, day=1,
                                 hour=0, minute=0, second=0, microsecond=0)
    return (start.timestamp(), now.timestamp(),
            prev_start.timestamp(), prev_month_end)


def _statut(inv: dict) -> int:
    """Normalise le champ statut Dolibarr (retourné en str ou int) en int."""
    try:
        return int(inv.get("statut", -99) or -99)
    except (TypeError, ValueError):
        return -99


def compute_ca(invoices: list[dict]) -> tuple[float, float]:
    """Retourne (CA mois courant HT, CA mois précédent HT) depuis factures validées."""
    (s, e, ps, pe) = _this_month_bounds()
    ca_curr = sum(
        float(inv.get("total_ht", 0) or 0)
        for inv in invoices
        if _statut(inv) in (1, 2) and s <= _ts(inv.get("date", 0)) <= e
    )
    ca_prev = sum(
        float(inv.get("total_ht", 0) or 0)
        for inv in invoices
        if _statut(inv) in (1, 2) and ps <= _ts(inv.get("date", 0)) <= pe
    )
    return ca_curr, ca_prev


def compute_impayes(invoices: list[dict]) -> tuple[float, int]:
    """Retourne (total impayé HT, nombre) depuis factures statut=1."""
    items = [
        inv for inv in invoices
        if _statut(inv) == 1 and float(inv.get("remaintopay", 0) or 0) > 0
    ]
    total = sum(float(inv.get("remaintopay", 0) or 0) for inv in items)
    return total, len(items)


def compute_dso(invoices: list[dict]) -> float:
    """Days Sales Outstanding = (impayés / CA annuel) × 365."""
    now_ts  = datetime.now(timezone.utc).timestamp()
    year_ts = now_ts - 365 * 86400
    ca_year = sum(
        float(inv.get("total_ht", 0) or 0)
        for inv in invoices
        if _statut(inv) in (1, 2) and _ts(inv.get("date", 0)) > year_ts
    )
    impayes, _ = compute_impayes(invoices)
    if ca_year <= 0:
        return 0.0
    return round(impayes / ca_year * 365, 1)


def compute_pipe(proposals: list[dict]) -> tuple[float, int]:
    """Devis ouverts (statut 0 ou 1) — total HT et nombre."""
    open_props = [p for p in proposals if _statut(p) in (0, 1)]
    total = sum(float(p.get("total_ht", 0) or 0) for p in open_props)
    return total, len(open_props)


def compute_conversion(proposals: list[dict], orders: list[dict]) -> float | None:
    """Taux de conversion devis → commande (30 derniers jours)."""
    cutoff = datetime.now(timezone.utc).timestamp() - 30 * 86400
    recent_props = [p for p in proposals if _ts(p.get("date_creation", 0)) > cutoff]
    if not recent_props:
        return None
    # Commandes liées à des devis récents (devis signés = statut 2)
    converted = sum(1 for p in recent_props if _statut(p) == 2)
    return round(converted / len(recent_props) * 100, 1)


def compute_rfm(invoices: list[dict]) -> list[RFMSegment]:
    """Segmentation RFM par client depuis les factures payées."""
    now_ts   = datetime.now(timezone.utc).timestamp()
    year_ts  = now_ts - 365 * 86400
    by_socid: dict[str, dict] = {}

    for inv in invoices:
        if _statut(inv) != 2:  # payées seulement
            continue
        socid = str(inv.get("socid", ""))
        name  = inv.get("socnom", "") or inv.get("name", "") or f"Tiers {socid}"
        ts    = _ts(inv.get("date", 0))
        ht    = float(inv.get("total_ht", 0) or 0)
        if socid not in by_socid:
            by_socid[socid] = {"name": name, "last_ts": ts, "freq": 0, "monetary": 0.0}
        entry = by_socid[socid]
        entry["last_ts"]  = max(entry["last_ts"], ts)
        if ts > year_ts:
            entry["freq"]     += 1
            entry["monetary"] += ht

    segments: list[RFMSegment] = []
    for socid, d in list(by_socid.items())[:20]:  # top 20
        recency = int((now_ts - d["last_ts"]) / 86400)
        freq    = d["freq"]
        monetary = d["monetary"]

        if recency < 60 and freq >= 3 and monetary > 5000:
            seg = "CHAMPION"
        elif recency < 120 and freq >= 2:
            seg = "FIDÈLE"
        elif recency < 90 and freq == 1:
            seg = "PROMETTEUR"
        elif 120 <= recency <= 365 and freq >= 2:
            seg = "À_RISQUE"
        elif recency > 365:
            seg = "PERDU"
        else:
            seg = "PROSPECT"

        segments.append(RFMSegment(
            socid=int(socid) if socid.isdigit() else 0,
            name=d["name"],
            recency_days=recency,
            frequency=freq,
            monetary_ht=round(monetary, 2),
            segment=seg,
        ))

    return sorted(segments, key=lambda x: x["monetary_ht"], reverse=True)


def compute_health_score(
    ca_curr: float, ca_prev: float,
    impayes: float, dso: float,
    taux_conv: float | None,
) -> int:
    score = 20  # base

    # CA trend
    if ca_prev > 0:
        trend = (ca_curr - ca_prev) / ca_prev * 100
        if trend >= 0:
            score += 20
        elif trend >= -20:
            score += 5
        else:
            score -= 10

    # DSO
    if dso <= 30:
        score += 20
    elif dso <= 45:
        score += 10
    elif dso > 60:
        score -= 20

    # Impayés / CA
    ca_ref = ca_curr or ca_prev or 1
    imp_pct = impayes / ca_ref * 100
    if imp_pct < 5:
        score += 20
    elif imp_pct < 20:
        score += 5
    else:
        score -= 20

    # Conversion
    if taux_conv is not None:
        if taux_conv >= 50:
            score += 20
        elif taux_conv >= 30:
            score += 10
        elif taux_conv < 20:
            score -= 10

    return max(0, min(100, score))


def compute_projections(
    ca_curr: float, ca_prev: float,
    pipe_ht: float, taux_conv: float | None,
) -> list[Projection]:
    trend = (ca_curr / ca_prev) if ca_prev > 0 else 1.0
    tc    = (taux_conv or 40) / 100

    return [
        Projection(
            scenario="optimiste",
            ca_90j_ht=round(ca_curr * 3 * trend * 1.15 + pipe_ht * 0.6, 0),
            hypotheses=["Trend maintenu +15%", "60% du pipe converti", "Saison favorable"],
        ),
        Projection(
            scenario="base",
            ca_90j_ht=round(ca_curr * 3 * trend + pipe_ht * tc, 0),
            hypotheses=["Trend historique maintenu", f"Taux conversion {tc*100:.0f}%"],
        ),
        Projection(
            scenario="pessimiste",
            ca_90j_ht=round(ca_curr * 3 * trend * 0.85 + pipe_ht * 0.25, 0),
            hypotheses=["Ralentissement -15%", "25% du pipe converti", "Risques impayés"],
        ),
    ]


def compute_wellbeing(score: int, dso: float, impayes: float) -> WellbeingStatus:
    alerts: list[str] = []
    if dso > 60:
        alerts.append(f"DSO élevé : {dso:.0f} jours (seuil 45j)")
    if dso > 45:
        alerts.append(f"DSO à surveiller : {dso:.0f} jours")
    if impayes > 10000:
        alerts.append(f"Impayés significatifs : {impayes:,.0f} € HT")

    if score >= 70:
        return WellbeingStatus(
            status="tout va bien",
            message="L'activité est saine. Continuez sur cette lancée.",
            alerts=alerts,
            color="#22c55e",
        )
    elif score >= 40:
        return WellbeingStatus(
            status="attention",
            message="Quelques signaux à surveiller. Pas d'urgence, mais agissez.",
            alerts=alerts,
            color="#f59e0b",
        )
    else:
        return WellbeingStatus(
            status="vigilance",
            message="Plusieurs indicateurs dégradés. Action requise.",
            alerts=alerts,
            color="#ef4444",
        )


def _top_clients(rfm: list[RFMSegment], n: int = 5) -> list[dict]:
    return [
        {"name": s["name"], "segment": s["segment"],
         "ca_ht": s["monetary_ht"], "recency_days": s["recency_days"]}
        for s in rfm[:n]
    ]


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION RAPPORT MARKDOWN
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_eur(val: float) -> str:
    return f"{val:,.0f} €".replace(",", " ")


def generate_synthesis_md(snap: FinancialSnapshot) -> str:
    wb = snap["wellbeing"]
    now = snap["generated_at"][:16].replace("T", " ")

    proj_rows = "\n".join(
        f"| {p['scenario'].capitalize()} | {_fmt_eur(p['ca_90j_ht'])} | "
        f"{' · '.join(p['hypotheses'])} |"
        for p in snap["projections"]
    )

    rfm_rows = "\n".join(
        f"| {s['name'][:25]} | {s['segment']} | {s['recency_days']}j | "
        f"{s['frequency']} | {_fmt_eur(s['monetary_ht'])} |"
        for s in snap["rfm_segments"][:8]
    )

    alerts_md = ("\n".join(f"- ⚠️  {a}" for a in wb["alerts"])
                 if wb["alerts"] else "- Aucune alerte active")

    mode_label = "" if snap["mode"] == "live" else " *(mode dégradé — Dolibarr inaccessible)*"

    return f"""# SYNTHÈSE STRATÉGIQUE — InPressco{mode_label}

> Générée le {now} UTC

---

## 🎯 État général — {wb["status"].upper()}

> **{wb["message"]}**

{alerts_md}

---

## 📊 KPIs du mois

| Indicateur | Valeur |
|------------|--------|
| CA mois courant HT | {_fmt_eur(snap["ca_mois_ht"])} |
| CA mois précédent HT | {_fmt_eur(snap["ca_mois_prec_ht"])} |
| Évolution | {f"{snap['evolution_pct']:+.1f}%" if snap["evolution_pct"] is not None else "—"} |
| Impayés | {_fmt_eur(snap["impayes_total_ht"])} ({snap["impayes_count"]} facture(s)) |
| DSO | {snap["dso_days"]} jours |
| Pipeline ouvert | {_fmt_eur(snap["pipe_ht"])} ({snap["pipe_count"]} devis) |
| Taux conversion 30j | {f"{snap['taux_conversion_pct']}%" if snap["taux_conversion_pct"] is not None else "—"} |
| Score santé | **{snap["health_score"]}/100** |

---

## 📈 Projections 90 jours

| Scénario | CA 90j HT | Hypothèses |
|----------|-----------|------------|
{proj_rows}

---

## 👥 Segments clients (RFM)

| Client | Segment | Dernière cmd | Fréquence | CA HT |
|--------|---------|--------------|-----------|-------|
{rfm_rows}

---

## 💚 Bien-être dirigeant

**Statut** : `{wb["status"]}`
**Message** : {wb["message"]}

---

*Données live Dolibarr. Pour régénérer : `python main.py --synthesis`*
"""


# ─────────────────────────────────────────────────────────────────────────────
# GÉNÉRATION SVG
# ─────────────────────────────────────────────────────────────────────────────

def generate_synthesis_svg(snap: FinancialSnapshot) -> str:
    wb    = snap["wellbeing"]
    score = snap["health_score"]
    W, H  = 900, 600
    svg   = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                       width=str(W), height=str(H), viewBox=f"0 0 {W} {H}")

    def rect(x, y, w, h, fill, rx=8, stroke="", sw=0):
        a = dict(x=str(x), y=str(y), width=str(w), height=str(h), fill=fill, rx=str(rx))
        if stroke:
            a.update({"stroke": stroke, "stroke-width": str(sw)})
        ET.SubElement(svg, "rect", **a)

    def text(x, y, s, fill="#f1f5f9", sz=13, fw="normal", anchor="start"):
        el = ET.SubElement(svg, "text", x=str(x), y=str(y), fill=fill,
                           **{"font-size": str(sz), "font-weight": fw,
                              "text-anchor": anchor,
                              "font-family": "Inter, -apple-system, sans-serif"})
        el.text = str(s)

    # Fond
    rect(0, 0, W, H, "#0f172a", rx=0)

    # Header
    rect(0, 0, W, 65, "#1e293b", rx=0)
    text(24, 28, "INPRESSCO", fill="#C9A96E", sz=12, fw="600")
    text(24, 48, "SYNTHÈSE STRATÉGIQUE", fill="#f1f5f9", sz=18, fw="700")
    text(W - 24, 28, snap["generated_at"][:10], fill="#94a3b8", sz=12, anchor="end")
    text(W - 24, 48, wb["status"].upper(), fill=wb["color"], sz=14, fw="700", anchor="end")

    # 4 KPI cards
    kpis = [
        ("CA mois", _fmt_eur(snap["ca_mois_ht"]), "#3b82f6"),
        ("DSO", f"{snap['dso_days']}j", "#f59e0b" if snap["dso_days"] > 45 else "#22c55e"),
        ("Impayés", _fmt_eur(snap["impayes_total_ht"]), "#ef4444" if snap["impayes_total_ht"] > 5000 else "#22c55e"),
        ("Conversion", f"{snap['taux_conversion_pct'] or '—'}%", "#a855f7"),
    ]
    for i, (label, value, color) in enumerate(kpis):
        cx = 30 + i * 215
        rect(cx, 85, 200, 80, "#1e293b", rx=10, stroke=color, sw=1)
        text(cx + 12, 108, label, fill="#94a3b8", sz=12)
        text(cx + 12, 138, value, fill=color, sz=20, fw="700")

    # Projections
    rect(30, 185, W - 60, 140, "#1e293b", rx=10)
    text(50, 210, "Projections 90 jours", fill="#C9A96E", sz=13, fw="600")
    proj_colors = ["#22c55e", "#3b82f6", "#ef4444"]
    max_proj = max((p["ca_90j_ht"] for p in snap["projections"]), default=1) or 1
    for i, (proj, pcolor) in enumerate(zip(snap["projections"], proj_colors)):
        py = 220 + i * 38
        bar_w = int((W - 130) * min(proj["ca_90j_ht"] / max_proj, 1))
        rect(50, py, W - 120, 28, "#0f172a", rx=6)
        if bar_w > 0:
            rect(50, py, bar_w, 28, pcolor, rx=6)
        text(56, py + 18, proj["scenario"].capitalize(), fill="#f1f5f9", sz=11, fw="600")
        text(W - 70, py + 18, _fmt_eur(proj["ca_90j_ht"]), fill=pcolor, sz=11, fw="700", anchor="end")

    # RFM top clients
    rect(30, 345, W - 60, 180, "#1e293b", rx=10)
    text(50, 370, "Top clients — Segments RFM", fill="#C9A96E", sz=13, fw="600")
    seg_colors = {
        "CHAMPION": "#22c55e", "FIDÈLE": "#3b82f6", "PROMETTEUR": "#a855f7",
        "À_RISQUE": "#f59e0b", "PERDU": "#ef4444", "PROSPECT": "#94a3b8",
    }
    for i, seg in enumerate(snap["rfm_segments"][:5]):
        ry = 380 + i * 28
        sc = seg_colors.get(seg["segment"], "#94a3b8")
        text(50, ry, seg["name"][:22], fill="#f1f5f9", sz=11)
        text(320, ry, seg["segment"], fill=sc, sz=11, fw="600")
        text(480, ry, f"{seg['recency_days']}j", fill="#94a3b8", sz=11)
        text(560, ry, _fmt_eur(seg["monetary_ht"]), fill=sc, sz=11, fw="600")

    # Wellbeing banner
    rect(30, 540, W - 60, 42, wb["color"] + "22", rx=8, stroke=wb["color"], sw=1)
    text(50, 566, f"💚 {wb['message']}", fill=wb["color"], sz=12, fw="600")

    ET.indent(svg, space="  ")
    return ET.tostring(svg, encoding="unicode")


# ─────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

async def run_synthesis(
    output_dir:     Path | None = None,
    trigger_report: bool = True,
) -> FinancialSnapshot:
    """Calcule et retourne le FinancialSnapshot. Jamais d'exception propagée."""
    if output_dir is None:
        output_dir = REPORTS_DIR
    output_dir.mkdir(exist_ok=True)

    try:
        raw = await _fetch_all()
        invoices  = raw["invoices"]
        proposals = raw["proposals"]
        orders    = raw["orders"]
        mode      = "live" if (invoices or proposals) else "degraded"
    except Exception:
        invoices = proposals = orders = []
        mode = "degraded"

    ca_curr, ca_prev  = compute_ca(invoices)
    impayes, imp_cnt  = compute_impayes(invoices)
    dso               = compute_dso(invoices)
    pipe_ht, pipe_cnt = compute_pipe(proposals)
    taux_conv         = compute_conversion(proposals, orders)
    rfm               = compute_rfm(invoices)
    score             = compute_health_score(ca_curr, ca_prev, impayes, dso, taux_conv)
    projections       = compute_projections(ca_curr, ca_prev, pipe_ht, taux_conv)
    wellbeing         = compute_wellbeing(score, dso, impayes)

    evol = round((ca_curr - ca_prev) / ca_prev * 100, 1) if ca_prev > 0 else None

    snap = FinancialSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        ca_mois_ht=round(ca_curr, 2),
        ca_mois_prec_ht=round(ca_prev, 2),
        evolution_pct=evol,
        impayes_total_ht=round(impayes, 2),
        impayes_count=imp_cnt,
        dso_days=dso,
        health_score=score,
        pipe_ht=round(pipe_ht, 2),
        pipe_count=pipe_cnt,
        taux_conversion_pct=taux_conv,
        projections=projections,
        rfm_segments=rfm,
        wellbeing=wellbeing,
        top_clients=_top_clients(rfm),
    )

    if trigger_report:
        try:
            md = generate_synthesis_md(snap)
            (output_dir / "STRATEGIC_SYNTHESIS.md").write_text(md, encoding="utf-8")
            svg = generate_synthesis_svg(snap)
            (output_dir / "STRATEGIC_SYNTHESIS.svg").write_text(svg, encoding="utf-8")
        except Exception:
            pass  # rapports optionnels

        # Enregistre l'intention
        try:
            from tools.intent_tracker import record_intent
            record_intent(
                action="synthesis_generated",
                description=f"Synthèse stratégique — score {score}/100 — {wellbeing['status']}",
                category="stratégique",
                actor="tools",
                context={"score": score, "mode": mode, "ca_mois": ca_curr},
                outcome="success",
            )
        except Exception:
            pass

    return snap


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-files", action="store_true",
                        help="Calcule sans écrire les fichiers rapport")
    args = parser.parse_args()

    snap = asyncio.run(run_synthesis(trigger_report=not args.no_files))

    wb = snap["wellbeing"]
    print(f"\n{'='*55}")
    print(f"  SYNTHÈSE STRATÉGIQUE INPRESSCO")
    print(f"  {snap['generated_at'][:16]} UTC — Mode : {snap['mode'].upper()}")
    print(f"{'='*55}")
    print(f"  Score santé    : {snap['health_score']}/100")
    print(f"  État           : {wb['status'].upper()}")
    print(f"  CA mois HT     : {_fmt_eur(snap['ca_mois_ht'])}")
    print(f"  Impayés        : {_fmt_eur(snap['impayes_total_ht'])} ({snap['impayes_count']} fact.)")
    print(f"  DSO            : {snap['dso_days']} jours")
    print(f"  Pipeline       : {_fmt_eur(snap['pipe_ht'])} ({snap['pipe_count']} devis)")
    if snap["taux_conversion_pct"] is not None:
        print(f"  Conversion 30j : {snap['taux_conversion_pct']}%")
    print(f"\n  {wb['message']}")
    if wb["alerts"]:
        for a in wb["alerts"]:
            print(f"  ⚠️  {a}")
    print(f"{'='*55}\n")

    if not args.no_files:
        print(f"  📄 {REPORTS_DIR}/STRATEGIC_SYNTHESIS.md")
        print(f"  🖼  {REPORTS_DIR}/STRATEGIC_SYNTHESIS.svg")
