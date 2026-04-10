"""steps/flux_a/gate1_disqualify.py — Gate 1 : filtre disqualification email.

Vérifie 8 cas qui rendent l'email non-actionnable AVANT toute action Dolibarr.
Raise StopPipeline si l'email doit être ignoré.

Cas couverts (contrôlables depuis ctx sans appel API) :
  1. Sujet RE: / FW: / FWD: → réponse à un thread existant
  2. Corps court (< 50 mots) + signal d'acquittement → accusé de réception
  3. Hors-bureau / réponse automatique (corps ou sujet)
  4. Expéditeur InPressco interne
  5. Newsletter / email marketing (signaux unsubscribe)
  6. Corps vide ou non-parseable (< 20 chars nettoyés)
  7. Intention email = réclamation ou relance (champ email_sentiment.intention)
  8. Sujet hors-bureau explicite
"""
import logging
import re

from src import config
from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline

logger = logging.getLogger(__name__)

# ── Signaux accusé de réception (phrases composées — évite les faux positifs) ──
_ACK_SIGNALS = frozenset({
    "bien reçu", "bien noté", "parfait merci", "merci pour votre",
    "bonne réception", "message bien reçu", "j'ai bien reçu",
    "nous avons bien reçu", "accusé de réception",
})

# ── Signaux hors-bureau (corps) ────────────────────────────────────────────────
_OOO_BODY_SIGNALS = frozenset({
    "absent du bureau", "out of office", "en déplacement", "sera absent",
    "réponse automatique", "automatic reply", "auto-reply", "autoreply",
    "will be out", "je suis absent", "serai de retour", "will return",
    "je suis en vacances", "on holiday", "on vacation",
})

# ── Signaux newsletter / marketing ────────────────────────────────────────────
_NEWSLETTER_SIGNALS = frozenset({
    "se désabonner", "unsubscribe", "désabonnement",
    "ne plus recevoir ces", "gérer vos préférences", "manage preferences",
})


async def gate1_disqualify(ctx: Context) -> None:
    """
    Filtre disqualification — 8 cas. Raise StopPipeline si non-actionnable.
    Ne fait aucun appel API.
    """
    subject = ctx.email_subject or ""
    body    = ctx.email_body or ""
    sender  = ctx.email_sender_address or ""

    subject_lower = subject.lower()
    body_lower    = body.lower()

    # ── Cas 1 : Réponse / transfert (RE: / FW: / FWD:) ───────────────────
    if re.match(r'^\s*(RE|FW|FWD)\s*:', subject, re.IGNORECASE):
        ctx.routing_category = "PROJECT_UPDATE"
        raise StopPipeline(
            f"gate1[cas1]: sujet RE:/FW: → routing PROJECT_UPDATE — {subject[:80]!r}"
        )

    # ── Cas 8 : Sujet hors-bureau explicite ───────────────────────────────
    if re.search(r'(absent|out of office|réponse automatique|automatic reply)', subject_lower):
        raise StopPipeline(
            f"gate1[cas8]: sujet hors-bureau détecté — {subject[:80]!r}"
        )

    # ── Cas 4 : Expéditeur InPressco interne ─────────────────────────────
    if sender and any(excl in sender for excl in config.INPRESSCO_EXCLUDE_EMAILS):
        raise StopPipeline(
            f"gate1[cas4]: expéditeur interne InPressco — {sender!r}"
        )

    # ── Cas 6 : Corps vide ou non-parseable ──────────────────────────────
    body_clean = re.sub(r'\s+', '', body)
    if len(body_clean) < 20:
        raise StopPipeline(
            f"gate1[cas6]: corps email vide ou trop court "
            f"({len(body_clean)} chars après nettoyage)"
        )

    # ── Cas 3 : Hors-bureau (corps) ───────────────────────────────────────
    if any(sig in body_lower for sig in _OOO_BODY_SIGNALS):
        raise StopPipeline("gate1[cas3]: hors-bureau / réponse automatique détectée dans le corps")

    # ── Cas 2 : Accusé de réception court ─────────────────────────────────
    word_count = len(body.split())
    if word_count < 50 and any(sig in body_lower for sig in _ACK_SIGNALS):
        raise StopPipeline(
            f"gate1[cas2]: accusé de réception / remerciement court "
            f"({word_count} mots) — DISQUALIFIED"
        )

    # ── Cas 5 : Newsletter / email marketing ─────────────────────────────
    if any(sig in body_lower for sig in _NEWSLETTER_SIGNALS):
        raise StopPipeline("gate1[cas5]: newsletter / email marketing détecté")

    # ── Cas 7 : Intention réclamation ou relance (enrichie par s02) ───────
    intention = (ctx.email_sentiment or {}).get("intention", "")
    if intention in {"réclamation", "relance"}:
        ctx.routing_category = "PROJECT_UPDATE"
        raise StopPipeline(
            f"gate1[cas7]: intention={intention!r} → routing PROJECT_UPDATE"
        )

    logger.debug(
        f"gate1: email qualifié — {subject[:60]!r} "
        f"({word_count} mots, sender={sender!r})"
    )
