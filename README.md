# InPressco MWP — Workflow d'automatisation des devis

## Prérequis
- Python 3.11+
- VS Code (recommandé)
- Compte Microsoft Azure (pour l'API Outlook)
- Accès à l'API Dolibarr InPressco
- Clé API OpenAI

## Installation

```bash
# 1. Cloner / dézipper le projet
cd inpressco-mwp

# 2. Créer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés
```

## Configuration

Éditer `.env` :
```
OPENAI_API_KEY=sk-...
OUTLOOK_TENANT_ID=...
OUTLOOK_CLIENT_ID=...
OUTLOOK_CLIENT_SECRET=...
OUTLOOK_REFRESH_TOKEN=...
DOLIBARR_API_KEY=...
```

Pour obtenir le `OUTLOOK_REFRESH_TOKEN`, voir la documentation MSAL :
https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow

## Lancement

```bash
# Exécution unique (les deux flux)
python main.py

# Planification toutes les minutes (cron Linux)
* * * * * cd /chemin/vers/inpressco-mwp && .venv/bin/python main.py >> cron.log 2>&1

# Planification Windows (Planificateur de tâches)
# Créer une tâche qui exécute : python main.py dans le dossier du projet
```

## Structure MWP

```
inpressco-mwp/
├── CLAUDE.md          ← Layer 0 : identité du workspace
├── CONTEXT.md         ← Layer 1 : routing des tâches
├── stages/            ← Layer 2 : contrats de chaque stage
│   ├── 01_extraction_email/CONTEXT.md
│   ├── 02_analyse_client/CONTEXT.md
│   ├── 03_analyse_besoin_impression/CONTEXT.md
│   ├── 04_construction_devis/CONTEXT.md
│   └── 05_archivage/CONTEXT.md
├── _config/           ← Layer 3 : configuration persistante
│   ├── dolibarr_config.md
│   └── outlook_config.md
├── shared/            ← Layer 3 : règles métier
│   ├── regles_extraction.md
│   ├── regles_impression.md
│   └── regles_devis.md
├── src/               ← Code Python
│   ├── config.py
│   ├── middleware/    pipeline.py + context.py
│   ├── connectors/    outlook.py + dolibarr.py + openai_client.py
│   ├── steps/         flux_a/ + flux_b/
│   └── utils/         devis_builder.py
├── main.py            ← Point d'entrée
├── requirements.txt
└── .env.example
```

## Développement VS Code

Extensions recommandées :
- Python (Microsoft)
- Pylance
- Python Debugger
- GitLens

Pour déboguer un flux spécifique, créer un fichier `debug_run.py` :
```python
import asyncio
from src.middleware.context import Context
from src.steps.flux_a.steps import s01_get_email, s02_extract_client_ai

async def debug():
    ctx = Context()
    await s01_get_email(ctx)
    print(ctx.email_subject)
    await s02_extract_client_ai(ctx)
    print(ctx.client_data)

asyncio.run(debug())
```

## Intervention humaine (points de contrôle MWP)

Les outputs de chaque stage sont dans `stages/XX_nom/output/result.json`.
Vous pouvez inspecter et modifier ces fichiers entre les stages.

Points critiques recommandés :
1. **Après Stage 1** : vérifier les données client extraites
2. **Après Stage 3** : vérifier les composants d'impression (⭐ le plus important)
3. **Après Stage 4** : vérifier le devis dans Dolibarr avant archivage

## Logs

Le fichier `pipeline.log` contient l'historique de toutes les exécutions.
