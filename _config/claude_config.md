# claude_config.md — Configuration Anthropic Claude (Layer 3)

## Modèles utilisés

| Modèle | ID | Usage |
|--------|----|-------|
| Claude Opus | `claude-opus-4-5` | Analyses complexes (extraction client, analyse besoin, email réponse) |
| Claude Haiku | `claude-haiku-4-5-20251001` | Routing et sentiment (rapide, économique) |
| Claude Sonnet | `claude-sonnet-4-6` | Moteur IA dashboard chat (streaming) |

- **Temperature** : `0` par défaut dans le pipeline (déterministe — critique pour l'extraction structurée)
- **Response format** : JSON enforced via system prompt ("Retourner UNIQUEMENT le JSON")

## Usages dans le pipeline

| Étape | Méthode | Modèle | Input | Output |
|-------|---------|--------|-------|--------|
| s02 — appel parallèle 1 | `extract_client_data()` | Opus | expéditeur + corps email nettoyé | JSON client (soc_nom, email, contact...) |
| s02 — appel parallèle 2 | `analyse_sentiment_email()` | Haiku | expéditeur + corps email | JSON sentiment (sentiment, urgence, profil, intention) |
| s02 — appel parallèle 3 | `classify_email_routing()` | Haiku | expéditeur + corps email | JSON routing (categorie, confidence, motif) |
| s06 — analyse besoin | `analyse_besoin_impression()` | Opus | corps email nettoyé | JSON composants d'impression |
| s12 — email réponse | `generate_email_reponse_client()` | Opus | context projet complet | HTML email CONFIG_CLIENT_v2026 |
| dashboard `/api/chat` | streaming | Sonnet | messages + snapshot Dolibarr | SSE stream texte |

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
| analyse_sentiment_email | ~200 | ~2000 | ~2200 |
| classify_email_routing | ~200 | ~2000 | ~2200 |
| analyse_besoin_impression | ~400 | ~2000 | ~2400 |
| generate_email_reponse_client | ~600 | ~1000 | ~1600 |

## Variable d'environnement
```
ANTHROPIC_API_KEY=sk-ant-...
```
Chargée dans `src/config.py` via `python-dotenv`.

## Note migration OpenAI → Claude

Migration complète au 28/03/2026.
`openai_client.py` conservé pour référence — ne plus l'importer dans le pipeline.
`OPENAI_API_KEY` supprimé de `config.py` et `.env.example`.
