"""Utilitaires d'URL et d'enrichissement pour les objets Dolibarr."""
import logging

logger = logging.getLogger(__name__)

MODULE_PARAMS: dict[str, tuple[str, str]] = {
    "propal":              ("comm/propal/card.php",      "propal"),
    "commande":            ("commande/card.php",          "commande"),
    "facture":             ("compta/facture/card.php",    "facture"),
    "facture_fournisseur": ("fourn/facture/card.php",     "facture_fournisseur"),
    "expedition":          ("expedition/card.php",        "expedition"),
}


def build_links(obj: dict, module: str, web_url: str) -> dict:
    """Retourne {project_name, url, pdf_url} pour un objet Dolibarr."""
    params = MODULE_PARAMS.get(module)
    if params is None:
        logger.warning(f"build_links : module inconnu {module!r} — url et pdf_url seront vides")
        params = ("", "")
    card_path, modulepart = params
    ao = obj.get("array_options") or {}
    last_doc = obj.get("last_main_doc") or ""
    return {
        "project_name": ao.get("options_fhp_project_name") or "",
        "url":          f"{web_url}/{card_path}?id={obj.get('id', '')}" if card_path else "",
        "pdf_url":      f"{web_url}/document.php?modulepart={modulepart}&file={last_doc}" if last_doc else "",
    }


def enrich(obj: dict, module: str, web_url: str) -> dict:
    """Retourne une copie de obj enrichie avec project_name, url et pdf_url."""
    return {**obj, **build_links(obj, module, web_url)}
