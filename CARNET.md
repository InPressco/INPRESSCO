# Carnet de bord — InPressco Pipeline MWP

---

## Session du 28/03/2026 — Mise à jour système complète MWP

### Ce qui a été fait — Implémentations codebase

**1. Fix sécurité P0 — Injection SQL `dolibarr.py`**
- `_sanitize_sqlfilter_value()` renforcé : supprime `;`, backticks, `--`, `/**/`, et keywords SQL (union, select, drop, insert, exec, xp_)
- Fix appliqué sur les deux appels `find_thirdparty()` (email + name)

**2. `s12_send_email_client()` — Step manquant implémenté (`flux_a/steps.py`)**
- Calcule le total HT depuis les lignes du devis
- Génère le corps HTML via `claude_client.generate_email_reponse_client()` (8 blocs CONFIG_CLIENT_v2026)
- Envoie via `outlook.send_email()` en réponse au message source (thread conservé)
- Log une note interne Dolibarr (agendaevents) sur le devis
- Stocke dans `ctx.output_response` et `ctx.output_silent`
- Robuste : échec envoi n'arrête pas le pipeline (l'email peut être renvoyé manuellement)

**3. `generate_email_reponse_client()` — Nouvelle méthode `claude_client.py`**
- Modèle : Claude Opus 4.5
- Format : 8 blocs CONFIG_CLIENT_v2026 (accusé réception → conclusion bienveillante)
- "Phrase Paola" adaptée post-devis : "Nous vous adressons ci-joint votre devis {ref}..."
- Adapte le registre selon `email_sentiment.profil` et `email_sentiment.urgence`
- Retourne HTML brut prêt à envoyer

**4. `send_email()` — Nouvelle méthode `outlook.py`**
- Deux modes : `sendMail` (envoi direct) et `createReply` (conserve le thread)
- Support CC
- Authentification MSAL token (même flux que les autres méthodes)

**5. `context.py` — Champs output ajoutés**
- `output_response: dict` — réponse email (to, subject, body_html, status)
- `output_actions: list[dict]` — actions Dolibarr à valider
- `output_silent: list[dict]` — traitements automatiques logués

**6. `dispatcher.py` — s12 câblé dans Flux A**
- `build_flux_a()` : s03→s12 (11 steps + 1 nouveau)
- Import `s12_send_email_client` ajouté

**7. `config.py` — Nettoyage legacy OpenAI**
- `OPENAI_API_KEY` et `OPENAI_MODEL` supprimés
- Migration Claude complète

**8. `.env.example` — Mis à jour**
- Suppression `OPENAI_API_KEY`
- Ajout `ANTHROPIC_API_KEY` et `OUTLOOK_USER_EMAIL`
- Documentation complète

**9. `_config/claude_config.md` — Créé**
- Remplace `openai_config.md`
- Documente les 5 méthodes Claude + le chat dashboard

**10. `CONTEXT.md` — Mis à jour**
- État système reflète la réalité (engine/ déjà créé, 24 skills, s12 implémenté)
- P0 injection SQL marqué CORRIGÉ
- Tous les P1 moteur/dashboard marqués IMPLÉMENTÉS

**Seul bloqueur restant : credentials Azure AD (Outlook)**
- s01 (lecture emails), s12 (envoi réponse) sont fonctionnels côté code
- Bloqués uniquement par l'absence de OUTLOOK_TENANT_ID / CLIENT_ID / CLIENT_SECRET

---

## Session du 28/03/2026 — Ajout skill planche-archi-inpressco

### Ce qui a été fait

**Installation du skill `planche-archi-inpressco`**
- Création de `.claude/skills/planche-archi-inpressco/SKILL.md` — agent prompt Nanobanana complet
- Fonctionnalités : Visual Mood Engine (4 univers), structure des vues par type de produit, annotations 100% françaises, filigrane antifraude www.in-pressco.com, cartouche produit, ratio automatique
- Mise à jour `CLAUDE.md` : ajout dans la table des skills + section pipeline (`visual ←→ planche-archi-inpressco`)
- Intégrations documentées : dolibarr-query, memoire-client, charte-graphique, bdd-images-query, archiveur, projets-artefacts, validation-qc

