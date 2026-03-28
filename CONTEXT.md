# CONTEXT.md — Layer 1 : Routing des tâches + État du projet

## État du projet — 28/03/2026 (mis à jour)

| Composant | Statut | Détail |
|-----------|--------|--------|
| `src/connectors/claude_client.py` | ✅ Produit | 5 méthodes : extract_client_data, analyse_sentiment, classify_routing, analyse_besoin, **generate_email_reponse_client** |
| `src/connectors/outlook.py` | ✅ Produit | Lecture + archivage + **send_email()** (sendMail + createReply) |
| `src/connectors/dolibarr.py` | ✅ Produit | Injection SQL corrigée — sanitisation stricte (quotes, `;`, backticks, keywords SQL) |
| `src/middleware/context.py` | ✅ Produit | Enrichi avec **output_response, output_actions, output_silent** |
| `src/utils/imposition.py` | ✅ Testé | 3/3 datasets OK |
| `src/utils/html_cleaner.py` | ✅ Testé | 44-67% compression HTML |
| `src/utils/devis_builder.py` | ✅ Testé | 3/3 datasets OK |
| `src/engine/main.py` | ✅ Produit | Boucle polling Flux A + B en parallèle |
| `src/engine/dispatcher.py` | ✅ Produit | Routing + **s12_send_email_client ajouté** à Flux A |
| `src/steps/flux_a/steps.py` | ✅ Produit | **12 steps** s01→s12 (email réponse CONFIG_CLIENT_v2026) |
| `src/steps/flux_b/steps.py` | ✅ Produit | 3 steps s01→s03 |
| `dashboard/app.py` | ✅ Produit | 14 endpoints : KPIs, stats, DAF, CA chart, clients, chat Claude, upload assets |
| `.env.example` | ✅ Créé | Anthropic + Azure AD + Dolibarr + dashboard |
| `_config/claude_config.md` | ✅ Créé | Remplace openai_config.md — documente les 5 méthodes Claude |
| Dolibarr API (GET) | ✅ Testé | /status, /thirdparties OK — sortfield=rowid KO → supprimé |
| Dolibarr API (écriture) | ❌ Non testé | create_proposal, upload_document, agenda — à valider en staging |
| Outlook / Microsoft Graph | ❌ Bloqué | Credentials Azure AD manquants — BLOQUEUR TOTAL pour s01 et s12 |
| Freshprocess API | ❌ Non testé | 3 clés présentes, auth non découverte |
| Skills installés | ✅ 24 actifs | dont agent-acheteur-inpressco + planche-archi-inpressco (28/03/2026) |

---

## Architecture cible (ROADMAP 2026-03-28)

```
contact@in-pressco.com
        │
        ▼
┌─────────────────────────────────────────────────┐
│  COUCHE 0 — Réception                           │
│  Microsoft Graph API  ·  html_cleaner           │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  COUCHE 1 — Gate (toujours en premier)          │
│  droits-profils  ·  mail-routing  ·  sentiment  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  COUCHE 2 — Cerveau                             │
│  orchestrateur  ·  mémoire-client               │
└──┬──────────┬──────────┬──────────┬─────────────┘
   │          │          │          │
 Prix     Cmd/Devis  Commerce    Admin/Général
   │          │          │          │
┌──▼──────────▼──────────▼──────────▼─────────────┐
│  COUCHE 3 — Skills métier (24 skills)            │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  COUCHE 4 — Sorties                             │
│  reponse-client  ·  validation-qc               │
│  archiveur  ·  agenda                           │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  COUCHE 5 — Silencieux                          │
│  notification  ·  gestion-erreurs               │
│  stage-output  ·  claude-client                 │
└────────────────────┬────────────────────────────┘
                     │
              Dolibarr / Freshprocess
```

---

## Architecture des couches (fichiers)

```
Layer 0  CLAUDE.md              → Identité, règles absolues
Layer 1  CONTEXT.md             → Routing, état projet (ce fichier)
Layer 2  stages/XX/CONTEXT.md  → Contrat input/output de chaque stage
Layer 3  _config/*.md           → Configuration persistante (IDs, endpoints)
         shared/*.md            → Règles métier et prompts IA
Layer 4  stages/XX/output/      → Artifacts de travail (result.json par stage)
```

