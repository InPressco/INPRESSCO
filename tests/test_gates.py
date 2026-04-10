"""tests/test_gates.py — Tests unitaires Gate 1, Gate 3, Gate 4.

Aucun appel API réel — mocks uniquement.

Usage :
    pytest tests/test_gates.py -v
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

import pytest

# ── Setup path ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

os.environ.setdefault("ANTHROPIC_API_KEY",    "dummy")
os.environ.setdefault("DOLIBARR_API_KEY",     "dummy")
os.environ.setdefault("OUTLOOK_TENANT_ID",    "dummy")
os.environ.setdefault("OUTLOOK_CLIENT_ID",    "dummy")
os.environ.setdefault("OUTLOOK_CLIENT_SECRET","dummy")
os.environ.setdefault("OUTLOOK_USER_EMAIL",   "nicolas@in-pressco.com")

from src.middleware.context import Context
from src.middleware.pipeline import StopPipeline
from src.steps.flux_a.gate1_disqualify import gate1_disqualify
from src.steps.flux_a.gate3_qualify_dolibarr import gate3_qualify_dolibarr
from src.steps.flux_a.s13_send_email_client import s13_send_email_client


def _ctx(**kwargs) -> Context:
    """Crée un Context avec des valeurs par défaut valides."""
    defaults = {
        "email_id":             "test-email-001",
        "email_subject":        "Demande de devis cartes de visite",
        "email_sender_address": "client@exemple.fr",
        "email_body":           (
            "Bonjour, nous souhaitons commander des cartes de visite pour notre équipe commerciale. "
            "Format souhaité : 85x55mm recto/verso, papier 350g couché mat, pelliculage mat. "
            "Quantité : 1000 exemplaires. Nous avons besoin d'une livraison avant fin avril. "
            "Pourriez-vous nous faire une offre détaillée avec délai de production ? "
            "Nos fichiers sont prêts en PDF haute définition. Cordialement."
        ),
        "email_sentiment":      {"sentiment": "positif", "urgence": "faible", "intention": "demande_devis"},
        "routing_category":     "NEW_PROJECT",
        "devis_ref":            "PROV-2026-0042",
        "devis_id":             42,
        "socid":                100,
        "soc_nom":              "Exemple SARL",
        "nom_projet":           "Cartes de visite",
        "client_created":       False,
        "composants_isoles":    [],
        "devis_lines":          [{"product_type": 0, "qty": 1000, "subprice": 150.0}],
    }
    defaults.update(kwargs)
    return Context(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# GATE 1 — 6 tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_gate1_passe_email_normal():
    """Email normal → gate1 passe sans exception."""
    ctx = _ctx()
    await gate1_disqualify(ctx)  # ne doit pas lever


@pytest.mark.asyncio
async def test_gate1_bloque_re():
    """Sujet RE: → gate1 stoppe et routing = PROJECT_UPDATE."""
    ctx = _ctx(email_subject="RE: Demande de devis cartes de visite")
    with pytest.raises(StopPipeline, match="gate1\\[cas1\\]"):
        await gate1_disqualify(ctx)
    assert ctx.routing_category == "PROJECT_UPDATE"


@pytest.mark.asyncio
async def test_gate1_bloque_fw():
    """Sujet FW: → gate1 stoppe."""
    ctx = _ctx(email_subject="FW: Devis urgent")
    with pytest.raises(StopPipeline, match="gate1\\[cas1\\]"):
        await gate1_disqualify(ctx)


@pytest.mark.asyncio
async def test_gate1_bloque_remerciement_court():
    """Corps < 50 mots + signal ack → gate1 stoppe."""
    ctx = _ctx(
        email_subject="Re votre devis",
        email_body="Merci pour votre retour rapide.",
    )
    # On retire RE: du sujet pour forcer l'évaluation du cas 2
    ctx.email_subject = "Votre devis reçu"
    with pytest.raises(StopPipeline, match="gate1\\[cas2\\]"):
        await gate1_disqualify(ctx)


@pytest.mark.asyncio
async def test_gate1_bloque_hors_bureau():
    """Signal hors-bureau dans le corps → gate1 stoppe."""
    ctx = _ctx(
        email_subject="Devis cartes de visite",
        email_body=(
            "Absent du bureau jusqu'au 15 avril. "
            "Pour toute urgence contacter Paola."
        ),
    )
    with pytest.raises(StopPipeline, match="gate1\\[cas3\\]"):
        await gate1_disqualify(ctx)


@pytest.mark.asyncio
async def test_gate1_bloque_expediteur_interne():
    """Expéditeur InPressco → gate1 stoppe."""
    ctx = _ctx(email_sender_address="paola@in-pressco.com")
    with pytest.raises(StopPipeline, match="gate1\\[cas4\\]"):
        await gate1_disqualify(ctx)


@pytest.mark.asyncio
async def test_gate1_bloque_corps_vide():
    """Corps < 20 chars → gate1 stoppe."""
    ctx = _ctx(email_body="Bonjour.")
    with pytest.raises(StopPipeline, match="gate1\\[cas6\\]"):
        await gate1_disqualify(ctx)


# ══════════════════════════════════════════════════════════════════════════════
# GATE 3 — 3 tests (avec mocks Dolibarr)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_gate3_passe_client_connu_sans_doublon():
    """socid valide + pas de devis doublon → gate3 passe."""
    ctx = _ctx()
    with patch(
        "src.steps.flux_a.gate3_qualify_dolibarr.DolibarrClient"
    ) as mock_cls:
        mock_doli = AsyncMock()
        mock_doli.list_proposals_by_socid.return_value = []
        mock_cls.return_value = mock_doli
        await gate3_qualify_dolibarr(ctx)  # ne doit pas lever


@pytest.mark.asyncio
async def test_gate3_bloque_client_inconnu():
    """socid = SOCID_INCONNU → gate3 stoppe + event ⏸ créé."""
    from src import config
    ctx = _ctx(socid=config.DOLIBARR_SOCID_INCONNU)
    with patch(
        "src.steps.flux_a.gate3_qualify_dolibarr.DolibarrClient"
    ) as mock_cls:
        mock_doli = AsyncMock()
        mock_doli.create_agenda_event.return_value = {"id": 999}
        mock_cls.return_value = mock_doli
        with pytest.raises(StopPipeline, match="gate3\\[check1\\]"):
            await gate3_qualify_dolibarr(ctx)
        mock_doli.create_agenda_event.assert_called_once()


@pytest.mark.asyncio
async def test_gate3_bloque_doublon_devis():
    """Devis ouvert avec nom projet similaire → gate3 stoppe + routing PROJECT_UPDATE."""
    ctx = _ctx(nom_projet="Catalogue printemps")
    with patch(
        "src.steps.flux_a.gate3_qualify_dolibarr.DolibarrClient"
    ) as mock_cls:
        mock_doli = AsyncMock()
        mock_doli.list_proposals_by_socid.return_value = [
            {
                "ref": "PROV-2026-0030",
                "statut": "0",
                "array_options": {"options_fhp_project_name": "Catalogue printemps 2026"},
            }
        ]
        mock_cls.return_value = mock_doli
        with pytest.raises(StopPipeline, match="gate3\\[check2\\]"):
            await gate3_qualify_dolibarr(ctx)
    assert ctx.routing_category == "PROJECT_UPDATE"


@pytest.mark.asyncio
async def test_gate3_bloque_lignes_vides():
    """devis_lines vide → gate3 stoppe + event ⏸ créé."""
    ctx = _ctx(devis_lines=[])
    with patch(
        "src.steps.flux_a.gate3_qualify_dolibarr.DolibarrClient"
    ) as mock_cls:
        mock_doli = AsyncMock()
        mock_doli.list_proposals_by_socid.return_value = []
        mock_doli.create_agenda_event.return_value = {"id": 998}
        mock_cls.return_value = mock_doli
        with pytest.raises(StopPipeline, match="gate3\\[check3\\]"):
            await gate3_qualify_dolibarr(ctx)
        mock_doli.create_agenda_event.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# GATE 4 (intégrée dans s13) — 4 tests
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_gate4_bloque_hors_horaire():
    """Heure hors plage → s13 met en file d'attente sans envoyer."""
    ctx = _ctx()
    with patch(
        "src.steps.flux_a.s13_send_email_client._get_local_hour", return_value=2
    ):
        await s13_send_email_client(ctx)
    assert ctx.output_response.get("status") == "queued_until_8h"