**Logique du skill**
- Déclenchement automatique sur tout produit complexe/finition spéciale (même sans demande)
- Déclenchement sur mots-clés : dorure, gaufrage, vernis, reliure spéciale, découpe, pelliculage, format non standard, grammage élevé
- Déclenchement sur demandes explicites : "planche technique", "concept board", "multi-vues", "vue éclatée"
- Sortie JSON Nanobanana avec aspect_ratio auto (1:1 / 3:2 / 16:9) et résolution 4K PNG

**État skills au 28/03/2026 : 24 installés, 24 documentés, 1 désactivé intentionnellement**

---

## Session du 28/03/2026 — Ajout skill agent-acheteur-inpressco

### Ce qui a été fait

**Installation du skill `agent-acheteur-inpressco`**
- Création de `.claude/skills/agent-acheteur-inpressco/SKILL.md` — workflow complet 9 étapes
- Création de 4 fichiers de référence métier :
  - `references/faconnier.md` — terminologie + bloc technique façonnage
  - `references/papetier.md` — terminologie + bloc technique papier/support
  - `references/imprimeur.md` — terminologie + bloc technique impression
  - `references/finisseur.md` — terminologie + bloc technique finitions spéciales
- Mise à jour `CLAUDE.md` : ajout dans la table des skills + section pipeline (`buyer ←→ agent-acheteur-inpressco`)
- Intégrations documentées : dolibarr-query, memoire-client, reponse-client, validation-qc, gestion-erreurs, projets-artefacts

**Logique du skill**
- Classifie automatiquement le type de sous-traitant (façonnier / papetier / imprimeur / finisseur) depuis les mots-clés du devis
- Construit toujours 2-3 paliers de quantité (Q×0.5 / Q / Q×2, adaptés aux paliers métier)
- Détecte l'urgence depuis la date de livraison client et adapte le ton de l'email
- Identifie le fournisseur via Dolibarr (tag fournisseur) ou demande confirmation utilisateur
- Génère un email par type de sous-traitant si multi-prestation

**État skills au 28/03/2026 : 23 installés, 23 documentés, 1 désactivé intentionnellement**

---

## Session du 28/03/2026 — Verrouillage système

### Ce qui a été fait

**Audit de cohérence complet + verrouillage des skills**
- Inventaire des 22 skills installés vs references dans CLAUDE.md / CONTEXT.md
- Suppression des 3 skills fantômes : `extraction-tiers`, `imprimerie-workflow`, `inpressco-devis`
  → extraction-tiers : logique embarquée dans `openai_client.py::extract_client_data()`
  → imprimerie-workflow : n'a jamais été créé
  → inpressco-devis : rôle absorbé par `inpressco-commerce`
- Ajout des 4 skills manquants dans CLAUDE.md : `droits-profils-inpressco`, `dolibarr-query-inpressco`, `archiveur-inpressco`, `controleur-gestion-inpressco`
- Correction section "Intégration skills → pipeline MWP" : s02 documente les 3 appels GPT parallèles (déjà implémentés), s03 filtre sur NEW_PROJECT
- Marquage des TODOs P1 déjà réalisés : routing s02/s03, sentiment s02
- Documentation de la décision `_CATEGORIES_DEVIS = {"NEW_PROJECT"}`
- Note sur `notification-interne-inpressco` désactivée (alertes = log uniquement)
- CONTEXT.md : section "Données à ajouter dans le Context" → mise à jour → "champs déjà implémentés"

**État skills au 28/03/2026 : 22 installés, 22 documentés, 1 désactivé intentionnellement**

---

## Session du 25/03/2026 (suite — après-midi)

### Ce qui a été fait

**Corrections Dolibarr API**
- Suppression de tous les `sortfield` invalides (`p.datec`, `f.datef`, `c.date_commande`, `t.datec`)
  → cette instance Dolibarr/Freshprocess ne les reconnaît pas → erreur 503
- Fix dans `tests/test_dolibarr.py` ET `dashboard/app.py` `/api/kpis`
- L'API répond maintenant sur tous les endpoints (proposals, invoices, supplier_invoices, orders)

