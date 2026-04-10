"""steps/flux_a/s08_create_devis.py — Création du devis dans Dolibarr (S13a)."""
import logging
from datetime import datetime, timezone

from src import config
from src.connectors.dolibarr import DolibarrClient
from src.connectors.outlook import OutlookClient
from src.middleware.context import Context
from src.utils.pipeline_helpers import write_stage_output

logger = logging.getLogger(__name__)

# ── Valeurs CIMA (array_options.options_cima) ─────────────────────────────────
# Format FreshProcess : "{id}, {LABEL}"
# IDs à vérifier via GET /extrafields/propal si les valeurs ne s'enregistrent pas.
_CIMA_RIEN = "8, RIEN"
_CIMA_MAP = [
    ("1, PROTOTYPAGE DEVELOPPEMENT", [
        "prototype", "maquette physique", "test produit", "développement", "r&d", "proto",
    ]),
    ("2, PRODUCTION SURMESURE RSE", [
        "rse", "recyclé", "eco-responsable", "éco-responsable", "pefc", "fsc", "sur mesure",
        "papier recyclé", "matière recyclée",
    ]),
    ("3, CIRCUIT COURT", [
        "circuit court", "producteur local", "km 0",
    ]),
    ("4, CONCEPTION NUMERIQUE", [
        "numérique", "digital", "impression numérique", "bat numérique",
        "jet d'encre", "laser", "toner",
    ]),
    ("5, MARKETING PERSO (non reproductible)", [
        "personnalisé", "variable", "numéros", "impression variable",
        "numérotation", "données variables",
    ]),
    ("6, MANUFACTURE TRADI", [
        "offset", "sérigraphie", "dorure", "gaufrage", "marquage à chaud",
        "typographie", "hot stamping", "vernis sélectif", "thermogravure",
        "relief", "pelliculage velours", "soft touch",
    ]),
]

# ── Valeurs STATUT CLIENT (array_options.options_statut) ─────────────────────
# IDs à vérifier via GET /extrafields/propal si les valeurs ne s'enregistrent pas.
_STATUT_A_DEFINIR = "1, A définir"
_STATUT_RIEN      = "2, RIEN"
_STATUT_RECCURENT = "3, RECCURENT"
_STATUT_PRIVILEGE = "4, PRIVILEGE"
_STATUT_TAPIS     = "5, TAPIS ROUGE"

# Maisons TOP (Chanel, Hermès, Dom Pérignon…) → TAPIS ROUGE dès 1 commande
_BRANDS_TAPIS = {
    "chanel", "hermès", "hermes", "dom pérignon", "dom perignon",
    "moët", "moet", "hennessy", "dior", "louis vuitton", "vuitton", "lvmh",
    "givenchy", "céline", "celine", "rolex", "cartier", "patek", "chopard",
}

# Maisons reconnues mais second tier → PRIVILEGE dès 1 commande
_BRANDS_PRIVILEGE = {
    "bulgari", "bvlgari", "prada", "gucci", "ysl", "yves saint laurent",
    "kering", "richemont", "omega", "longines", "swarovski",
    "saint-gobain", "michelin", "airbus", "savoie mont blanc",
}

# ── Valeurs CLASSIFICATION DU PROJET (VA) (array_options.options_classificationduprojetva)
# Format sans espace : "{id},{LABEL}" — tel que configuré dans Dolibarr
_CLASSIF_A_DEFINIR       = "1,A définir"
_CLASSIF_SANS_VA         = "2,SANS VA"
_CLASSIF_COMPLEXE_SANS   = "3,COMPLEXE SANS VA"
_CLASSIF_COMPLEXE_VA     = "4,COMPLEXE AVEC VA"
_CLASSIF_COMPLEXE_VA_PP  = "5,COMPLEXE++ AVEC VA ++"

# Finitions Valeur Ajoutée (VA) — dorure, gaufrage, sérigraphie, etc.
_FINITIONS_VA = [
    "dorure", "gaufrage", "sérigraphie", "marquage à chaud", "hot stamping",
    "vernis sélectif", "vernis uv", "soft touch", "thermogravure",
    "découpe spéciale", "pelliculage velours", "relief",
]