@pytest.mark.asyncio
async def test_gate4_bloque_prix_zero():
    """total_ht = 0 avec lignes tarifaires → s13 bloque."""
    ctx = _ctx(devis_lines=[{"product_type": 0, "qty": 1000, "subprice": 0.0}])
    with patch("src.steps.flux_a.s13_send_email_client._get_local_hour", return_value=10):
        await s13_send_email_client(ctx)
    assert ctx.output_response.get("status") == "blocked_zero_price"


@pytest.mark.asyncio
async def test_gate4_bloque_nouveau_contact():
    """client_created=True → s13 crée event ⏸ et n'envoie pas."""
    ctx = _ctx(client_created=True)
    with patch("src.steps.flux_a.s13_send_email_client._get_local_hour", return_value=10):
        with patch(
            "src.steps.flux_a.s13_send_email_client.DolibarrClient"
        ) as mock_cls:
            mock_doli = AsyncMock()
            mock_doli.create_agenda_event.return_value = {"id": 997}
            mock_cls.return_value = mock_doli
            await s13_send_email_client(ctx)
    assert ctx.output_response.get("status") == "pending_go_new_contact"
    mock_doli.create_agenda_event.assert_called_once()


@pytest.mark.asyncio
async def test_gate4_bloque_sentiment_hostile():
    """Sentiment agressif → s13 crée event ⏸ et n'envoie pas."""
    ctx = _ctx(
        email_sentiment={"sentiment": "agressif", "urgence": "critique"},
        client_created=False,
    )
    with patch("src.steps.flux_a.s13_send_email_client._get_local_hour", return_value=10):
        with patch(
            "src.steps.flux_a.s13_send_email_client.DolibarrClient"
        ) as mock_cls:
            mock_doli = AsyncMock()
            mock_doli.create_agenda_event.return_value = {"id": 996}
            mock_cls.return_value = mock_doli
            await s13_send_email_client(ctx)
    assert ctx.output_response.get("status") == "pending_go_hostile_sentiment"
    mock_doli.create_agenda_event.assert_called_once()
