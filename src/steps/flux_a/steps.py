"""steps/flux_a/steps.py — Manifest : re-exporte tous les steps Flux A.

Chaque step vit dans son propre fichier (s01_*.py … s13_*.py + routing.py).
Ce fichier existe uniquement pour la compatibilité des imports existants
(dispatcher.py, engine/main.py, dashboard/app.py).
"""
from src.steps.flux_a.s01_get_email import s01_get_email
from src.steps.flux_a.s02_extract_client_ai import s02_extract_client_ai
from src.steps.flux_a.s03_clean_data import s03_clean_data
from src.steps.flux_a.s04_find_or_create_client import s04_find_or_create_client
from src.steps.flux_a.s05_get_attachments import s05_get_attachments
from src.steps.flux_a.s06_analyse_besoin import s06_analyse_besoin
from src.steps.flux_a.s07_build_devis_lines import s07_build_devis_lines
from src.steps.flux_a.s08_create_devis import s08_create_devis
from src.steps.flux_a.s09_upload_attachments import s09_upload_attachments
from src.steps.flux_a.s10_log_email import s10_log_email
from src.steps.flux_a.s11_archive_outlook import s11_archive_outlook
from src.steps.flux_a.s12_notify_team import s12_notify_team
from src.steps.flux_a.s13_send_email_client import s13_send_email_client
from src.steps.flux_a.routing import (
    s_mark_non_devis,
    s_route_to_admin,
    s_route_to_commerce,
)

__all__ = [
    "s01_get_email",
    "s02_extract_client_ai",
    "s03_clean_data",
    "s04_find_or_create_client",
    "s05_get_attachments",
    "s06_analyse_besoin",
    "s07_build_devis_lines",
    "s08_create_devis",
    "s09_upload_attachments",
    "s10_log_email",
    "s11_archive_outlook",
    "s12_notify_team",
    "s13_send_email_client",
    "s_mark_non_devis",
    "s_route_to_admin",
    "s_route_to_commerce",
]
