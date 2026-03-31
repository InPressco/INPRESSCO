"""steps/flux_a/s04_find_or_create_client.py — Trouver ou créer le tiers Dolibarr."""
import logging

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.middleware.context import Context

logger = logging.getLogger(__name__)


async def s04_find_or_create_client(ctx: Context) -> None:
    """Recherche le tiers dans Dolibarr. Le crée si besoin. Fallback = socid 16."""
    doli = DolibarrClient()
    data = ctx.client_data
    soc_nom = data.get("soc_nom")
    email = data.get("email")

    found = await doli.find_thirdparty(email=email, name=soc_nom)

    if found:
        ctx.socid = int(found["id"])
        ctx.soc_nom = found.get("name", soc_nom or "")
        logger.info(f"Tiers trouvé : socid={ctx.socid}, nom={ctx.soc_nom!r}")

    elif soc_nom and email:
        payload = {
            "name": soc_nom,
            "client": 1,
            "email": email,
            "name_alias": f"{data.get('contact_prenom','')} {data.get('contact_nom','')}".strip(),
        }
        for field in ("zip", "town", "address", "phone"):
            if data.get(field):
                payload[field] = data[field]

        created = await doli.create_thirdparty(payload)
        ctx.socid = int(created["id"])
        ctx.soc_nom = soc_nom
        ctx.client_created = True
        logger.info(f"Tiers créé : socid={ctx.socid}, nom={ctx.soc_nom!r}")

    else:
        ctx.socid = config.DOLIBARR_SOCID_INCONNU
        ctx.soc_nom = "CLIENT A RENSEIGNER"
        logger.warning("Client non identifiable → socid=16 (CLIENT A RENSEIGNER)")