def _detect_cima(composants: list[dict], email_body: str) -> str:
    """
    Détecte la catégorie CIMA en analysant l'ensemble des données de fabrication.
    Priorité : champs composants (finition · support · impression · produit) → body email.
    """
    composant_texts = []
    for c in composants:
        composant_texts.extend([
            (c.get("type_finition")    or "").lower(),
            (c.get("support_grammage") or "").lower(),
            (c.get("type_impression")  or "").lower(),
            (c.get("produit")          or "").lower(),
            (c.get("conditionnement")  or "").lower(),
        ])
    full_text = " ".join(composant_texts) + " " + (email_body or "").lower()

    for cima_val, keywords in _CIMA_MAP:
        for kw in keywords:
            if kw in full_text:
                return cima_val

    return _CIMA_RIEN


def _detect_classif_projet(composants: list[dict]) -> str:
    """
    Classifie le projet selon la présence de finitions VA et la complexité technique.

    VA = Valeur Ajoutée : dorure, gaufrage, sérigraphie, soft touch, etc.

    - SANS VA          : projet standard, aucune finition VA
    - COMPLEXE SANS VA : multi-composants ou reliure, mais zéro VA
    - COMPLEXE AVEC VA : au moins 1 finition VA
    - COMPLEXE++ AVEC VA ++ : 2+ composants avec VA OU 2+ types de VA distincts
    """
    nb = len(composants)
    va_count   = 0   # nombre de composants portant au moins 1 finition VA
    va_types   = set()
    complexity = 0   # signal de complexité hors VA

    for c in composants:
        finition = (c.get("type_finition") or "").lower()
        types_va_present = [fa for fa in _FINITIONS_VA if fa in finition]
        if types_va_present:
            va_count += 1
            va_types.update(types_va_present)
        if c.get("type_reliure"):
            complexity += 1

    if nb >= 3:
        complexity += 1

    if va_count == 0:
        return _CLASSIF_COMPLEXE_SANS if complexity >= 1 else _CLASSIF_SANS_VA

    if va_count >= 2 or len(va_types) >= 2:
        return _CLASSIF_COMPLEXE_VA_PP

    return _CLASSIF_COMPLEXE_VA


async def _detect_statut_client(
    doli: DolibarrClient, socid: int, client_created: bool, soc_nom: str
) -> str:
    """
    Déduit le statut commercial du client.

    - TAPIS ROUGE : maison top luxe (Chanel, Hermès, Dom Pérignon…) + ≥ 1 commande
    - PRIVILEGE   : marque reconnue second tier + ≥ 1 commande
    - RECCURENT   : 3+ commandes, marque non prestige
    - RIEN        : client connu, faible activité
    - A DEFINIR   : nouveau client OU aucune commande + marque inconnue
    """
    if client_created:
        return _STATUT_A_DEFINIR

    low = (soc_nom or "").lower()
    is_tapis     = any(b in low for b in _BRANDS_TAPIS)
    is_privilege = any(b in low for b in _BRANDS_PRIVILEGE)

    try:
        count = await doli.count_orders_by_socid(socid)
        if is_tapis and count >= 1:
            return _STATUT_TAPIS
        if is_privilege and count >= 1:
            return _STATUT_PRIVILEGE
        if count >= 3:
            return _STATUT_RECCURENT
        if count == 0:
            return _STATUT_A_DEFINIR
        return _STATUT_RIEN
    except Exception as e:
        logger.warning(f"s08: count_orders_by_socid échoué → {e} — fallback A définir")
        return _STATUT_A_DEFINIR