---

## Flux disponibles

### Flux A — Nouveau devis entrant
**Déclencheur** : email non traité dans le dossier Outlook `DEVIS`
**Séquence** :
1. `s01` — Récupère le dernier email non traité (`[Traité]` filtre)
2. `s02` — Extrait les données client via `claude_client.py` + `html_cleaner` (3 appels parallèles)
3. `s03` — Valide routing (seule catégorie `NEW_PROJECT` poursuit) + nettoyage exclusions InPressco
4. `s04` — Trouve ou crée le tiers dans Dolibarr (fallback socid=16)
5. `s05` — Récupère les pièces jointes non-inline
6. `s06` — Analyse besoin impression via Claude + `post_process_composants()` Python
7. `s07` — Construit les lignes Dolibarr via `devis_builder.build_lines()`
8. `s08` — Crée le devis → valide (génère ref PRO...) → remet en brouillon → write marker anti-doublon
9. `s09` — Upload les PJ dans le dossier Dolibarr du devis
10. `s10` — Log email dans agenda Dolibarr lié au devis
11. `s11` — Crée dossier Outlook, renomme mail `[Traité]`, déplace → efface marker
12. `s12` — Génère email réponse CONFIG_CLIENT_v2026 via Claude + envoi Outlook sendMail + log agenda Dolibarr

### Flux B — Suivi de devis existants
**Déclencheur** : email non traité dans un sous-dossier `ETUDE PROJET` d'Outlook
**Séquence** :
1. `s01` — Récupère les sous-dossiers d'ETUDE PROJET
2. `s02` — Récupère les emails non traités de chaque sous-dossier
3. `s03` — Pour chaque email : identifie le devis, upload PJ, log agenda, marque `[Traité]`

### Moteur engine/ (✅ implémenté)
Le moteur `src/engine/` orchestre les flux ci-dessus avec une boucle centrale :
```
graph_client.list_unread_emails("DEVIS")
→ make_run_id() + check_no_duplicate()
→ html_cleaner.clean()
→ claude_client.run_s02() → routing + sentiment + extraction
→ dispatcher.route() → sélection chaîne (chain_A / chain_B / chain_admin / chain_fallback)
→ chaîne.execute()
→ output_builder.build() → {response, actions, silent}
→ [validation humaine si nécessaire]
→ stage_output.write() + graph_client.mark_read()
```

**Routing map dispatcher.py** :
```python
ROUTING_MAP = {
    "NEW_PROJECT":      "chain_A",
    "PROJECT_UPDATE":   "chain_B",
    "PRICE_REQUEST":    "chain_A",
    "SUPPLIER_INVOICE": "chain_admin",
    "SUPPLIER_QUOTE":   "chain_admin",
    "ACTION":           "chain_silent",
    "UNKNOWN":          "chain_fallback",
}
```

**Structure de sortie output_builder.py** :
```python
{
  "response":  {"to", "subject", "body", "status": "pending|sent|cancelled"},
  "actions":   [{"type", "label", "payload", "status": "pending|confirmed|cancelled", "comment"}],
  "silent":    [{"type", "label", "status": "done"}]
}
```

---

## Migration OpenAI → Claude (état)

