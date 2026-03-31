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

# IDs dossiers Outlook — FLUX InPressco + sous-dossiers (vérifiés le 30/03/2026 via Graph API)
OUTLOOK_FOLDER_INBOX:              str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAAAAAEMAAA="
OUTLOOK_FOLDER_FLUX_INPRESSCO:     str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAGUrtifAAA="
# Sous-dossiers de FLUX InPressco — destinations finales après classification
OUTLOOK_FOLDER_COMMERCE:          str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRaAAA="   # >> COMMERCE
OUTLOOK_FOLDER_ETUDE:             str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRZAAA="   # >> ETUDE PROJET
OUTLOOK_FOLDER_GENERAL:           str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRYAAA="   # >> GENERAL
OUTLOOK_FOLDER_MARKETING_RS:      str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHwfJB0AAA="   # >> MARKETING / RS
OUTLOOK_FOLDER_ADMIN:             str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRXAAA="   # ADMIN
OUTLOOK_FOLDER_TARIF_FOURNISSEURS:str = "AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTExZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAGUrtiiAAA="   # TARIF FOURNISSEURS
OUTLOOK_FOLDER_DEVIS:             str = OUTLOOK_FOLDER_COMMERCE  # alias pipeline
# Routing fournisseurs : SUPPLIER_QUOTE → TARIF_FOURNISSEURS, SUPPLIER_INVOICE → ADMIN
OUTLOOK_FOLDER_DEVIS_FOURNISSEUR:  str = OUTLOOK_FOLDER_TARIF_FOURNISSEURS
OUTLOOK_FOLDER_FACTURE_FOURNISSEUR:str = OUTLOOK_FOLDER_ADMIN

# ─── Drop zone universelle ────────────────────────────────────────────────────
# Dossier Outlook "FLUX INPRESSCO" : point d'entrée unique du pipeline.
# Tous les emails à traiter doivent atterrir ici :
#   - Via règle Outlook (auto-route de la boîte principale)
#   - Via glisser-déposer manuel depuis n'importe où dans Outlook
#   - Via API Graph (move_message depuis la boîte de réception)
# Après traitement, chaque email est déplacé vers sa destination finale :
#   NEW_PROJECT           → sous-dossier ETUDE PROJET (par s11) → Flux A
#   SUPPLIER_QUOTE        → DEVIS_FOURNISSEUR (par sc07)         → Flux C
#   SUPPLIER_INVOICE      → FACTURE_FOURNISSEUR (par sc07)       → Flux C
#   PROJECT_UPDATE        → géré par Flux B dans ETUDE (juste marqué [Routé-])
#   ADMINISTRATIF_GENERALE→ dossier ADMIN (marqué + déplacé)
#   Autres (commerce)     → dossier COMMERCE (marqué + déplacé)
OUTLOOK_FOLDER_PENDING: str = OUTLOOK_FOLDER_FLUX_INPRESSCO

# Arborescence devis : créée automatiquement à la première utilisation
# OUTLOOK_FOLDER_DOSSIERS_DEVIS : parent des sous-dossiers par devis (un dossier = un DEV-XXXX)
# OUTLOOK_FOLDER_ARCHIVES       : dossiers déplacés ici quand le devis est facturé
OUTLOOK_FOLDER_DOSSIERS_DEVIS: str = os.environ.get("OUTLOOK_FOLDER_DOSSIERS_DEVIS", "")
OUTLOOK_FOLDER_ARCHIVES: str       = os.environ.get("OUTLOOK_FOLDER_ARCHIVES", "")

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