async def s08_create_devis(ctx: Context) -> None:
    """Crée le devis dans Dolibarr, le valide pour générer la ref, puis remet en brouillon."""
    doli = DolibarrClient()

    # Conversion date email → epoch
    received_str = ctx.email_received_at or datetime.now(timezone.utc).isoformat()
    received_dt  = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
    date_epoch   = int(received_dt.timestamp())

    # Conversion date livraison souhaitée → epoch
    date_livraison = 0
    if ctx.date_livraison_souhaitee:
        try:
            date_livraison = int(
                datetime.fromisoformat(ctx.date_livraison_souhaitee).timestamp()
            )
        except ValueError:
            logger.warning(f"s08: date livraison invalide : {ctx.date_livraison_souhaitee!r}")

    # ── Détection CIMA, STATUT CLIENT et STATUT PROJET ───────────────────
    cima_val         = _detect_cima(ctx.composants_isoles, ctx.email_body)
    statut_val       = await _detect_statut_client(doli, ctx.socid, ctx.client_created, ctx.soc_nom)
    statut_projet    = _detect_classif_projet(ctx.composants_isoles)

    # ── note_private Bloc 1 — Tracabilité pipeline ────────────────────────
    note_private = (
        f"Devis créé automatiquement — "
        f"mail \"{ctx.email_subject}\" reçu le "
        f"{received_dt.strftime('%d/%m/%Y')} — "
        f"run {ctx.email_id or 'N/A'}\n"
        f"Gate 1 : OK · Gate 3 : OK · "
        f"CIMA : {cima_val} · Statut client : {statut_val} · Classification projet : {statut_projet}"
    )

    # ── note_public — Synthèse contexte (visible sur PDF client) ─────────
    note_public = ctx.synthese_contexte or ""

    # ── Payload devis ─────────────────────────────────────────────────────
    payload = {
        "socid":              ctx.socid,
        "date":               date_epoch,
        "model_pdf":          config.DOLIBARR_MODEL_PDF,
        "note_private":       note_private,
        "note_public":        note_public,
        "date_livraison":     date_livraison,
        "cond_reglement_id":  config.DOLIBARR_COND_REGLEMENT_BAT,
        "mode_reglement_id":  config.DOLIBARR_MODE_REGLEMENT_VIREMENT,
        "array_options": {
            "options_fhp_project_name":  ctx.nom_projet,
            "options_cima":              cima_val,
            "options_statut":            statut_val,
            "options_classificationduprojetva": statut_projet,
            "options_autonotes_private": ctx.autonotes_private or "",
            "options_version_actuelle":  "1",
        },
        "lines": ctx.devis_lines,
    }

    # 1. Créer le devis
    created  = await doli.create_proposal(payload)
    devis_id = int(created["id"])

    # Marker anti-doublon : écrire dès maintenant
    write_stage_output(4, {
        "email_id":  ctx.email_id,
        "devis_id":  devis_id,
        "devis_ref": "",
        "socid":     ctx.socid,
        "soc_nom":   ctx.soc_nom,
    })

    # 2. Valider → génère la référence PRO...
    validated    = await doli.validate_proposal(devis_id)
    ctx.devis_ref = validated.get("ref", "")
    ctx.devis_id  = devis_id

    write_stage_output(4, {
        "email_id":  ctx.email_id,
        "devis_id":  devis_id,
        "devis_ref": ctx.devis_ref,
        "socid":     ctx.socid,
        "soc_nom":   ctx.soc_nom,
    })

    # 3. Remettre en brouillon pour édition manuelle
    await doli.set_to_draft(devis_id)

    # 4. Créer le dossier Outlook dédié (séparateur tiret simple — fix bug em-dash)
    if config.OUTLOOK_FOLDER_DOSSIERS_DEVIS:
        try:
            outlook = OutlookClient()
            folder_display = f"{ctx.devis_ref} - {(ctx.soc_nom or '')[:100]}"
            folder_id = await outlook.get_or_create_folder(
                config.OUTLOOK_FOLDER_DOSSIERS_DEVIS,
                folder_display,
            )
            ctx.outlook_folder_id = folder_id
            logger.info(f"s08: dossier Outlook créé → {folder_display!r}")
        except Exception as e:
            logger.warning(f"s08: création dossier Outlook échouée → {e}")

    logger.info(
        f"s08: devis créé — id={ctx.devis_id}, ref={ctx.devis_ref!r}, "
        f"CIMA={cima_val!r}, STATUT={statut_val!r}, CLASSIF={statut_projet!r}"
    )
