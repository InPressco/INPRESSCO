# ANALYSE SYSTÈME COMPLET — InPressco MWP + SOLEIL MWP
*Généré le 30/03/2026 — Lecture architecte IA*

---

## 1. IDENTITÉ DES DEUX PROJETS

| Aspect | inpressco-mwp | SOLEIL-mwp |
|--------|--------------|------------|
| **Rôle** | Pipeline devis — Python orchestre, Claude est un outil | Système nerveux central — Claude est le seul cerveau |
| **IA** | Appelée dans le code Python (claude_client.py) | Claude.AI exclusivement via MCP tools |
| **Pipeline** | Séquentiel s01→s12 automatique | Claude décide, propose, l'humain valide |
| **DB** | Pas de DB locale | DB SOLEIL : 9 tables, mémoire vivante |
| **Scope** | Pipeline devis InPressco uniquement | Tout : business + marketing + personnel + stratégie |
| **Scheduler** | Polling Outlook toutes les N secondes | 4 crons + hook Phase 2 notification |
| **Skills** | Injectés dans les system prompts du code | Appliqués par Claude selon le contexte |
| **Version** | Moteur v2 — Flux A→C implémentés | Hub MCP v1 — 55+ tools, DB opérationnelle |

---

## 2. VISION FONDATRICE (partagée — source : CLAUDE.md)

```
InPressco est un moteur de développement, porteur d'une vision futuriste
et raisonnée — symbole de l'évolution et de l'adaptation de l'homme
dans son environnement futur.
```

**3 principes non-négociables :**
1. Transparence — chaque action lisible
2. Sobriété — faire moins, le faire vraiment bien
3. Humanité — l'IA exécute, l'humain décide et pilote

**Règle d'or :**  Toute action irréversible (email, Dolibarr, fichier) requiert validation humaine. Aucune exception.

---

## 3. ARCHITECTURE inpressco-mwp

### 3.1 Grille des couches (L0→L7)