| Ancien | Nouveau | Statut |
|--------|---------|--------|
| `openai_client.py::extract_client_data()` | `claude_client.py::extract_client_data()` | ✅ |
| `openai_client.py::classify_email_routing()` | `claude_client.py::classify_email_routing()` | ✅ |
| `openai_client.py::analyse_sentiment_email()` | `claude_client.py::analyse_sentiment_email()` | ✅ |
| `openai_client.py::analyse_besoin_impression()` | `claude_client.py::analyse_besoin_impression()` | ✅ |
| `model="gpt-4.1-mini"` | `model="claude-opus-4-5"` (complexe) | ✅ |
| — | `model="claude-haiku-4-5-20251001"` (routing/QC) | ✅ |
| Logique métier en dur dans le code | Skills `.md` injectés en system prompt | ✅ |
| `OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | ❌ à faire |
| `_config/openai_config.md` | `_config/claude_config.md` | ❌ à faire |

---

## Skills Claude — Intégration dans le pipeline

| Skill | Rôle dans le pipeline | Fichiers de référence |
|-------|----------------------|----------------------|
| `droits-profils-inpressco` | **Toujours en premier** — identifier le profil avant toute action sensible | — |
| `mail-routing-inpressco` | Routing email → 8 catégories. **s02** : appel parallèle → `ctx.routing_category`. **s03** : filtre `NEW_PROJECT` | — |
| `analyse-sentiment-email` | Profil expéditeur. **s02** : appel parallèle → `ctx.email_sentiment` | — |
| `inpressco-commerce` | Expert imprimeur. **s06** : enrichir analyse besoin. **s12** : email CONFIG_CLIENT_v2026 + fourchette HT | `references/finitions.md`, `references/matieres.md` |
| `dolibarr-query-inpressco` | CRUD Dolibarr. **s04** : find/create tiers. **s08** : create/validate/draft devis | — |
| `reponse-client-inpressco` | **s12** : rédaction + envoi email réponse client | — |
| `generation-pdf-inpressco` | **s12** : PDF devis (API Dolibarr azur_fp ou reportlab fallback) | — |
| `archiveur-inpressco` | **s09** : upload PJ email → dossier devis Dolibarr | — |
| `agenda-inpressco` | **s10** : log email dans agenda Dolibarr | — |
| `validation-qc-inpressco` | Gate avant envoi client (s12) et avant archivage (s11) | — |
| `projets-artefacts-inpressco` | Proposer sauvegarde après s06, s08, s12 | — |
| `gestion-erreurs-inpressco` | Filet de sécurité — appelé automatiquement en cas d'erreur API | — |

### Flux A enrichi avec les skills

```
s01  Récupération email Outlook
     → vérification marker anti-doublon (stage_output)
s02  3 appels Claude parallèles (claude_client.py) :
     ① extract_client_data    → ctx.client_data      [logique : extraction inline]
     ② analyse_sentiment      → ctx.email_sentiment  [skill : analyse-sentiment-email]
     ③ classify_routing       → ctx.routing_category [skill : mail-routing-inpressco]
s03  Validation routing : filtre _CATEGORIES_DEVIS = {"NEW_PROJECT"}
     → toute autre catégorie : StopPipeline(motif)
     → nettoyage données client + exclusions InPressco
s04  Tiers Dolibarr [skill : dolibarr-query-inpressco]
s05  Pièces jointes
s06  Analyse impression ← inpressco-commerce (matières + finitions)
     + post_process_composants() Python (imposition, score)
s07  Construction lignes
s08  Création devis Dolibarr [skill : dolibarr-query-inpressco]
     → stage_output.write() marker anti-doublon
s09  Upload PJ [skill : archiveur-inpressco]
s10  Log agenda Dolibarr [skill : agenda-inpressco]
s11  ← validation-qc-inpressco (avant archivage)
     Archivage Outlook → effacement marker
s12  ← generate_email_reponse_client() Claude Opus (8 blocs CONFIG_CLIENT_v2026)
     ← send_email() Outlook Graph API (sendMail + createReply pour conserver le thread)
     ← create_agenda_event() Dolibarr (log note interne sur le devis)
     → ctx.output_response, ctx.output_silent
     ⚠️ Fonctionnel côté code — bloqué en prod par credentials Azure AD (s01+s12)

cross projets-artefacts-inpressco → proposer sauvegarde après s06, s08, s12
```

### Context (ctx) — champs implémentés

```python
# src/middleware/context.py
ctx.email_sentiment = {
    "sentiment": "positif|neutre|négatif|agressif",
    "urgence": "faible|modérée|critique",
    "profil": "formel|décontracté|anxieux|exigeant|bienveillant",
    "intention": "demande_devis|demande_info|réclamation|relance|autre"
}
ctx.routing_category = "NEW_PROJECT|VISUAL_CREATION|PROJECT_UPDATE|..."
ctx.email_reponse_client = "..."  # généré par s12