**Dashboard — câblage complet**
- Bouton "Lancer pipeline" → `POST /api/run` (affiche PID, rafraîchit status + runs après 3s)
- Ticker → dynamique depuis `/api/status` au lieu de texte hardcodé
- Table "Derniers devis" → alimentée par `devis_ouverts` de `/api/kpis` (données réelles Dolibarr)
- Table "Historique runs" → depuis `/api/runs` (données réelles pipeline.log)
- Connecteur Dolibarr → état réel (vert si `/api/kpis` répond)
- "Voir dans Dolibarr" → endpoint `/api/config` exposant l'URL de base
- Stages s01→s05 → se marquent "Terminé" si `stages/XX/output/result.json` existe
- Correction bug CSS : `.amber` appliqué au bon élément parent
- "GPT-4o" corrigé en "GPT-4.1-mini"
- Refresh : status toutes les 60s, KPIs toutes les 5min, runs toutes les 60s

**Analyse architecture — failles identifiées**
- Double traitement email (dévis créé + email non archivé = doublon au run suivant)
- Injection sqlfilters dans dolibarr.py (email/name non sanitisés)
- Layer 4 outputs absents (stages n'écrivent aucun result.json)
- Pipeline non-idempotent après s08
- Dashboard CRM manquant (liste_id.md)
- Tests Dolibarr write non sécurisés (prod active)
- Freshprocess API non authentifiée
- Refresh token Outlook sans renouvellement auto

---

## Session du 25/03/2026 (matin)

### Ce qui a été fait

**Analyse et refactoring architecture**
- Analyse complète du projet (layers 0→4, flux A+B, connecteurs, steps)
- `_config/openai_config.md` créé

**Amélioration des prompts IA**
- Retrait du calcul d'imposition du prompt GPT → déplacé en Python (`imposition.py`)
- Retrait du score numérique → calculé en Python par comptage de champs

**Nouveaux utilitaires Python**
- `src/utils/imposition.py` — poses, feuilles, score 0-10, alertes métier
- `src/utils/html_cleaner.py` — strip HTML emails Outlook avant envoi IA

**Steps mis à jour**
- `s02` : utilise `prepare_email_for_ai()` avant GPT
- `s06` : utilise `prepare_email_for_ai()` + `post_process_composants()` après GPT

**Dashboard**
- `dashboard/app.py` — Backend FastAPI complet
- `dashboard/index.html` — UI thème amber (IBM Plex Mono + Syne)
- `/api/kpis` — CA mois, impayés clients, fournisseurs, devis ouverts (Dolibarr live)

**Dataset de tests**
- 3 datasets JSON + `run_dataset.py` (3/3 PASS sans API)
- `run_with_openai.py` + `test_dolibarr.py` + `test_freshprocess.py`

### État des credentials au 25/03/2026

| Credential | Statut |
|------------|--------|
| `OPENAI_API_KEY` | ✅ Renseigné et fonctionnel |
| `DOLIBARR_API_KEY` | ✅ Testé (GET OK, écriture non testée) |
| `DOLIBARR_BASE_URL` | ✅ Renseigné |
| `OUTLOOK_TENANT_ID` | ❌ Placeholder |
| `OUTLOOK_CLIENT_ID` | ❌ Placeholder |
| `OUTLOOK_CLIENT_SECRET` | ❌ Placeholder |
| `OUTLOOK_REFRESH_TOKEN` | ❌ Placeholder |

---

## TODO — Prochaine session

### 🔴 P0 — Sécurité prod immédiate

- [x] **Sanitiser sqlfilters dans `src/connectors/dolibarr.py`** ✅ 27/03
  → `_sanitize_sqlfilter_value()` strip quotes, backslashes, chars de contrôle, tronque à 100 chars
  → Appliqué sur email et name avant insertion dans sqlfilters

- [x] **Protéger contre le double traitement email** ✅ 27/03
  → `write_stage_output()` / `read_stage_output()` dans `pipeline_helpers.py`
  → s08 écrit marker `{email_id, devis_id, devis_ref}` dès création du devis (avant validate)
  → s01 vérifie le marker après récupération de l'email → StopPipeline si doublon détecté
  → s11 efface le marker après archivage complet

### 🔴 P0 — Credentials Outlook (bloqueur end-to-end)

- [ ] **Azure AD → App registrations :**
  - `OUTLOOK_TENANT_ID` → Overview → Directory (tenant) ID
  - `OUTLOOK_CLIENT_ID` → Application (client) ID
  - `OUTLOOK_CLIENT_SECRET` → Certificates & secrets → New client secret

- [ ] **Générer le Refresh Token OAuth2**
  ```
  URL : https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize
        ?client_id={CLIENT_ID}&response_type=code
        &redirect_uri=http://localhost:8080/callback
        &scope=Mail.ReadWrite offline_access
  Puis : POST token exchange → récupérer refresh_token
  ```

### 🔴 P0 — Aligner prompt extraction avec skill `extraction-tiers`

- [x] **Extraction client intégrée directement dans `openai_client.py::extract_client_data()`** ✅ 28/03
  → Le skill `extraction-tiers` n'existe pas en fichier `.claude/skills/` — sa logique est embarquée dans le code Python
  → Format JSON unifié dans `openai_client.py` : soc_nom, contact_nom, contact_prenom, email, nom_projet, phone, zip, town, address, siren, siret
  → CLAUDE.md et CONTEXT.md mis à jour pour refléter cet état

---

### 🟠 P1 — Layer 4 : outputs pipeline

- [ ] **Ajouter `write_stage_output(stage_num, data)` dans `src/utils/`**
  → Écrit `stages/0N_*/output/result.json`
  → Appelé depuis `main.py` après chaque stage majeur
  → Permet replay depuis un stage sans tout relancer
  → Débloque les indicateurs stage dans le dashboard

### 🟠 P1 — Intégrer `mail-routing-inpressco` dans s02/s03

- [x] **Routing intégré dans `s02_extract_client_ai` + `s03_clean_data`** ✅ 28/03
  → `openai_client.py::classify_email_routing()` : 8 catégories (NEW_PROJECT, VISUAL_CREATION, SUPPLIER_INVOICE, PROJECT_UPDATE, SUPPLIER_QUOTE, PRICE_REQUEST, ACTION, UNKNOWN)
  → Appel GPT parallèle dans s02 (asyncio.gather, 3 appels simultanés) → `ctx.routing_category`
  → s03 filtre : `_CATEGORIES_DEVIS = {"NEW_PROJECT"}` → StopPipeline sur toute autre catégorie
  → DÉCISION DOCUMENTÉE : seule NEW_PROJECT crée un devis en Flux A. Les autres catégories (VISUAL_CREATION, PROJECT_UPDATE...) nécessiteront des flux dédiés (Flux C, D...).

### 🟠 P1 — Intégrer `analyse-sentiment-email` dans s02

- [x] **Appel parallèle analyse sentiment dans `s02_extract_client_ai`** ✅ 28/03
  → `openai_client.py::analyse_sentiment_email()` intégré dans asyncio.gather (s02)
  → Stocké dans `ctx.email_sentiment` : sentiment, urgence, profil, intention
  → TODO restant : afficher badge urgence="critique" dans dashboard (table "Derniers devis")

### 🟠 P1 — Nouveau step s12 : email réponse client

- [ ] **Créer `s12_send_client_response` dans `src/steps/flux_a/steps.py`**
  → Lire `user/inpressco-devis/SKILL.md` + `references/finitions.md` + `references/matieres.md`
  → Lire `user/inpressco-commerce/SKILL.md`
  → Générer email CONFIG_CLIENT_v2026 (ton B2B haut de gamme, sans gras, phrase Paola)
  → Inclure : ref devis créé (depuis ctx.devis_ref), suggestions matières, fourchette HT
  → Envoyer via Outlook Graph API (répondre au fil de l'email original)
  → Stocker le texte généré dans `ctx.email_reponse_client`
  → **Dépend de** : Outlook credentials (bloqueur P0)

### 🟠 P1 — Tests Dolibarr écriture (prod safe)

- [ ] **Créer section write dans `tests/test_dolibarr.py`**
  → Nécessite flag `--write` explicite pour activer
  → Crée un tiers TEST, un devis TEST → vérifie → supprime immédiatement
  → Log "CLEANUP OK" pour confirmer que rien n'est laissé en prod
  → Tester : create_proposal, validate_proposal, set_to_draft, upload_document, create_agenda_event

### 🟠 P1 — Dashboard CRM avec `ux-inpressco` + `frontend-design`

- [ ] **Utiliser le skill `ux-inpressco` pour générer les composants CRM**
  → Déclencher avec : "génère le composant CRM dashboard suivi clients"
  → Produit : composant HTML/React prêt à intégrer dans `dashboard/index.html`
  → Demander : table clients (nom, nb devis, CA total, dernier devis, statut, urgence)
  → Utiliser le skill `frontend-design` pour le style (thème amber déjà défini)

### 🟠 P1 — Dashboard CRM (liste_id.md)

- [ ] **Endpoint `/api/clients`**
  → GET Dolibarr `/thirdparties?limit=20`
  → Pour chaque client : agréger nb devis + CA depuis `/proposals` et `/invoices`
  → Retourner liste triée par dernière activité

- [ ] **Section CRM dans `dashboard/index.html`**
  → Table par client : nom, nb devis, CA total, dernier devis, statut
  → Clic sur client → filtre les devis

### 🟡 P2 — Freshprocess API

- [ ] **Lancer `python tests/test_freshprocess.py`**
  → Identifier le bon format d'authentification (Bearer, X-API-Key, Basic, etc.)
  → Explorer les endpoints disponibles (`/projects`, `/data`, `/records`)

- [ ] **Mapper les données Freshprocess → Dolibarr**
  → Une fois l'auth découverte : comprendre la structure (tiers, devis, commandes)
  → Implémenter la sync : nouveau tiers FP → créer/trouver dans Dolibarr

### 🟡 P2 — OpenAI datasets complets

- [ ] **Lancer les 3 datasets avec vraie API**
  ```bash
  python tests/run_with_openai.py --compare
  ```
  → Vérifier datasets 02 (complexe) et 03 (interne)

### 🟡 P2 — KPIs Dolibarr : tri chronologique

- [ ] **Vérifier quel `sortfield` est accepté par cette version**
  → Tester `t.date_creation`, `t.tms`, `rowid` sur /thirdparties
  → Une fois validé : réintroduire un tri chronologique pour que les KPIs
     CA mois soient complets (limit=200 sans tri peut manquer des factures récentes)

### 🟡 P2 — Enrichir s06 avec les références matières/finitions InPressco

- [ ] **Charger `user/inpressco-devis/references/finitions.md` et `matieres.md`**
  → Ajouter ces références dans `shared/regles_impression.md` (Layer 3)
  → Le prompt `analyse_besoin_impression` peut mentionner les finitions disponibles
  → Évite que GPT propose des finitions non disponibles chez InPressco

### 🟡 P2 — MCP Server : exposer le pipeline en outil Claude

- [ ] **Évaluer `examples/mcp-builder` skill**
  → Créer un MCP server FastMCP pour exposer le pipeline :
    - `tool: trigger_pipeline()` → POST /api/run
    - `tool: get_pipeline_status()` → GET /api/status
    - `tool: get_kpis()` → GET /api/kpis
  → Permet d'interagir avec le pipeline directement depuis Claude Code
  → Utiliser `examples/mcp-builder/reference/python_mcp_server.md` comme guide

### 🟡 P2 — Skill `notification-interne-inpressco` désactivé

- [ ] **Décider si ce skill doit être réactivé ou supprimé**
  → Actuellement préfixé `_disabled_` dans `.claude/skills/`
  → `gestion-erreurs-inpressco` mentionne les alertes critiques — elles sont ignorées silencieusement
  → Option A : réactiver si un canal de notification est disponible (email, webhook, Slack)
  → Option B : supprimer définitivement et log-only pour les erreurs critiques
  → Référence dans CLAUDE.md mise à jour : "⚠️ notification désactivée — log uniquement"

### ⚪ P3 — Pipeline robustesse

- [ ] **Mode `--dry-run`** : simuler sans créer dans Dolibarr ni archiver Outlook
- [ ] **Cron** : lancer pipeline toutes les 15 min en heures ouvrées (8h-18h lun-ven)
- [ ] **Script `refresh_outlook_token.py`** : renouveler le refresh token manuellement
- [ ] **Alertes** : écrire `pipeline_errors.json` si erreur critique (+ webhook optionnel)

---

## Commandes utiles

```bash
# Tests sans API
python tests/run_dataset.py

# Tests avec OpenAI
python tests/run_with_openai.py 01
python tests/run_with_openai.py --compare

# Diagnostic Dolibarr (safe — GET uniquement)
python tests/test_dolibarr.py
python tests/test_dolibarr.py --full

# Découverte Freshprocess
python tests/test_freshprocess.py

# Pipeline complet
python main.py

# Dashboard
uvicorn dashboard.app:app --reload --port 8080
```

---

*Dernière mise à jour : 28/03/2026*
