# openai_config.md — Configuration OpenAI (Layer 3)

## Modèle utilisé
- **Model ID** : `gpt-4.1-mini`
- **Temperature** : `0` (déterministe — critique pour l'extraction structurée)
- **Response format** : `{"type": "json_object"}` (enforced)

## Usages dans le pipeline

| Étape | Méthode | Input | Output |
|-------|---------|-------|--------|
| s02_extract_client_ai | `extract_client_data()` | expéditeur + corps email nettoyé | JSON client (soc_nom, email, contact...) |
| s06_analyse_besoin | `analyse_besoin_impression()` | corps email nettoyé | JSON composants d'impression |

## Pré-traitement obligatoire avant envoi à l'IA

Le corps des emails est nettoyé par `src/utils/html_cleaner.py` **avant** tout appel IA :
- Strip des balises HTML (styles, scripts, boilerplate Outlook)
- Décodage des entités HTML
- Troncature à 8000 caractères max

## Post-traitement après l'analyse besoin

Le calcul d'imposition et le score de complétude sont calculés **en Python** par `src/utils/imposition.py`,
**après** l'appel IA (pas dans le prompt) :
- `IMPOSITION_BRUTE_700x1000` et `IMPOSITION_BRUTE_330x480` → `calculer_imposition()`
- `SCORE_DEVIS.score_sur_10` → `calculer_score()` (les alertes sémantiques viennent de l'IA)

## Limites et tokens estimés

| Appel | Tokens système | Tokens user (max) | Total estimé |
|-------|---------------|-------------------|--------------|
| extract_client_data | ~300 | ~2000 | ~2300 |
| analyse_besoin_impression | ~400 | ~2000 | ~2400 |

## Variable d'environnement
```
OPENAI_API_KEY=sk-...
```
Chargée dans `src/config.py` via `python-dotenv`.