| Couche | Composant | Fichier | Volonté initiale |
|--------|-----------|---------|-----------------|
| L0 | Identité workspace | CLAUDE.md, CONTEXT.md | Règles absolues + vision |
| L1 | Config + secrets | src/config.py, _config/*.md | Variables centralisées, assertions au démarrage |
| L2 | Connecteur IA | src/connectors/claude_client.py | Pont IA pur — traduit besoins métier en appels Claude |
| L2 | Connecteur ERP | src/connectors/dolibarr.py | CRUD sécurisé Dolibarr — sanitisation stricte |
| L2 | Connecteur mail | src/connectors/outlook.py | Accès messagerie — lecture + envoi uniquement |
| L3 | Middleware | src/middleware/context.py | Mémoire du run — objet mutable unique partagé |
| L3 | Pipeline | src/middleware/pipeline.py | Exécution séquentielle steps + StopPipeline |
| L4 | Steps Flux A | src/steps/flux_a/steps.py | Orchestration s01→s13 (nouveau devis) |
| L4 | Steps Flux B | src/steps/flux_b/steps.py | Orchestration s01→s03 (suivi devis ETUDE) |
| L4 | Steps Flux C | src/steps/flux_c/steps.py | Orchestration sc01→sc07 (emails fournisseurs) |
| L5 | Utils métier | src/utils/imposition.py | Calcul imposition Python pur — zéro IA |
| L5 | Utils métier | src/utils/devis_builder.py | Construction lignes Dolibarr — transformation Python pur |
| L5 | Utils métier | src/utils/html_cleaner.py | Nettoyage HTML emails — réduction bruit uniquement |
| L6 | Engine | src/engine/main.py | Boucle polling Flux A + B en parallèle |
| L6 | Dispatcher | src/engine/dispatcher.py | Routing email → chaîne — décision unique et traçable |
| L7 | Dashboard | dashboard/app.py | Monitoring + CRM léger — lecture + chat Claude |
| META | Source vérité | core/system_reference.py | Référentiel 30 skills, 6 chaînes, conventions |
| META | Outils système | tools/sentinel.py, tools/system_verify.py | Autodiagnostic — jamais de logique métier |

### 3.2 Flux disponibles

**Flux A — Nouveau devis (s01→s13)**
```
s01  Récupération email depuis FLUX_INPRESSCO (drop zone universelle)
     → anti-doublon via stage_output marker
s02  3 appels Claude séquentiels (délai 13s anti-rate-limit) :
     ① extract_client_data   [Opus, temp=0, max=2048] → ctx.client_data
     ② analyse_sentiment     [Haiku, temp=0, max=500]  → ctx.email_sentiment
     ③ classify_routing      [Haiku, temp=0, max=500]  → ctx.routing_category
s03  Validation routing → seule catégorie NEW_PROJECT poursuit
     Nettoyage exclusions InPressco (soc_nom, email)
s04  find_or_create_thirdparty → ctx.socid, ctx.soc_nom
     fallback : socid=16 "CLIENT A RENSEIGNER"
s05  Récupération PJ non-inline → ctx.attachments
s06  Analyse besoin impression [Opus] + post_process_composants() Python
     → ctx.composants_isoles, ctx.synthese_contexte
s07  build_lines(composants, synthese) → ctx.devis_lines
s08  create_proposal → validate → set_to_draft → write marker anti-doublon
     → créer sous-dossier Outlook "{devis_ref} — {soc_nom}"
s09  Upload PJ → dossier devis Dolibarr
s10  log_email_to_agenda → événement Dolibarr lié au devis
s11  Archivage Outlook : renommer [Traité], déplacer, effacer marker
s12  Email interne "GO requis" avec bouton → ctx sauvegardé en DB (SOLEIL)
     STOP — attend validation humaine (clic GO)
s13  Envoi email CONFIG_CLIENT_v2026 au client
     → déclenchement manuel via /api/go/{devis_id}
```

**Dispatcher routing (dispatcher.py)**
```
NEW_PROJECT           → flux_a  (s03→s12+s13)
PROJECT_UPDATE        → mark [Routé-] (géré Flux B dans ETUDE)
SUPPLIER_QUOTE        → flux_c  (sc01→sc07) → TARIF_FOURNISSEURS
SUPPLIER_INVOICE      → flux_c  (sc01→sc07) → ADMIN
ADMINISTRATIF_GENERALE→ mark + move ADMIN
VISUAL_CREATION       → mark + move COMMERCE
PRICE_REQUEST         → mark + move COMMERCE
ACTION                → mark + move COMMERCE
UNKNOWN               → mark + move COMMERCE
```

### 3.3 Contrats d'intention — inpressco-mwp

| Composant | Intent | Invariants |
|-----------|--------|-----------|
| `claude_client.py` | Pont IA pur | Jamais logique métier · jamais accès Dolibarr · retry 3x sur rate limit |
| `dolibarr.py` | CRUD sécurisé | Sanitisation stricte (quotes/`;`/backticks/keywords SQL) · GET avant POST |
| `outlook.py` | Accès messagerie | Jamais décision métier · jamais write Dolibarr |
| `context.py` | Mémoire du run | Un seul Context par run · errors toujours dans `ctx.errors[]` |
| `flux_a/steps.py` | Orchestration s01→s13 | Chaque step = responsabilité unique · ordre immuable · pas import connecteur direct |
| `dispatcher.py` | Routing unique | Une entrée = une chaîne · toutes les catégories couvertes |
| `imposition.py` | Calcul Python pur | Fonctions pures · zéro API · résultat déterministe |
| `devis_builder.py` | Construction lignes | Zéro API · entrée composants → sortie list[dict] |
| `html_cleaner.py` | Strip bruit HTML | Pas de parsing sémantique · perte information interdite |
| `dashboard/app.py` | Monitoring CRM | Pas écriture Dolibarr directe · données sensibles masquées |
| `core/system_reference.py` | Source vérité | Lecture seule · versionné · synchronisé SOLEIL |

---

## 4. ARCHITECTURE SOLEIL-mwp

### 4.1 Structure des modules

| Module | Rôle | Volonté initiale |
|--------|------|-----------------|
| `mcp_server.py` | Hub MCP — 10 groupes, 55+ tools | Aucun appel IA — bras de Claude uniquement |
| `mcp_server_http.py` | Exposition SSE + ngrok pour Claude.AI web | Transport layer — zéro logique métier |
| `database/schema.sql` | 9 tables DB SOLEIL | Mémoire vivante — persistance cross-session |
| `database/db.py` | CRUD DB — toutes les fonctions | Accès DB pur — zéro logique métier |
| `config.py` | Config centralisée multi-entités | Variables env + IDs Dolibarr + chemins SOLEIL |
| `pipeline/context.py` | Contexte pipeline (même rôle inpressco) | Mémoire run — objet mutable unique partagé |
| `pipeline/flux_a.py` | Steps récepteurs (Claude a analysé en amont) | Réception résultats Claude via MCP — zéro appel IA |
| `connectors/dolibarr.py` | CRUD Dolibarr | Même contrat que inpressco — sanitisation stricte |
| `connectors/outlook.py` | Client Graph API synchrone | Collecte emails brute pour daemon |
| `processing/imposition.py` | Calcul imposition | Python pur — identique inpressco |
| `processing/devis_builder.py` | Construction lignes | Python pur — identique inpressco |
| `processing/file_classifier.py` | Classifieur fichiers déterministe | 3 niveaux : chemin→entité→type — zéro IA |
| `watcher/arborescence_watcher.py` | File watcher watchdog | Indexation auto tout nouveau fichier SOLEIL/ |
| `brain/sentinel.py` | Autodiagnostic système | Contrôles DB + Dolibarr + scheduler + anti-patterns |
| `brain/strategic_engine.py` | Intelligence live Dolibarr | Snapshots, projections, RFM |
| `scheduler/jobs.py` | 4 crons déclarés | Briefing / snapshot / relances / synthèse hebdo |
| `core/system_reference.py` | Source vérité (identique inpressco) | Référentiel partagé |

### 4.2 DB SOLEIL — 9 tables

```
emails              → Historique complet emails (pending → processed)
memory              → Mémoire contextuelle (clients, routines, préférences, pipeline_pending)
ideas               → Idées et réflexions structurées
strategic_log       → Journal décisions stratégiques
analytics_snapshots → Snapshots Dolibarr datés (base projections 90j)
media               → Fichiers BAT, visuels, PDF
conversations       → Historique Claude cross-session
social_drafts       → Drafts réseaux sociaux
pipeline_events     → Audit trail complet (toutes les actions)
scheduler_jobs      → État et historique des crons
```

### 4.3 MCP Tools — 10 groupes

```
email_*         → get_pending, get_by_id, mark_processed, search, send
dolibarr_*      → CRUD complet (identique inpressco)
memory_*        → save, get_client, get_briefing, search, save_idea, save_strategic
media_*         → list, search
processing_*    → analytics_snapshot, build_devis_lines, compile_insights
system_*        → health, get_logs, log, scheduler_status/trigger, schedule_task
brain_*         → sentinel_status, generate_reports, get_report, get_synthesis
context_*       → load (chargement contexte cross-session)
n8n_*           → list_workflows, trigger
arborescence_*  → get_tree, list, create_entity, save_file, move_file, search, list_templates
pipeline_*      → list_steps, run_step, list_pending_go, send_go
trieur_*        → scan, preview, classify, suggest, move, run_auto, report
```

### 4.4 Scheduler — 4 crons

| Job | Heure | Action |
|-----|-------|--------|
| `briefing_morning` | 07h25 lun-ven | Emails pending + devis à relancer + factures retard → memory |
| `snapshot_analytics` | 18h00 quotidien | Snapshot Dolibarr → analytics_snapshots |
| `relances_auto` | 09h00 quotidien | Détecte relances → memory type:relance |
| `weekly_synthesis` | Vendredi 17h00 | Synthèse semaine → strategic_log |

### 4.5 Différence architecturale clé — s02 et s06

**inpressco-mwp** : le code Python appelle Claude (claude_client.py) dans s02 et s06.
**SOLEIL-mwp** : Claude analyse EN AMONT et passe les résultats via MCP tools.
Les steps s02 et s06 de SOLEIL sont des "récepteurs" — `s02_set_client_data`, `s06_set_composants`.

---

## 5. CONFIG PARTAGÉE — Constantes communes

Les deux projets partagent **les mêmes constantes Dolibarr** :

```python
DOLIBARR_SOCID_INCONNU           = 16
DOLIBARR_USER_OWNER_ID           = 166
DOLIBARR_PRODUCT_IMPRESSION      = "35700"
DOLIBARR_COND_REGLEMENT_BAT      = 15
DOLIBARR_MODE_REGLEMENT_VIREMENT = 2
DOLIBARR_MODEL_PDF               = "azur_fp"
DOLIBARR_SPECIAL_CODE_CONTEXTE   = 104777
DOLIBARR_SPECIAL_CODE_DESCRIPTIF = 104778

# Exclusions InPressco (données internes)
INPRESSCO_EXCLUDE_EMAILS  = ["@in-pressco.com"]
INPRESSCO_EXCLUDE_NAMES   = ["InPressco", "In'pressco", "Nicolas Bompois", "Alys"]
```

**IDs dossiers Outlook identiques dans les deux projets :**
```
INBOX              = AAMkADE4...EEMAA=
FLUX_INPRESSCO     = AAMkADE4...rtifAAA=
COMMERCE           = AAMkADE4...iRaAAA=
ETUDE              = AAMkADE4...iRZAAA=
GENERAL            = AAMkADE4...iRYAAA=
ADMIN              = AAMkADE4...iRXAAA=
```

**Modèles Claude calibrés :**
```
claude-opus-4-6              → extraction complexe (temp=0, max=2048)
claude-haiku-4-5-20251001    → routing/sentiment (temp=0, max=500)
claude-sonnet-4-6            → rédaction email (temp=0.3, max=4000)
```

---

## 6. BLOQUEURS ACTIFS

| Bloqueur | Impact | Statut |
|----------|--------|--------|
| Credentials Azure AD manquants | s01 (lecture emails) + s12/s13 (envoi) bloqués dans les 2 projets | ❌ EN ATTENTE |
| Dolibarr écriture non testée | create_proposal, upload_document, agenda — testés GET uniquement | ❌ NON VALIDÉ |
| Freshprocess API | 3 clés disponibles, auth non découverte | ❌ NON TESTÉ |
| `openai_client.py` encore présent | Dead code — remplacé par claude_client.py | ⚠️ À SUPPRIMER |
| `openai_config.md` encore présent | Dead config — remplacé par claude_config.md | ⚠️ À SUPPRIMER |
| `run_with_openai.py` non migré | Test obsolète — référence OpenAI | ⚠️ À MIGRER |

---

## 7. ANTI-PATTERNS DÉTECTÉS (état 30/03/2026)

### inpressco-mwp

| # | Fichier | Problème | Priorité |
|---|---------|---------|---------|
| 1 | `src/steps/flux_a/steps.py:s02` | Délai asyncio.sleep(13) entre appels = workaround rate-limit fragilisant le pipeline | P1 — à monitorer |
| 2 | `src/connectors/openai_client.py` | Dead code — connecteur OpenAI abandonné mais toujours présent | P2 — supprimer |
| 3 | `src/engine/dispatcher.py` | Import direct de tous les steps (long list) — couplage fort L6→L4 | P3 — cosmétique |
| 4 | `dashboard/index.html.bak`, `.bak2` | Fichiers de backup non nettoyés | P3 — cleanup |

### SOLEIL-mwp

| # | Fichier | Problème | Priorité |
|---|---------|---------|---------|
| 1 | `mcp_server_http.py` | DNS rebinding protection désactivée | P1 — sécurité à vérifier en prod |
| 2 | `pipeline/flux_a.py:s12` | `import sqlite3` inutilisé importé à l'intérieur d'une fonction | P3 — cosmétique |
| 3 | `connectors/outlook.py` | Synchrone (non-async) contrairement à inpressco — incompatibilité si pipeline async | P2 — à homogénéiser |

### Divergence entre les deux projets

| Point | inpressco | SOLEIL | Risque |
|-------|-----------|--------|--------|
| `context.py` — champs `supplier_*` | ✅ présents (Flux C) | ❌ absents | SOLEIL ne gère pas Flux C |
| `s01` — dossier source | FLUX_INPRESSCO (drop zone) | DEVIS (dossier ciblé) | SOLEIL doit aligner sur drop zone |
| `s08` — marker anti-doublon | Via `stage_output` fichier | Via DB SOLEIL `pipeline_events` | Architecture correcte, mécanismes différents |
| `system_reference.py` | Version 2026-03-28 | Version 2026-03-28 | ✅ Synchronisé |

---

## 8. SKILLS — REGISTRE ET MAPPING PIPELINE

**27 skills actifs dans les deux workspaces :**

```
Infrastructure
  droits-profils-inpressco   → Gate sécurité — toujours en premier
  gestion-erreurs-inpressco  → Filet de sécurité universel
  orchestrateur-inpressco    → Chef d'orchestre multi-skills
  validation-qc-inpressco    → Dernier filtre avant action irréversible

CRM / Client
  memoire-client-inpressco   → Socle CRM — charge contexte complet tiers
  mail-routing-inpressco     → 8 catégories routing email
  analyse-sentiment-email    → Profil psycho-communicationnel
  inpressco-commerce         → Expert imprimeur — brief, tarif, email CONFIG_CLIENT

Dolibarr / Data
  dolibarr-query-inpressco   → CRUD Dolibarr (toutes opérations)
  analyse-transversale-inpressco → Analyse RFM, tendances, anomalies
  controleur-gestion-inpressco → DAF virtuel — tréso, CA, impayés, marge

Production / Documents
  archiveur-inpressco        → Classification + nommage + dépôt fichiers
  generation-pdf-inpressco   → PDF devis/factures (API Dolibarr ou reportlab)
  reponse-client-inpressco   → Rédaction + envoi emails clients
  agent-acheteur-inpressco   → Demandes de prix fournisseurs
  suivi-commande-inpressco   → Statut commandes production
  agenda-inpressco           → RDV, relances, rappels — Dolibarr ↔ Outlook

Créatif / Mémoire
  projets-artefacts-inpressco → Mémoire productions Claude cross-sessions
  charte-graphique-inpressco  → Extraction + mémorisation chartes clients
  bdd-images-query-inpressco  → Garde-fou anti-doublon images
  planche-archi-inpressco     → Prompts Nanobanana — planches techniques
  ux-inpressco               → Composants React/HTML

Stratégie / Humain
  guide-evolution-inpressco  → Développement personnel + spiritualité
  veille-prix-inpressco      → Benchmark concurrents (Exaprint, etc.)
  chat-to-db-inpressco       → Pont conversation → base de données

Exclusifs SOLEIL
  patrimoine-inpressco       → Gestion patrimoine immobilier
  architecte-ia-inpressco    → CTO virtuel — review code + MWP (présent dans les deux)
```

**Mapping skills → steps pipeline :**
```
s02  mail-routing + analyse-sentiment (inpressco : appels Claude · SOLEIL : MCP tools)
s03  mail-routing validation
s04  dolibarr-query-inpressco
s06  inpressco-commerce (enrichissement matières + finitions)
s08  dolibarr-query-inpressco + validation-qc-inpressco (gate avant création)
s09  archiveur-inpressco
s10  agenda-inpressco
s12  generation-pdf-inpressco + projets-artefacts (SOLEIL : email interne GO)
s13  reponse-client-inpressco (inpressco) / manuel via GO (SOLEIL)
```

---

## 9. CONVENTION VALIDATIONS ⏸

Tout skill qui génère une action nécessitant validation humaine crée un événement Dolibarr :
```
done=0, label "⏸ [skill] — [action] — [ref]"
```

**7 points de validation actifs :**
```
⏸ acheteur        → email demande de prix fournisseur prêt
⏸ réponse-client  → email client rédigé, prêt à envoyer
⏸ validation-qc   → devis créé/modifié, prêt à valider
⏸ pdf             → PDF généré, prêt à envoyer
⏸ archiveur       → fichier prêt à déposer, nommage à confirmer
⏸ chat-to-db      → données conversationnelles prêtes à persister
⏸ routing-ambigu  → email non classifié, catégorie à confirmer
```

Cycle : `done=0 créé → utilisateur répond OUI/NON/MODIFIER → done=1`
Consultation : `GET /agendaevents?done=0` + filtre label `⏸`

---

## 10. ÉTAT FONCTIONNEL PAR COMPOSANT

### inpressco-mwp

| Composant | État | Note |
|-----------|------|------|
| Flux A s01→s07 | ✅ Opérationnel | Bloqué sur credentials Azure AD en prod |
| Flux A s08 (devis) | ✅ Opérationnel | Dolibarr écriture non testée en prod |
| Flux A s09→s11 | ✅ Opérationnel | Idem bloqueur Azure AD |
| Flux A s12 (GO interne) | ✅ Opérationnel | Email interne → attend clic GO |
| Flux A s13 (email client) | ✅ Opérationnel | Déclenché via /api/go/{id} |
| Flux B s01→s03 | ✅ Opérationnel | Bloqué Azure AD |
| Flux C sc01→sc07 | ✅ Implémenté | À tester |
| Dashboard 14 endpoints | ✅ Opérationnel | |
| API /api/health | ✅ | |
| API /api/synthesis | ✅ | Live Dolibarr |
| Tests run_dataset.py | ✅ 3/3 OK | Sans API |
| Sentinel (tools/) | ✅ | Score 100/100 (28/03/2026) |

### SOLEIL-mwp

| Composant | État | Note |
|-----------|------|------|
| MCP Server (55+ tools) | ✅ Opérationnel | Connecté à Dolibarr |
| DB SOLEIL | ✅ Opérationnelle | 9 tables, 1929 fichiers indexés |
| Trieur | ✅ Opérationnel | scan/classify/move/auto/index |
| Watcher | ✅ Actif | ~/Documents/SOLEIL/ — indexation auto |
| Index JSON | ✅ 4,6 Mo | 1929 fichiers, 717 avec contenu extrait |
| Scheduler | ✅ 4 crons | snapshot_analytics validé |
| Daemon email | ❌ Bloqué | Credentials Azure AD manquants |
| email_send | ❌ Bloqué | Idem |
| Pipeline flux_a | ✅ Structuré | Bloqué Azure AD |
| Sentinel (brain/) | ✅ | Vérifie DB + Dolibarr + scheduler + anti-patterns |

---

## 11. NEXT STEPS PRIORISÉS

### P0 — Débloqueur unique
```
→ Configurer Azure AD :
  OUTLOOK_TENANT_ID, OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET
  → renseigner dans .env des deux projets
  → test : python tests/test_outlook.py (inpressco) | system_health (SOLEIL)
```

### P1 — Validation prod Dolibarr écriture
```
→ Créer devis test + cleanup explicite
→ Valider create_proposal / upload_document / create_agenda_event
→ Documenter dans CONTEXT.md
```

### P1 — Nettoyage inpressco-mwp
```
→ Supprimer src/connectors/openai_client.py (dead code)
→ Supprimer _config/openai_config.md (dead config)
→ Migrer tests/run_with_openai.py → tests/test_claude_client.py
→ Supprimer dashboard/index.html.bak, .bak2
```

### P2 — Aligner drop zone Outlook (SOLEIL)
```
→ SOLEIL pipeline/flux_a.py s01 : lire depuis FLUX_INPRESSCO (drop zone)
  au lieu du dossier DEVIS ciblé
→ Aligner sur inpressco-mwp (OUTLOOK_FOLDER_PENDING = FLUX_INPRESSCO)
```

### P2 — Tests inpressco-mwp
```
→ tests/test_claude_client.py : 3 appels séquentiels s02 avec email_01
→ tests/test_graph_client.py  : lecture email (dry-run) via Graph API
```

### P3 — Freshprocess API
```
→ python tests/test_freshprocess.py → découvrir format auth
→ Documenter dans _config/freshprocess_config.md
```

---

## 12. FICHIERS À LIRE EN PRIORITÉ (pour toute intervention)

```
Layer 0  CLAUDE.md                    → Vision + règles absolues + filtre permanent
Layer 0  CONTEXT.md                   → État projet + roadmap + failles
Layer 1  src/config.py                → Toutes les constantes (IDs Dolibarr, dossiers Outlook)
Layer 2  src/connectors/claude_client.py → Interface IA (calibration modèles, retry)
Layer 2  src/connectors/dolibarr.py   → Sanitisation, patterns CRUD
Layer 3  src/middleware/context.py    → Contrat de données entre steps
Layer 4  src/steps/flux_a/steps.py   → Pipeline principal s01→s13
Layer 6  src/engine/dispatcher.py    → Table de routing complète
Layer META  core/system_reference.py → Source de vérité (skills, conventions, anti-patterns)
```

---

*Ce fichier est un snapshot 30/03/2026. Il ne se met pas à jour automatiquement.*
*Recréer si un changement architectural majeur est apporté.*
