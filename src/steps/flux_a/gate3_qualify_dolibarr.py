"""steps/flux_a/gate3_qualify_dolibarr.py — Gate 3 : qualification Dolibarr avant create_proposal.

Vérifie 3 conditions AVANT de créer quoi que ce soit dans Dolibarr :
  1. Client identifié (socid != DOLIBARR_SOCID_INCONNU)
  2. Pas de devis ouvert en doublon (même socid + nom projet similaire ≥ 80%)
  3. Lignes devis construites (devis_lines non vide)

Si un check échoue :
  - check 1 → event ⏸ "client inconnu" créé en Dolibarr + StopPipeline
  - check 2 → routing_category = PROJECT_UPDATE + StopPipeline (silencieux)
  - check 3 → event ⏸ "lignes vides" créé en Dolibarr + StopPipeline
"""
import difflib
import logging

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline

logger = logging.getLogger(__name__)

# Seuil similarité fuzzy nom projet (0.0 → 1.0)
_FUZZY_THRESHOLD = 0.80

# Statuts "ouverts" : brouillon=0, ouvert=1
_STATUTS_OUVERTS = {0, 1}


def _fuzzy_match(a: str, b: str) -> float:
    """Score similarité entre 2 chaînes (SequenceMatcher, insensible à la casse)."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


async def gate3_qualify_dolibarr(ctx: Context) -> None:
    """
    Gate 3 : 3 checks Dolibarr avant create_proposal.
    Raise StopPipeline si l'un des checks échoue.
    """
    doli = DolibarrClient()

    # ── Check 1 : Client identifié ────────────────────────────────────────
    if not ctx.socid or ctx.socid == config.DOLIBARR_SOCID_INCONNU:
        try:
            await doli.create_agenda_event({
                "label": (
                    f"⏸ validation-qc — client inconnu — "
                    f"{(ctx.email_subject or '')[:80]}"
                ),
                "note": (
                    f"Email entrant sans client identifiable.\n"
                    f"Expéditeur : {ctx.email_sender_address}\n"
                    f"Sujet : {ctx.email_subject}\n"
                    f"Projet détecté : {ctx.nom_projet or '?'}\n"
                    f"Action requise : identifier le client et relancer le pipeline."
                ),
                "datep": 0,
                "datef": 0,
                "fk_element": 0,
                "elementtype": "societe",
                "type_code": "AC_OTH",
                "userownerid": config.DOLIBARR_USER_OWNER_ID,
                "fk_soc": config.DOLIBARR_SOCID_INCONNU,
                "done": 0,
            })
        except Exception as e:
            logger.warning(f"gate3[check1]: échec création event ⏸ client inconnu → {e}")

        raise StopPipeline(
            f"gate3[check1]: socid inconnu (={ctx.socid}) — event ⏸ créé"
        )

    # ── Check 2 : Doublon devis ouvert pour ce client ─────────────────────
    if ctx.nom_projet:
        try:
            proposals = await doli.list_proposals_by_socid(
                ctx.socid,
                limit=5,
                statuts=_STATUTS_OUVERTS,
            )
            for prop in proposals:
                existing_name = (
                    (prop.get("array_options") or {}).get("options_fhp_project_name")
                    or prop.get("titre", "")
                    or ""
                )
                score = _fuzzy_match(ctx.nom_projet, existing_name)
                if score >= _FUZZY_THRESHOLD:
                    existing_ref = prop.get("ref", "?")
                    ctx.routing_category = "PROJECT_UPDATE"
                    logger.info(
                        f"gate3[check2]: doublon — devis {existing_ref!r} "
                        f"(similarité={score:.0%}, nom={existing_name!r}) "
                        f"→ routing PROJECT_UPDATE"
                    )
                    raise StopPipeline(
                        f"gate3[check2]: devis ouvert {existing_ref!r} "
                        f"similaire à {ctx.nom_projet!r} ({score:.0%})"
                    )
        except StopPipeline:
            raise
        except Exception as e:
            logger.warning(
                f"gate3[check2]: vérification doublons échouée (non-bloquant) → {e}"
            )

    # ── Check 3 : Lignes devis construites ───────────────────────────────
    if not ctx.devis_lines:
        try:
            await doli.create_agenda_event({
                "label": (
                    f"⏸ validation-qc — lignes devis vides — "
                    f"{(ctx.email_subject or '')[:80]}"
                ),
                "note": (
                    f"Le pipeline n'a pas pu construire de lignes devis.\n"
                    f"Client : {ctx.soc_nom or '?'} (socid={ctx.socid})\n"
                    f"Projet : {ctx.nom_projet or '?'}\n"
                    f"Action requise : analyser l'email et créer le devis manuellement."
                ),
                "datep": 0,
                "datef": 0,
                "fk_element": ctx.socid or 0,
                "elementtype": "societe",
                "type_code": "AC_OTH",
                "userownerid": config.DOLIBARR_USER_OWNER_ID,
                "fk_soc": ctx.socid,
                "done": 0,
            })
        except Exception as e:
            logger.warning(f"gate3[check3]: échec création event ⏸ lignes vides → {e}")

        raise StopPipeline(
            f"gate3[check3]: devis_lines vide pour socid={ctx.socid} — event ⏸ créé"
        )

    logger.debug(
        f"gate3: qualifié — socid={ctx.socid}, "
        f"{len(ctx.devis_lines)} lignes, projet={ctx.nom_projet!r}"
    )
