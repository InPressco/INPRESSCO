"""connectors/claude_client.py — Client Anthropic Claude (remplace openai_client.py).

Même interface que OpenAIClient — drop-in replacement.
Modèles :
  - claude-opus-4-5          → analyses complexes (extraction client, besoin impression)
  - claude-haiku-4-5-20251001 → routing et sentiment (rapide, économique)
"""
import asyncio
import json
import logging
import re

import anthropic

from src import config

logger = logging.getLogger(__name__)

_MODEL_FULL = "claude-opus-4-6"
_MODEL_FAST = "claude-haiku-4-5-20251001"


def _extract_json_from_text(text: str) -> str:
    """Extrait le JSON d'une réponse Claude même si du texte l'entoure.

    Stratégies dans l'ordre :
      1. Bloc ```json ... ``` ou ``` ... ```
      2. Premier objet JSON { ... } détecté par accolades
      3. Texte brut strippé (fallback)
    """
    text = text.strip()
    # 1. Bloc markdown
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fence:
        return fence.group(1).strip()
    # 2. Chercher le premier { et l'accolade fermante correspondante
    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    # 3. Fallback brut
    return text


class ClaudeClient:
    """Client asynchrone Anthropic Claude."""

    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    async def extract_json(
        self,
        system_prompt: str,
        user_content: str,
        model: str = _MODEL_FULL,
        max_tokens: int = 2048,
        temperature: float = 0,
    ) -> dict:
        """
        Appel Claude avec instruction de retourner UNIQUEMENT du JSON.
        Parse et retourne le dict Python. Retry automatique si rate limit (429).
        """
        for attempt in range(3):
            try:
                response = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )
                break
            except anthropic.RateLimitError as e:
                wait = 60 if attempt == 0 else 120
                logger.warning(f"Rate limit Claude (tentative {attempt+1}/3) — attente {wait}s : {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(wait)
        raw = response.content[0].text if response.content else "{}"
        # Extraire le JSON même si Claude ajoute du texte autour
        raw = _extract_json_from_text(raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON invalide reçu de Claude : {raw[:200]}")
            raise ValueError(f"Réponse Claude non parseable : {e}") from e

    async def extract_client_data(self, sender: str, email_body: str) -> dict:
        """
        Extraire les données client depuis un email.
        Utilise le prompt de shared/regles_extraction.md.
        """
        system_prompt = """
Tu es un agent d'extraction de données.
Analyse le contenu d'un email et extrais les informations structurées.

RÈGLES STRICTES :
1. Extraire UNIQUEMENT les informations explicitement présentes
2. Déduire le nom société depuis le domaine email si custom (CamelCase, - et . → espaces)
3. Si corps du mail mentionne un client (ex: "pour X", "commande de X") → utiliser comme soc_nom
4. Ne JAMAIS inventer une donnée
5. Retourner UNIQUEMENT le JSON, sans texte supplémentaire

EXCLURE ABSOLUMENT :
- InPressco, In'pressco, Nicolas Bompois, Alys
- @in-pressco.com
- 670 Boulevard Lepic 73100 AIX-LES-BAINS

EXCEPTION : si expéditeur @in-pressco.com → chercher le nom client dans le CORPS → soc_nom, email=null

CHAMPS OBLIGATOIRES : soc_nom, type="client", contact_nom, contact_prenom, email, nom_projet
CHAMPS OPTIONNELS (si présents) : phone, zip, town, address, siren, siret
RÈGLES : données absentes obligatoires → null | nom_projet JAMAIS null ni vide
"""
        user_content = f"Expéditeur :\n{sender}\n\nEmail à analyser :\n{email_body}"
        return await self.extract_json(system_prompt, user_content, model=_MODEL_FULL)

    async def analyse_sentiment_email(self, sender: str, email_body: str) -> dict:
        """
        Analyse le profil psycho-communicationnel de l'expéditeur.
        Retourne sentiment, urgence, profil, intention.
        """
        system_prompt = """
Tu es un agent d'analyse psycho-communicationnelle.
Analyse l'email fourni et retourne UNIQUEMENT un JSON avec ces 4 champs.

Règles :
- sentiment : "positif" | "neutre" | "négatif" | "agressif"
  (remerciements/enthousiasme → positif ; ton neutre → neutre ; frustration/reproche → négatif ; majuscules/attaque → agressif)
- urgence : "faible" | "modérée" | "critique"
  (aucune date → faible ; délai mentionné → modérée ; "URGENT"/deadline immédiate → critique)
- profil : "formel" | "décontracté" | "anxieux" | "exigeant" | "bienveillant"
  (vocabulaire soutenu → formel ; tutoiement/abréviations → décontracté ; beaucoup de questions → anxieux ; ton directif → exigeant ; formules douces → bienveillant)
- intention : "demande_devis" | "demande_info" | "réclamation" | "relance" | "autre"

Retourner UNIQUEMENT le JSON, sans texte supplémentaire.
"""
        user_content = f"Expéditeur :\n{sender}\n\nEmail :\n{email_body}"
        return await self.extract_json(system_prompt, user_content, model=_MODEL_FAST)

    async def classify_email_routing(self, sender: str, email_body: str) -> dict:
        """
        Classifie l'email dans une des 8 catégories de routing InPressco.
        Retourne categorie, confidence, motif.
        """
        system_prompt = """
Tu es un agent de routing email pour une imprimerie (In'Pressco).
Analyse l'email et retourne UNIQUEMENT un JSON avec la catégorie de routing.

Catégories disponibles :
- NEW_PROJECT              : demande de devis/nouveau projet client externe (aucune référence Dolibarr)
- VISUAL_CREATION          : demande de création graphique (logo, maquette, visuel, design)
- SUPPLIER_INVOICE         : facture reçue d'un fournisseur
- PROJECT_UPDATE           : mise à jour d'un projet existant (référence DEV-XXXX, CMD-XXXX, FA-XXXX présente)
- SUPPLIER_QUOTE           : offre de prix reçue d'un fournisseur/sous-traitant
- PRICE_REQUEST            : demande de tarif envoyée à un fournisseur
- ACTION                   : email interne (@inpressco.fr) — action Dolibarr directe
- ADMINISTRATIF_GENERALE   : courrier administratif général (contrat, assurance, admin légale, relance paiement, banque, social, fiscal — hors facture fournisseur déjà classée SUPPLIER_INVOICE)
- UNKNOWN                  : non classifiable / commercial non-devis (newsletter, prospection, courtesy)

Règle prioritaire : si expéditeur @inpressco.fr → categorie = "ACTION" (sauf contenu contraire évident).
Règle PROJECT_UPDATE : présence d'un numéro DEV-XXXX, CMD-XXXX ou FA-XXXX = signal fort.
Règle ADMINISTRATIF_GENERALE : email sans enjeu commercial mais avec contenu administratif structuré.

Retourner UNIQUEMENT ce JSON :
{
  "categorie": "NOM_CATEGORIE",
  "confidence": "high | medium | low",
  "motif": "explication courte en une phrase"
}
"""
        user_content = f"Expéditeur :\n{sender}\n\nEmail :\n{email_body}"
        return await self.extract_json(system_prompt, user_content, model=_MODEL_FAST)

    async def generate_email_reponse_client(
        self,
        soc_nom: str,
        contact_prenom: str | None,
        nom_projet: str,
        devis_ref: str,
        devis_url: str,
        synthese_contexte: str,
        composants_isoles: list,
        email_sentiment: dict,
        total_ht: float = 0.0,
    ) -> str:
        """
        Génère le corps HTML de l'email de réponse CONFIG_CLIENT_v2026.

        Adapté au contexte post-création devis : le devis Dolibarr existe déjà,
        la référence et le lien sont fournis en contexte.

        Format obligatoire (8 blocs) :
        1. Accusé de réception
        2. Résumé synthétique du besoin
        3. Confirmation de faisabilité
        4. Annonce budget avec fourchette HT
        5. Phrase Paola (adaptée post-devis)
        6. Conversion délai en date réelle
        7. Demande des fichiers
        8. Conclusion bienveillante

        Retourne le corps HTML prêt à envoyer.
        """
        # Résumé des composants pour le prompt
        composants_txt = "\n".join(
            f"- {c.get('intitule_maitre', '?')} : {c.get('produit', '?')}"
            f" {c.get('quantite', '?')} ex"
            f" | {c.get('format_ferme_mm', {})} mm"
            f" | {c.get('type_impression', '?')}"
            f" | {c.get('type_finition', '?')}"
            for c in (composants_isoles or [])
        )

        urgence = email_sentiment.get("urgence", "faible")
        profil  = email_sentiment.get("profil", "formel")
        budget_mention = f"{total_ht:.0f} € HT (montant indicatif du devis)" if total_ht else "à préciser selon finitions"

        system_prompt = f"""
Tu es le moteur de rédaction commercial d'IN'PRESSCO, imprimeur-façonnier haut de gamme (Aix-les-Bains).

Génère l'email de réponse CONFIG_CLIENT_v2026 en HTML simple (pas de balises complexes).
Structure exacte — 8 blocs dans cet ordre, chaque bloc séparé par un <br><br> :

1. ACCUSÉ DE RÉCEPTION
   "Nous accusons réception de votre brief et vous remercions de votre confiance."

2. RÉSUMÉ SYNTHÉTIQUE DU BESOIN
   Reformuler le projet en 2-3 phrases. Utiliser les composants fournis.

3. CONFIRMATION DE FAISABILITÉ
   Confirmer que le projet est réalisable en atelier InPressco.
   Mentionner les points d'attention techniques si pertinents.

4. ANNONCE DU BUDGET
   Format : "Pour cette configuration, le budget se situe entre X € et Y € HT selon les finitions retenues."
   Base : {budget_mention}
   Toujours en HT. Fourchette basse = sobre, fourchette haute = premium InPressco.

5. PHRASE PAOLA — MOT POUR MOT OBLIGATOIRE
   "Nous vous adressons ci-joint votre devis {devis_ref}. Notre équipe reste disponible pour affiner ce projet avec vous."

6. DÉLAI EN DATE RÉELLE
   Mentionner un délai de production indicatif (3-12 jours selon complexité).
   Si l'urgence est "critique", mentionner la possibilité express.

7. DEMANDE DES FICHIERS
   "Pouvez-vous nous transmettre les fichiers HD ou une prémaquette afin de valider la faisabilité technique ?"

8. CONCLUSION BIENVEILLANTE
   "Nous restons à votre disposition pour tout complément d'information et vous accompagnons volontiers dans la définition de votre projet."

RÈGLES :
- Ton : professionnel B2B haut de gamme, chaleureux, sans familiarité
- Profil expéditeur détecté : {profil} — adapter le registre
- Urgence : {urgence} — adapter le bloc délai
- Mot interdit : "estimatif" → utiliser "budget indicatif"
- Pas de gras, pas d'icônes, pas de Markdown
- Commencer directement par "Madame, Monsieur," ou "Bonjour [Prénom],"
- Terminer par la signature In'Pressco standard :
  <br>Cordialement,<br>
  L'équipe commerciale In'Pressco<br>
  contact@in-pressco.com | www.in-pressco.com<br>
  670 Boulevard Lepic — 73100 Aix-les-Bains

RETOURNER UNIQUEMENT le corps HTML de l'email, sans JSON, sans texte introductif.
"""

        salut = f"Bonjour {contact_prenom}," if contact_prenom else "Madame, Monsieur,"
        user_content = f"""
Destinataire : {soc_nom}
Projet : {nom_projet}
Référence devis Dolibarr : {devis_ref}
Lien devis : {devis_url}

Composants identifiés :
{composants_txt if composants_txt else "(aucun composant extrait)"}

Synthèse du contexte :
{synthese_contexte}

Formule d'ouverture à utiliser : {salut}
"""
        response = await self._client.messages.create(
            model=_MODEL_FULL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text.strip() if response.content else ""

    async def analyse_besoin_impression(self, email_body: str) -> dict:
        """
        Analyser la demande d'impression depuis le corps de l'email.
        Retourne composants_isoles, synthese_contexte, date_livraison_souhaitee.

        Note : l'imposition et le score sont calculés en Python après cet appel
        (src/utils/imposition.py) — plus fiable que de demander du calcul à l'IA.
        """
        system_prompt = """Tu es expert impression/pré-presse. Extrais les composants d'impression en JSON valide UNIQUEMENT.

Règles : identifier chaque composant distinct, regrouper sous intitule_maitre, déduire format ouvert (agrafage/DCC : largeur×2 ; spirale/sans reliure : = fermé), lister alertes sémantiques, synthèse 3 phrases max, date livraison si mentionnée (YYYY-MM-DD).

JSON attendu :
{"synthese_contexte":"str","date_livraison_souhaitee":"YYYY-MM-DD|null","composants_isoles":[{"intitule_maitre":"str","produit":"str","nombre_pages":int|null,"format_ferme_mm":{"largeur":float|null,"hauteur":float|null},"format_ouvert_mm":{"largeur":float|null,"hauteur":float|null},"type_impression":"str|null","support_grammage":"str|null","type_finition":"str|null","type_reliure":"str|null","conditionnement":"str|null","franco_port":"str|null","quantite":int,"SCORE_DEVIS":{"alertes":["str"]},"TRACE":"str|null"}]}"""
        return await self.extract_json(system_prompt, email_body, model=_MODEL_FULL, max_tokens=16000)