# À ajouter pour output_builder.py :
ctx.output_response   = {}  # réponse email proposée
ctx.output_actions    = []  # actions Dolibarr à valider
ctx.output_silent     = []  # traitements automatiques
```

---

## Ressources partagées (Layer 3)

- `_config/dolibarr_config.md` — Endpoints, IDs fixes, constantes Dolibarr
- `_config/outlook_config.md` — IDs dossiers Outlook, filtres OData
- `_config/claude_config.md` — Modèles Claude, paramètres, note sur post-processing *(renommer depuis openai_config.md)*
- `shared/regles_extraction.md` — Prompt + schéma extraction données client
- `shared/regles_impression.md` — Prompt + schéma analyse besoin impression
- `shared/regles_devis.md` — Algorithme construction lignes (Python pseudocode)

---

## Failles à corriger (par priorité)

### 🔴 P0 — Sécurité prod immédiate

**Injection dans sqlfilters Dolibarr** ✅ CORRIGÉ
- `_sanitize_sqlfilter_value()` renforcé : supprime quotes, `;`, backticks, `--`, `/**/`, keywords SQL
- Fix appliqué le 28/03/2026

**Double traitement email** ✅ RÉSOLU
- Marker `stage_output.write()` écrit dès s08, vérifié en s01 avant traitement

**Credentials Microsoft Graph (BLOQUEUR TOTAL)** ❌ EN ATTENTE
- `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET` → Azure AD
- Sans ces credentials, s01 (lecture emails) et s12 (envoi réponse) sont bloqués
- Demander credentials à l'administrateur Azure

### 🟠 P1 — Moteur central ✅ IMPLÉMENTÉ

- `src/engine/main.py` ✅ — boucle polling Flux A + B en parallèle
- `src/engine/dispatcher.py` ✅ — routing + Flux A s03→s12
- `context.py` ✅ — enrichi avec `output_response`, `output_actions`, `output_silent`
- `outlook.py` ✅ — `send_email()` implémenté (sendMail + createReply)
- `claude_client.py` ✅ — `generate_email_reponse_client()` implémenté
- `.env.example` ✅ — documenté (Anthropic + Azure AD + Dolibarr)
- `_config/claude_config.md` ✅ — créé (remplace openai_config.md)

### 🟠 P1 — Dashboard CRM ✅ IMPLÉMENTÉ

- `/api/clients` ✅ — tiers + agrégation devis + CA
- `/api/chat` ✅ — streaming Claude Sonnet avec snapshot Dolibarr
- `/api/kpis` ✅, `/api/stats` ✅, `/api/daf` ✅, `/api/ca-chart` ✅

### 🟠 P1 — Tests sécurisés (EN COURS)

- `test_claude_client.py` — à créer (3 appels parallèles s02)
- `test_graph_client.py` — à créer (bloqué par credentials Azure AD)
- `tests/run_with_openai.py` — à migrer vers claude_client

### 🟡 P2 — Freshprocess API

- 3 clés disponibles (avant_vente, commande, justif) — auth non découverte
- Lancer `python tests/test_freshprocess.py` pour trouver le format d'auth
- Documenter dans `_config/freshprocess_config.md`

### 🟡 P2 — Fiabilité pipeline

- Pipeline non-idempotent après s08 : s09/s10/s11 peuvent rejouer → stages doivent relire le devis_id depuis result.json
- Sans sortfield, limit=200 Dolibarr → ordre indéterminé → KPIs CA potentiellement incomplets

### ⚪ P3 — Nice to have

- Cron toutes les 5 min en heures ouvrées (8h-18h lun-ven)
- Alertes erreurs critiques (log `pipeline_errors.json`)
- Refresh token Outlook automatisé (`scripts/refresh_outlook_token.py`)

---

## Décisions d'architecture importantes

### Imposition calculée en Python, pas dans le prompt IA
`src/utils/imposition.py` fait le calcul poses/feuilles en post-processing → fiable, traçable, testable.

### HTML stripping avant envoi à l'IA
`src/utils/html_cleaner.py` nettoie les corps emails Outlook avant tout appel Claude → réduit le bruit de 33-56%.

### Score SCORE_DEVIS calculé en Python
Claude fournit uniquement les alertes sémantiques. Le score 0-10 est calculé par `imposition.calculer_score()`.

### Dolibarr sortfield supprimé
Cette instance ne supporte pas les colonnes de tri standard. Tous les appels utilisent `limit=N` sans sortfield.
**Impact** : KPIs CA mois peuvent être incomplets si les 200 factures retournées ne couvrent pas le mois en cours.

### Dolibarr est en production
Les tests d'écriture (`test_dolibarr.py`) sont GET-only. Tout futur test write doit prévoir un cleanup explicite.

---

## Tests disponibles

```bash
# Tests sans API (Python pur — toujours disponibles)
python tests/run_dataset.py              # 3 datasets, 0 API requise

