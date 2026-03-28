"""debug_flux_a.py — Test rapide du Flux A step par step."""
import asyncio
import logging
logging.basicConfig(level=logging.DEBUG)

from src.middleware.context import Context
from src.steps.flux_a.steps import (
    s01_get_email,
    s02_extract_client_ai,
    s03_clean_data,
)

async def debug():
    ctx = Context()

    print("\n=== Step 1 : Récupération email ===")
    await s01_get_email(ctx)
    print(f"Sujet    : {ctx.email_subject}")
    print(f"Expéd.   : {ctx.email_sender_address}")

    print("\n=== Step 2 : Extraction client AI ===")
    await s02_extract_client_ai(ctx)
    print(f"soc_nom  : {ctx.client_data.get('soc_nom')}")
    print(f"email    : {ctx.client_data.get('email')}")
    print(f"projet   : {ctx.client_data.get('nom_projet')}")

    print("\n=== Step 3 : Nettoyage ===")
    await s03_clean_data(ctx)
    print(f"Données nettoyées : {ctx.client_data}")

    print("\nContexte final :", ctx.to_summary())

asyncio.run(debug())
