"""connectors/openai_client.py — Client OpenAI pour extraction et analyse."""
import json
import logging
from openai import AsyncOpenAI
from src import config

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client asynchrone OpenAI (GPT-4.1-mini)."""

    def __init__(self):
        self._client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL

    async def extract_json(self, system_prompt: str, user_content: str) -> dict:
        """
        Appel IA avec instruction de retourner UNIQUEMENT du JSON.
        Parse et retourne le dict Python.
        """
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON invalide reçu de l'IA : {raw[:200]}")
            raise ValueError(f"Réponse IA non parseable : {e}") from e

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
        return await self.extract_json(system_prompt, user_content)

    async def analyse_sentiment_email(self, sender: str, email_body: str) -> dict:
        """
        Analyse le profil psycho-communicationnel de l'expéditeur.
        Retourne sentiment, urgence, profil, intention.
        Basé sur le skill analyse-sentiment-email.
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
        return await self.extract_json(system_prompt, user_content)

    async def classify_email_routing(self, sender: str, email_body: str) -> dict:
        """
        Classifie l'email dans une des 8 catégories de routing InPressco.
        Basé sur le skill mail-routing-inpressco.
        Retourne categorie, confidence, motif.
        """
        system_prompt = """
Tu es un agent de routing email pour une imprimerie (In'Pressco).
Analyse l'email et retourne UNIQUEMENT un JSON avec la catégorie de routing.

Catégories disponibles :
- NEW_PROJECT : demande de devis/nouveau projet client externe (aucune référence Dolibarr)
- VISUAL_CREATION : demande de création graphique (logo, maquette, visuel, design)
- SUPPLIER_INVOICE : facture reçue d'un fournisseur
- PROJECT_UPDATE : mise à jour d'un projet existant (référence DEV-XXXX, CMD-XXXX, FA-XXXX présente)
- SUPPLIER_QUOTE : offre de prix reçue d'un fournisseur/sous-traitant
- PRICE_REQUEST : demande de tarif envoyée à un fournisseur
- ACTION : email interne (@inpressco.fr) — action Dolibarr directe
- UNKNOWN : non classifiable

Règle prioritaire : si expéditeur @inpressco.fr → categorie = "ACTION" (sauf contenu contraire évident).
Règle PROJECT_UPDATE : présence d'un numéro DEV-XXXX, CMD-XXXX ou FA-XXXX = signal fort.

Retourner UNIQUEMENT ce JSON :
{
  "categorie": "NOM_CATEGORIE",
  "confidence": "high | medium | low",
  "motif": "explication courte en une phrase"
}
"""
        user_content = f"Expéditeur :\n{sender}\n\nEmail :\n{email_body}"
        return await self.extract_json(system_prompt, user_content)

    async def analyse_besoin_impression(self, email_body: str) -> dict:
        """
        Analyser la demande d'impression depuis le corps de l'email.
        Retourne composants_isoles, synthese_contexte, date_livraison_souhaitee.

        Note : l'imposition et le score sont calculés en Python après cet appel
        (src/utils/imposition.py) — plus fiable que de demander du calcul à l'IA.
        """
        system_prompt = """
Tu es un expert en impression et pré-presse.
Analyse la demande client et extrais les composants d'impression de façon structurée.

RÈGLES :
1. Identifier chaque composant distinct (couverture, intérieur, marque-page, encart...)
2. Regrouper les composants liés sous un même intitule_maitre (ex: "Brochure A5")
3. Déduire le format ouvert depuis le format fermé selon le type de reliure :
   - Agrafage / Dos carré collé : largeur_ouverte = largeur_fermée × 2
   - Spirale / Sans reliure : format ouvert = format fermé
   - Si pas de reliure et composant simple : format ouvert = format fermé
4. Lister les alertes production sémantiques (incohérences, données suspectes)
5. Proposer une synthèse courte (3-4 phrases max)
6. Extraire la date de livraison souhaitée si mentionnée (format YYYY-MM-DD)

RÉPONDRE UNIQUEMENT EN JSON valide, sans texte supplémentaire.

Schéma attendu :
{
  "synthese_contexte": "string",
  "date_livraison_souhaitee": "YYYY-MM-DD ou null",
  "composants_isoles": [
    {
      "intitule_maitre": "string",
      "produit": "string",
      "nombre_pages": int_ou_null,
      "format_ferme_mm": {"largeur": float_ou_null, "hauteur": float_ou_null},
      "format_ouvert_mm": {"largeur": float_ou_null, "hauteur": float_ou_null},
      "type_impression": "string_ou_null",
      "support_grammage": "string_ou_null",
      "type_finition": "string_ou_null",
      "type_reliure": "string_ou_null",
      "conditionnement": "string_ou_null",
      "franco_port": "string_ou_null",
      "quantite": int,
      "SCORE_DEVIS": {"alertes": ["string — alerte sémantique uniquement"]},
      "TRACE": "string_ou_null — citation exacte du mail ayant permis l'extraction"
    }
  ]
}
"""
        return await self.extract_json(system_prompt, email_body)