# Tests avec Claude réel (ANTHROPIC_API_KEY requise)
python tests/run_with_openai.py          # → à migrer vers claude_client

# Tests connecteurs (read-only, prod safe)
python tests/test_dolibarr.py            # connexion + GET endpoints
python tests/test_dolibarr.py --full     # + JSON brut du 1er objet
python tests/test_freshprocess.py        # découverte auth Freshprocess

# À créer
python tests/test_claude_client.py       # 3 appels parallèles s02
python tests/test_graph_client.py        # réception + envoi Graph API (dry-run)

# Dashboard
uvicorn dashboard.app:app --reload --port 8080
```

---

## Points de vérification humaine recommandés

- **Après s02** : vérifier `soc_nom`, `email`, `nom_projet` extraits par Claude
- **Après s06** : vérifier les composants d'impression (formats, grammages, impositions)
- **Après s08** : vérifier le devis dans Dolibarr avant archivage (s09-s11)
- **Dashboard agent.html** : interface de validation 3 panneaux avant tout envoi/écriture

---

## Principe : limiter les échanges clients au strict nécessaire

**Règle absolue** : le système ne doit jamais envoyer plusieurs emails au même client sans validation humaine explicite.

### Contraintes d'envoi

| Situation | Comportement attendu |
|-----------|---------------------|
| Pipeline Flux A complet (s12) | **1 seul email** CONFIG_CLIENT_v2026 — jamais deux envois pour le même email entrant |
| Relance automatique | Interdite sans validation humaine — proposer dans `output_actions`, statut `pending` |
| Accusé de réception + devis en même message | Toujours fusionner en **1 email** (ne pas envoyer un AR puis un devis séparément) |
| Email de suivi (Flux B) | Log interne Dolibarr uniquement — pas d'email client automatique sauf demande explicite |
| Erreur pipeline → retry | Vérifier `ctx.output_response.status` avant tout renvoi — ne jamais renvoyer si `sent` |

### Règles de rédaction (s12 / reponse-client)

- **Pas de sur-communication** : un email bien construit vaut mieux que 3 emails courts
- **Pas de confirmation de confirmation** : ne pas envoyer "votre message a bien été reçu" si un email complet (CONFIG_CLIENT_v2026) suit dans la foulée
- **CC systématique** : toujours mettre contact@in-pressco.com en copie de chaque email client envoyé
- **Pas de rappel automatique sans délai minimal** : toute relance proposée par `agenda-inpressco` respecte les délais — +7j devis, +5j BAT, +3j facture

### Garde-fous techniques

- `ctx.output_response.status` passe à `"sent"` dès l'envoi réel — empêche un double envoi en cas de retry
- `s12` vérifie que l'email expéditeur n'est pas une adresse InPressco avant d'envoyer
- Tout email supplémentaire (relance, PDF séparé, AR intermédiaire) passe obligatoirement par `validation-qc-inpressco` avant envoi
