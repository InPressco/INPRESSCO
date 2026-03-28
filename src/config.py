"""config.py — Constantes et variables d'environnement."""
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()
else:
    print(
        "[WARN] python-dotenv non installé. Assurez-vous que les variables d'environnement sont définies. "
        "pip install python-dotenv"
    )

# === Anthropic Claude ===
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]

# === Outlook (Microsoft Graph) ===
OUTLOOK_TENANT_ID: str = os.environ["OUTLOOK_TENANT_ID"]
OUTLOOK_CLIENT_ID: str = os.environ["OUTLOOK_CLIENT_ID"]
OUTLOOK_CLIENT_SECRET: str = os.environ["OUTLOOK_CLIENT_SECRET"]
OUTLOOK_USER_EMAIL: str = os.environ.get("OUTLOOK_USER_EMAIL", "")
OUTLOOK_GRAPH_BASE: str = (
    f"https://graph.microsoft.com/v1.0/users/{OUTLOOK_USER_EMAIL}"
    if OUTLOOK_USER_EMAIL
    else "https://graph.microsoft.com/v1.0/me"
)

# IDs dossiers Outlook — format REST Graph API v1.0 (découverts le 28/03/2026)
OUTLOOK_FOLDER_DEVIS: str = "inbox"           # Boîte de réception — well-known name Graph API
OUTLOOK_FOLDER_ETUDE: str = "AAHD9iRZAAA="   # >> ETUDE PROJET (sous FLUX InPressco)

# === Dolibarr ===
DOLIBARR_API_KEY: str = os.environ["DOLIBARR_API_KEY"]
DOLIBARR_BASE_URL: str = os.environ.get(
    "DOLIBARR_BASE_URL",
    "https://in-pressco.crm.freshprocess.eu/api/index.php"
)

# IDs métier Dolibarr
DOLIBARR_SOCID_INCONNU: int = 16
DOLIBARR_USER_OWNER_ID: int = 166
DOLIBARR_PRODUCT_IMPRESSION: str = "35700"
DOLIBARR_COND_REGLEMENT_BAT: int = 15
DOLIBARR_MODE_REGLEMENT_VIREMENT: int = 2
DOLIBARR_MODEL_PDF: str = "azur_fp"
DOLIBARR_SPECIAL_CODE_CONTEXTE: int = 104777
DOLIBARR_SPECIAL_CODE_DESCRIPTIF: int = 104778

# === Dashboard ===
DASHBOARD_URL: str = os.environ.get("DASHBOARD_URL", "http://localhost:8080")
INPRESSCO_INTERNAL_EMAIL: str = os.environ.get("INPRESSCO_INTERNAL_EMAIL", "contact@in-pressco.com")

# === Données InPressco à exclure ===
INPRESSCO_EXCLUDE_EMAILS: list[str] = ["@in-pressco.com"]
INPRESSCO_EXCLUDE_NAMES: list[str] = [
    "InPressco", "In'pressco", "Nicolas Bompois", "Alys"
]
INPRESSCO_EXCLUDE_ADDRESS: str = "670 Boulevard Lepic 73100 AIX-LES-BAINS"
