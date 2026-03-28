"""utils/html_cleaner.py — Nettoyage des corps d'emails HTML avant envoi à l'IA.

Pourquoi ?
Les emails Outlook arrivent souvent en HTML avec des styles, balises, boilerplate
qui polluent le prompt et augmentent les tokens inutilement.
Ce module extrait le texte brut lisible.
"""
import re


def strip_html(html: str) -> str:
    """Convertit un corps d'email HTML en texte brut lisible.

    Sans dépendance externe (pas de BeautifulSoup requis).
    Suffisant pour les emails transactionnels courants.
    """
    if not html:
        return ""

    # Supprimer les blocs style et script entiers
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)

    # Remplacer les balises de saut de ligne/paragraphe par des newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|tr|li|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)

    # Supprimer toutes les autres balises HTML
    text = re.sub(r"<[^>]+>", " ", text)

    # Décoder les entités HTML courantes
    replacements = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
        "&eacute;": "é", "&egrave;": "è", "&ecirc;": "ê",
        "&agrave;": "à", "&acirc;": "â", "&ugrave;": "ù",
        "&ocirc;": "ô", "&ccedil;": "ç",
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)

    # Supprimer les entités numériques résiduelles
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"&\w+;", " ", text)

    # Nettoyer les espaces multiples et lignes vides consécutives
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())

    return text.strip()


def prepare_email_for_ai(body: str) -> str:
    """Prépare le corps d'email pour envoi à l'IA.

    Si le contenu ressemble à du HTML, le nettoie.
    Sinon le retourne tel quel (emails plain-text).
    Tronque à 8000 caractères pour éviter les dépassements de contexte.
    """
    if body and ("<html" in body.lower() or "<div" in body.lower() or "<p " in body.lower()):
        cleaned = strip_html(body)
    else:
        cleaned = body or ""

    # Tronquer si nécessaire (gpt-4.1-mini : 128k tokens, mais un email > 8k chars est suspect)
    if len(cleaned) > 8000:
        cleaned = cleaned[:8000] + "\n[... email tronqué à 8000 caractères]"

    return cleaned
