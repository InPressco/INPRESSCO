"""utils/imposition.py — Calcul d'imposition en Python (déplacé hors du prompt IA).

Pourquoi ici et pas dans le prompt IA ?
Les LLMs font des erreurs sur les ceil() et divisions entières.
Ce calcul est déterministe → Python est plus fiable et traçable.
"""
import math


# Formats de presse de référence (avec marges de sécurité 5mm par côté)
FORMATS_PRESSE = {
    "700x1000": (690, 990),
    "330x480": (320, 470),
}


def _poses_sur_format(format_ouvert_mm: dict, presse_w: int, presse_h: int) -> int | None:
    """Calcule le nombre de poses par feuille pour un format ouvert donné.

    Essaie les deux orientations (normale + rotation 90°) et retourne le max.
    Retourne None si le format ouvert est incomplet.
    """
    w = format_ouvert_mm.get("largeur")
    h = format_ouvert_mm.get("hauteur")
    if not w or not h or w <= 0 or h <= 0:
        return None

    # Orientation normale
    poses_normal = (presse_w // w) * (presse_h // h)
    # Rotation 90°
    poses_rotated = (presse_w // h) * (presse_h // w)

    poses = max(poses_normal, poses_rotated)
    return int(poses) if poses > 0 else None


def calculer_imposition(composant: dict) -> dict:
    """Calcule et injecte les blocs IMPOSITION_BRUTE_* dans un composant.

    Modifie le composant en place ET retourne le composant.
    Appelé en post-processing après l'appel IA, avant build_lines().
    """
    format_ouvert = composant.get("format_ouvert_mm") or {}
    quantite = composant.get("quantite") or 1

    for cle, (pw, ph) in FORMATS_PRESSE.items():
        bloc_key = f"IMPOSITION_BRUTE_{cle.replace('x', 'x')}"
        poses = _poses_sur_format(format_ouvert, pw, ph)

        if poses and poses > 0:
            feuilles = math.ceil(quantite / poses)
            composant[bloc_key] = {
                "poses_total": poses,
                "calcul_feuilles": {"feuilles": feuilles},
            }
        else:
            composant[bloc_key] = {
                "poses_total": None,
                "calcul_feuilles": {"feuilles": None},
            }

    return composant


def calculer_score(composant: dict) -> dict:
    """Calcule le score de complétude (0-10) et les alertes production.

    Remplace le SCORE_DEVIS retourné par l'IA (trop aléatoire).
    Le score IA reste utile pour les alertes sémantiques (ex: reliure incohérente).
    Ici on recalcule le score numérique en comptant les champs renseignés.
    """
    champs_obligatoires = [
        "support_grammage",
        "type_impression",
        "format_ferme_mm",
        "quantite",
    ]
    champs_bonus = [
        "type_finition",
        "type_reliure",
        "conditionnement",
        "franco_port",
        "nombre_pages",
    ]

    alertes = list((composant.get("SCORE_DEVIS") or {}).get("alertes", []))

    # Score de base sur les champs obligatoires (6 pts)
    score = 0.0
    for champ in champs_obligatoires:
        val = composant.get(champ)
        if val and val not in ("-", "null", ""):
            score += 1.5
        else:
            alertes.append(f"Champ manquant : {champ}")

    # Score bonus sur les champs optionnels (4 pts)
    for champ in champs_bonus:
        val = composant.get(champ)
        if val and val not in ("-", "null", ""):
            score += 0.8

    score_final = round(min(score, 10.0), 1)

    # Alertes spécifiques métier
    nombre_pages = composant.get("nombre_pages")
    if isinstance(nombre_pages, int) and nombre_pages % 2 != 0:
        alertes.append("Nombre de pages impair — vérifier la cohérence de mise en page")

    fo = composant.get("format_ouvert_mm") or {}
    imp = composant.get("IMPOSITION_BRUTE_700x1000") or {}
    if fo.get("largeur") and (imp.get("poses_total") or 0) == 0:
        alertes.append("Format non standard — imposition impossible sur 700×1000 et 330×480")

    composant["SCORE_DEVIS"] = {
        "score_sur_10": score_final,
        "alertes": list(dict.fromkeys(alertes)),  # dédupliqué, ordre préservé
    }
    return composant


def post_process_composants(composants: list[dict]) -> list[dict]:
    """Applique calcul d'imposition + score sur tous les composants.

    À appeler juste après ai.analyse_besoin_impression().
    """
    for comp in composants:
        calculer_imposition(comp)
        calculer_score(comp)
    return composants
