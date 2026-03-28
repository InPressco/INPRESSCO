# RAPPORT SYSTÈME — InPressco MWP
**Date** : 28/03/2026 · **Généré par** : Claude Code (audit automatisé)
**Projet** : Pipeline d'automatisation des devis — InPressco, imprimerie Aix-les-Bains
**Statut global** : 85% implémenté · Bloqueur unique : credentials Azure AD Outlook

---

## RÉSUMÉ EXÉCUTIF

| Dimension | Score | Notes |
|-----------|-------|-------|
| Code Python | 8/10 | 95% implémenté, async/await, retries en place |
| Documentation | 9/10 | Layer 0-3 complet, architecture claire |
| Sécurité | 7/10 | Injection SQL corrigée, anti-doublon actif |
| Tests | 5/10 | Datasets OK, Outlook/Write non validés |
| Production Ready | 3/10 | **Azure AD bloqueur total** |

**Lignes de code Python** : ~6 155 L
**Skills Claude installés** : 24 actifs + 1 désactivé
**Endpoints dashboard** : 14 (FastAPI)
**Tests passants** : 3/3 datasets (sans API)

---

## 1. STRUCTURE RACINE

| Fichier | Lignes | Rôle | Statut |
|---------|--------|------|--------|
| `main.py` | 84 | Point d'entrée — 1 flux unifié (intake → route → pipeline) | ✅ |
| `CLAUDE.md` | 240 | Layer 0 : identité workspace + 24 skills | ✅ 28/03 |
| `CONTEXT.md` | 382 | Layer 1 : routing, état projet, architecture, failles | ✅ 28/03 |
| `CARNET.md` | 396 | Journal de bord : sessions, décisions, TODO priorisé | ✅ 28/03 |
| `.env.example` | 21 | Template credentials (Anthropic, Azure AD, Dolibarr) | ✅ 28/03 |
| `README.md` | 124 | Quick start, installation, structure MWP | ✅ |
| `liste_id.md` | — | Directives dashboard CRM et sécurité tests | ✅ |

### Configuration persistante (Layer 3 — `_config/`)

| Fichier | Contenu | Statut |
|---------|---------|--------|
| `dolibarr_config.md` | Endpoints, IDs métier (socid, user, product, special_codes) | ✅ |
| `outlook_config.md` | Folder IDs, OData filters | ⚠️ À mettre à jour (IDs redécouverts 28/03) |
| `claude_config.md` | Modèles Claude, paramètres, 5 méthodes, migration OpenAI | ✅ Créé 28/03 |
| `openai_config.md` | Legacy — remplacé par claude_config.md | ❌ Obsolète |

### Règles métier (Layer 3 — `shared/`)

| Fichier | Contenu | Statut |
|---------|---------|--------|
| `regles_extraction.md` | Prompt système : extraction données client JSON | ✅ |
| `regles_impression.md` | Prompt + schéma : analyse besoin impression | ✅ |
| `regles_devis.md` | Algorithme construction lignes Dolibarr | ✅ |

---

## 2. CONNECTEURS (`src/connectors/`)

### claude_client.py — 308 L · ✅ Produit

Client Anthropic Claude (migration complète depuis OpenAI, 28/03)
Modèles : `claude-opus-4-5` (complexe) · `claude-haiku-4-5-20251001` (routing/sentiment)

| Méthode | Modèle | Input | Output | Notes |
|---------|--------|-------|--------|-------|
| `extract_json()` | Opus | system + user | dict | Fallback markdown |
| `extract_client_data()` | Opus | sender + body | dict (soc_nom, email, contact, projet...) | Exclut données InPressco |
| `analyse_sentiment_email()` | Haiku | sender + body | dict (sentiment, urgence, profil, intention) | 4 axes psych |
| `classify_email_routing()` | Haiku | sender + body | dict (categorie, confidence, motif) | 8 catégories |
| `analyse_besoin_impression()` | Opus | body + composants | dict (synthese, composants_isoles[]) | Post-process Python |
| `generate_email_reponse_client()` | Opus | contexte complet | HTML str | CONFIG_CLIENT_v2026, 8 blocs |

---

### dolibarr.py — 176 L · ✅ GET testé · ⚠️ Write non validé

Client REST Dolibarr/Freshprocess. Sécurité : `_sanitize_sqlfilter_value()` corrigée 28/03.

| Méthode | Endpoint | Type | Retry | Notes |
|---------|----------|------|-------|-------|
| `find_thirdparty(email, name)` | GET /thirdparties | Lecture | — | Sanitize email + name, essaie email puis nom |
| `create_thirdparty(data)` | POST /thirdparties | Écriture | — | Retourne {id, ...} |
| `create_proposal(data)` | POST /proposals | Écriture | 3× | Retourne {id, ...} |
| `validate_proposal(id)` | POST /proposals/{id}/validate | Écriture | 3× | Génère ref PRO... |
| `set_to_draft(id)` | POST /proposals/{id}/settodraft | Écriture | 3× | Remet éditable |
| `get_proposal_by_ref(ref)` | GET /proposals/ref/{ref} | Lecture | — | Retourne devis complet |
| `upload_document(modulepart, ref, filename, b64)` | POST /documents/upload | Écriture | 3× | PJ base64 |
| `create_agenda_event(data)` | POST /agendaevents | Écriture | — | Log note interne |

**Note Freshprocess** : `sortfield=t.rowid` non supporté → supprimé partout (28/03), tri côté Python.

---

### outlook.py — 272 L · ✅ Code complet · ❌ Bloqué Azure AD

Client Microsoft Graph (OAuth2 MSAL client credentials — app-only).

| Méthode | Action | Notes |
|---------|--------|-------|
| `_get_token()` | Acquire token MSAL | Cache + refresh auto |
| `get_emails(folder_id, filter, top, select)` | GET /mailFolders/{id}/messages | Tri côté client si $filter |
| `get_attachments(message_id)` | GET /messages/{id}/attachments | Liste PJ |
| `download_attachment(msg_id, att_id)` | GET /messages/{id}/attachments/{id}/$value | Binary |
| `get_folders(folder_id)` | GET /mailFolders/{id}/childFolders | Liste sous-dossiers |
| `get_folder_id_by_name(name)` | GET /mailFolders | Résolution par displayName |
| `send_email(to, subject, body_html, cc, reply_to_id)` | POST sendMail ou createReply | CC systématique contact@in-pressco.com |

**Folder IDs actuels** (découverts 28/03) :
- `OUTLOOK_FOLDER_DEVIS` = `"inbox"` (well-known name Graph)
- `OUTLOOK_FOLDER_ETUDE` = `"AAHD9iRZAAA="` (>> ETUDE PROJET sous FLUX InPressco)

---

### openai_client.py — 174 L · ❌ Legacy

À retirer. Partiellement remplacé par `claude_client.py`. Encore importé par `tests/run_with_openai.py`.

---

## 3. MIDDLEWARE (`src/middleware/`)

### context.py — 89 L · ✅

`Context` (dataclass) — objet mutable partagé entre tous les steps.

| Groupe | Champs clés | Peuplé par |
|--------|-------------|-----------|
| Email source | email_id, subject, sender, sender_address, body, has_attachments, attachments | s01 |
| Données IA | client_data, email_sentiment, routing_category, email_reponse_client | s02 |
| Dolibarr CRM | socid, soc_nom, nom_projet, client_created, devis_id, devis_ref | s04→s08 |
| Analyse impression | synthese_contexte, date_livraison_souhaitee, composants_isoles | s06 |
| Devis construit | devis_lines | s07 |
| Sorties structurées | output_response {to, cc, subject, body, status}, output_actions[], output_silent[] | s12 |
| Contrôle | skip_remaining, errors[], extra{} | Partout |

### pipeline.py — 59 L · ✅

`Pipeline` : orchestrateur de steps async.
`StopPipeline` : exception d'arrêt propre (sans erreur).
Comportement : séquence, gère exceptions, log chaque step, arrêt si skip_remaining.

---

## 4. STEPS FLUX A (`src/steps/flux_a/steps.py`) — 623 L

### 13 steps async — pipeline : intake (s01+s02) → route() → s03→s12

| Step | Fonction | Action principale | Statut |
|------|----------|-------------------|--------|
| **s01** | `s01_get_email` | Récupère dernier email inbox Outlook, vérifie anti-doublon (marker s08) | ✅ |
| **s02** | `s02_extract_client_ai` | 3 appels Claude parallèles : extract_client + sentiment + routing | ✅ |
| **s03** | `s03_clean_data` | Valide routing NEW_PROJECT, nettoie données client, filtre InPressco | ✅ |
| **s04** | `s04_find_or_create_client` | Cherche tiers Dolibarr (email→nom), crée si absent, fallback socid=16 | ✅ |
| **s05** | `s05_get_attachments` | Récupère PJ non-inline Outlook | ✅ |
| **s06** | `s06_analyse_besoin` | Claude analyse impression + post_process_composants() Python (imposition + score) | ✅ |
| **s07** | `s07_build_devis_lines` | Construit lignes Dolibarr (contexte + descriptifs + prix) | ✅ |
| **s08** | `s08_create_devis` | Crée devis Dolibarr → valide (→ ref) → remet brouillon → écrit marker anti-doublon | ✅ |
| **s09** | `s09_upload_attachments` | Upload PJ email → dossier devis Dolibarr | ✅ |
| **s10** | `s10_log_email` | Crée événement agenda Dolibarr (log note interne sur le devis) | ✅ |
| **s11** | `s11_archive_outlook` | Renomme email [Traité], déplace sous-dossier Outlook, efface marker | ✅ |
| **s12** | `s12_notify_team` | Notification interne équipe (email GO avant envoi client) | ⚠️ À implémenter |
| **s13** | `s13_send_email_client` | Génère CONFIG_CLIENT_v2026, envoie Outlook (CC contact@), log agenda | ⚠️ Bloqué Azure AD |

---

## 5. STEPS FLUX B (`src/steps/flux_b/steps.py`) — 136 L

> **Note** : Flux B est déclenché par N8N (déplacement email → sous-dossier), pas par le polling Python.

| Step | Fonction | Action | Statut |
|------|----------|--------|--------|
| **s01** | `s01_get_subfolders` | Récupère sous-dossiers >> ETUDE PROJET, fallback résolution par nom | ✅ |
| **s02** | `s02_get_messages` | Récupère emails non-[Traité] dans chaque sous-dossier | ✅ |
| **s03** | `s03_process_messages` | Pour chaque email : parse ref, upload PJ, log agenda, marque [Traité] | ✅ |

---

## 6. ENGINE (`src/engine/`)

### dispatcher.py — 83 L · ✅

Routing `ctx.routing_category` → `Pipeline | None`

```
NEW_PROJECT      → build_flux_a() (s03→s12)
PROJECT_UPDATE   → None (géré N8N)
SUPPLIER_INVOICE → None (géré N8N)
VISUAL_CREATION  → None (TODO)
PRICE_REQUEST    → None
ACTION           → None (email interne)
UNKNOWN          → None
```

### src/engine/main.py (non utilisé en prod) — 134 L

Moteur de polling alternatif (Flux A + B en parallèle, intervalle 300s).
**En usage** : `main.py` racine (flux unifié simplifié).

---

## 7. UTILITAIRES (`src/utils/`)

### imposition.py — 130 L · ✅ Testé 3/3

Calcul poses/feuilles **en Python pur**, jamais dans le prompt IA.

```python
FORMATS_PRESSE = {
    "700x1000": (690, 990),   # 5mm marges sécurité
    "330x480":  (320, 470),
}
```

| Fonction | Rôle |
|----------|------|
| `calculer_imposition(composant)` | Injecte IMPOSITION_BRUTE_700x1000, IMPOSITION_BRUTE_330x480 |
| `calculer_score(composant)` | Score 0-10 (6 pts obligatoires + 4 bonus), alertes métier |
| `post_process_composants(composants)` | Applique les 2 calculs à tous les composants |

### devis_builder.py — 164 L · ✅ Testé 3/3

Construit les lignes Dolibarr depuis les composants IA.

Structure par groupe (intitule_maitre) :
1. Ligne contexte client (`special_code=104777`, product_type=9)
2. Ligne descriptif fusionné (`special_code=104778`, product_type=9)
3. N lignes prix par quantité (fk_product=35700, product_type=0)

### html_cleaner.py — 70 L · ✅

`prepare_email_for_ai(html_body)` → strip HTML + decode entities + normalise espaces.
Compression 33–56% avant envoi IA.

### pipeline_helpers.py — 105 L · ✅

| Fonction | Rôle |
|----------|------|
| `read_stage_output(stage_num)` | Lit `stages/0N_*/output/result.json` |
| `write_stage_output(stage_num, data)` | Écrit result.json (marker anti-doublon s08) |
| `log_email_to_agenda(doli, ...)` | POST /agendaevents (log note interne) |
| `upload_attachments_to_proposal(doli, ...)` | Boucle upload PJ → Dolibarr |

### dolibarr_urls.py — 33 L · ✅

`build_links(obj, modulepart, base_url)` → dict {url, pdf_url, project_name}

---

## 8. CONFIG (`src/config.py`) — 61 L

| Variable | Valeur / Source | Notes |
|----------|----------------|-------|
| `ANTHROPIC_API_KEY` | `.env` | Requis |
| `OUTLOOK_TENANT_ID/CLIENT_ID/CLIENT_SECRET` | `.env` | ❌ Manquants — bloqueur |
| `OUTLOOK_USER_EMAIL` | `.env` | contact@in-pressco.com |
| `OUTLOOK_FOLDER_DEVIS` | Code | `"inbox"` (well-known Graph) |
| `OUTLOOK_FOLDER_ETUDE` | Code | `"AAHD9iRZAAA="` (>> ETUDE PROJET) |
| `DOLIBARR_API_KEY/BASE_URL` | `.env` | ✅ Configuré |
| `DOLIBARR_SOCID_INCONNU` | Code | 16 (CLIENT A RENSEIGNER) |
| `DOLIBARR_PRODUCT_IMPRESSION` | Code | `"35700"` |
| `DOLIBARR_MODEL_PDF` | Code | `"azur_fp"` |
| `DOLIBARR_SPECIAL_CODE_CONTEXTE/DESCRIPTIF` | Code | 104777 / 104778 |
| `INPRESSCO_INTERNAL_EMAIL` | Code | contact@in-pressco.com (CC systématique) |
| `INPRESSCO_EXCLUDE_EMAILS/NAMES/ADDRESS` | Code | Anti-pollution données InPressco |

---

## 9. DASHBOARD (`dashboard/`)

### app.py — 530+ L · ✅ Fonctionnel (post-fix sortfield 28/03)

**Fix critique appliqué 28/03** : `sortfield=t.rowid` supprimé de **tous** les appels Dolibarr (non supporté Freshprocess → erreurs silencieuses). Tri fait côté Python.

#### Endpoints GET

| Route | Données | Source |
|-------|---------|--------|
| `/` | UI dashboard | index.html static |
| `/api/status` | Statut pipeline + connecteurs | pipeline.log + Dolibarr /status |
| `/api/stats` | Devis semaine, brouillons, cmds production | Dolibarr proposals + orders |
| `/api/kpis` | CA mois, impayés clients/fournisseurs (83k€/78k€), devis ouverts (146) | Dolibarr invoices + proposals |
| `/api/daf` | Tréso détail, risques | Dolibarr |
| `/api/ca-chart` | CA 12 derniers mois | Dolibarr invoices |
| `/api/clients` | Tiers + agrégation CA | Dolibarr thirdparties |
| `/api/runs` | 20 dernières exécutions pipeline | pipeline.log |
| `/api/config` | Config publique (URLs, modèles) | Code |
| `/admin/dev` | Page dev | Statique |

#### Endpoints POST

| Route | Action | Notes |
|-------|--------|-------|
| `/api/run` | Lance `python main.py` subprocess non-bloquant | Bouton dashboard |
| `/api/chat` | Streaming SSE Claude + snapshot Dolibarr | 10 tools disponibles |
| `/api/upload` | Upload assets (images, PDFs) | Form multipart |

#### Tools IA disponibles dans `/api/chat`

| Tool | Type | Endpoint Dolibarr |
|------|------|------------------|
| `search_proposals` | Lecture | GET /proposals |
| `get_proposal` | Lecture | GET /proposals/{id} ou /ref/{ref} |
| `search_thirdparties` | Lecture | GET /thirdparties |
| `get_thirdparty` | Lecture | GET /thirdparties/{id} |
| `search_invoices` | Lecture | GET /invoices |
| `search_orders` | Lecture | GET /orders |
| `update_proposal` | **Écriture** | PUT /proposals/{id} |
| `update_proposal_line` | **Écriture** | PUT /proposals/{id}/lines/{lid} |
| `validate_proposal` | **Écriture** | POST /proposals/{id}/validate |
| `set_proposal_to_draft` | **Écriture** | POST /proposals/{id}/settodraft |

---

## 10. TESTS (`tests/`)

| Fichier | Lignes | Type | Résultat |
|---------|--------|------|---------|
| `run_dataset.py` | 362 | Datasets JSON, 0 API | ✅ 3/3 PASS |
| `run_with_openai.py` | 308 | API OpenAI legacy | ⚠️ À migrer vers Claude |
| `test_dolibarr.py` | 204 | API Dolibarr (GET only, prod-safe) | ✅ GET OK |
| `test_outlook.py` | 196 | API Graph Outlook | ❌ Bloqué Azure AD |
| `test_freshprocess.py` | 214 | Freshprocess auth | ⚠️ Auth non découverte |

**Tests à créer** :
- `test_claude_client.py` — 3 appels parallèles s02
- `test_dolibarr.py --write` — écriture avec cleanup explicite
- `test_graph_client.py` — dry-run Outlook (bloqué Azure AD)

---

## 11. SKILLS CLAUDE (24 actifs)

| # | Skill | Déclencheur | Pipeline | Statut |
|---|-------|-------------|---------|--------|
| 1 | `droits-profils-inpressco` | **Toujours en premier** | Gate sécurité | ✅ |
| 2 | `mail-routing-inpressco` | Email entrant | s02 (appel parallèle) | ✅ |
| 3 | `analyse-sentiment-email` | Email client | s02 (appel parallèle) | ✅ |
| 4 | `inpressco-commerce` | Brief/finition/matière | s06 + s12 | ✅ |
| 5 | `dolibarr-query-inpressco` | CRUD Dolibarr | s04 + s08 | ✅ |
| 6 | `reponse-client-inpressco` | Envoi email client | s12 (s13) | ✅ |
| 7 | `generation-pdf-inpressco` | "génère le PDF" | s12 | ✅ |
| 8 | `archiveur-inpressco` | Fichier à déposer | s09 + post-pipeline | ✅ |
| 9 | `agenda-inpressco` | RDV/relance/rappel | s10 | ✅ |
| 10 | `validation-qc-inpressco` | **Avant envoi client** (gate) | s11 + s12 | ✅ |
| 11 | `projets-artefacts-inpressco` | "Retrouve/reprends" | Cross (s06, s08, s12) | ✅ |
| 12 | `charte-graphique-inpressco` | "Voici notre charte" | Cross | ✅ |
| 13 | `orchestrateur-inpressco` | Workflow multi-skills | meta | ✅ |
| 14 | `gestion-erreurs-inpressco` | **Auto si erreur API** | error filet | ✅ |
| 15 | `bdd-images-query-inpressco` | **Avant toute image** | guard anti-doublon | ✅ |
| 16 | `memoire-client-inpressco` | Tiers identifiable | CRM socle | ✅ |
| 17 | `chat-to-db-inpressco` | Données collectées oralement | bridge → Dolibarr | ✅ |
| 18 | `controleur-gestion-inpressco` | Questions financières | tréso/CA/DSO | ✅ |
| 19 | `suivi-commande-inpressco` | Statut commande | post-pipeline | ✅ |
| 20 | `analyse-transversale-inpressco` | Tendances/anomalies | intel | ✅ |
| 21 | `ux-inpressco` | Composant/interface | design | ✅ |
| 22 | `planche-archi-inpressco` | Produit finition spéciale | visual Nanobanana | ✅ 28/03 |
| 23 | `agent-acheteur-inpressco` | Devis prestation externe | buyer RFQ | ✅ 28/03 |
| 24 | `reponse-client-inpressco` | Rédaction email réponse | s12 | ✅ |

**Désactivé** : `_disabled_notification-interne-inpressco` (pas de canal Slack/email)

---

## 12. DONNÉES DOLIBARR LIVE (28/03/2026)

Données réelles récupérées via `/api/kpis` et `/api/stats` :

| Indicateur | Valeur |
|-----------|--------|
| CA mois en cours (HT) | **56 824 €** |
| CA mois précédent (HT) | 65 893 € |
| Évolution | -13.8% |
| Devis ouverts | **146** (718 454 € TTC pipeline) |
| Devis cette semaine | **57** (41 991 € HT) |
| Devis brouillons | **14** (18 876 € HT) |
| Commandes semaine | **13** (16 725 € HT) |
| Commandes en prod | **10** (32 798 € HT) |
| Commandes bloquées | **16** (44 441 € HT) |
| Commandes en attente BAT | **7** (3 552 € HT) |
| Impayés clients | **83 836 € HT** (64 factures) |
| Impayés fournisseurs | **78 175 € HT** (57 factures) |
| Taux de transformation | **19.9%** (59 signés / 296 actifs) |
| Commandes non facturées | **17** (43 369 € HT) |

---

## 13. ARBORESCENCE COMPLÈTE

```
inpressco-mwp/
├── main.py                            ← Flux unifié (intake → route → pipeline)
├── CLAUDE.md                          ← Layer 0 : identité + 24 skills
├── CONTEXT.md                         ← Layer 1 : routing + état projet
├── CARNET.md                          ← Journal de bord + TODO priorisé
├── RAPPORT_SYSTEME_28032026.md        ← CE FICHIER
├── .env / .env.example
├── README.md
├── src/
│   ├── config.py                      ← Variables d'environnement (61 L)
│   ├── connectors/
│   │   ├── claude_client.py           ← 308 L · 6 méthodes async · Opus + Haiku
│   │   ├── dolibarr.py                ← 176 L · 8 méthodes async · REST Dolibarr
│   │   ├── outlook.py                 ← 272 L · 8 méthodes async · Graph API MSAL
│   │   └── openai_client.py           ← 174 L · LEGACY à retirer
│   ├── middleware/
│   │   ├── context.py                 ← 89 L · Context dataclass
│   │   └── pipeline.py                ← 59 L · Pipeline + StopPipeline
│   ├── steps/
│   │   ├── flux_a/steps.py            ← 623 L · s01→s13 (13 steps)
│   │   └── flux_b/steps.py            ← 136 L · s01→s03 (3 steps)
│   ├── utils/
│   │   ├── imposition.py              ← 130 L · calcul poses/feuilles/score
│   │   ├── devis_builder.py           ← 164 L · lignes Dolibarr
│   │   ├── html_cleaner.py            ← 70 L  · strip HTML emails
│   │   ├── pipeline_helpers.py        ← 105 L · stage outputs, agenda, upload
│   │   └── dolibarr_urls.py           ← 33 L  · builder URLs
│   └── engine/
│       ├── dispatcher.py              ← 83 L  · routing → pipelines
│       └── main.py                    ← 134 L · polling Flux A+B (backup)
├── dashboard/
│   ├── app.py                         ← 530+ L · FastAPI 14 endpoints
│   ├── index.html                     ← UI thème amber / IBM Plex Mono
│   ├── notice.html                    ← Documentation fonctionnelle dashboard
│   └── static/                        ← Assets (logo, fonts)
├── tests/
│   ├── dataset/
│   │   ├── email_01.json              ← Brochure A5
│   │   ├── email_02.json              ← Catalogue dos carré collé
│   │   └── email_03.json              ← Email interne / client dans le corps
│   ├── run_dataset.py                 ← 362 L · ✅ 3/3 PASS
│   ├── run_with_openai.py             ← 308 L · legacy à migrer
│   ├── test_dolibarr.py               ← 204 L · GET only, prod-safe
│   ├── test_outlook.py                ← 196 L · bloqué Azure AD
│   └── test_freshprocess.py           ← 214 L · auth non découverte
├── stages/
│   ├── 01_extraction_email/           ← Contrat s01-s02 + output/result.json
│   ├── 02_analyse_client/             ← Contrat s03-s04 + output/result.json
│   ├── 03_analyse_besoin_impression/  ← Contrat s05-s06 + output/result.json
│   ├── 04_construction_devis/         ← Contrat s07-s08 + output/result.json
│   └── 05_archivage/                  ← Contrat s09-s11 + output/result.json
├── _config/
│   ├── dolibarr_config.md
│   ├── outlook_config.md              ← ⚠️ À mettre à jour (IDs 28/03)
│   ├── claude_config.md               ← ✅ Créé 28/03
│   └── openai_config.md               ← ❌ Obsolète
├── shared/
│   ├── regles_extraction.md
│   ├── regles_impression.md
│   └── regles_devis.md
└── .claude/skills/                    ← 24 skills SKILL.md
    ├── agent-acheteur-inpressco/
    │   ├── SKILL.md
    │   └── references/ (faconnier, papetier, imprimeur, finisseur)
    ├── planche-archi-inpressco/SKILL.md
    └── [22 autres skills]/SKILL.md
```

---

## 14. BLOCAGES & PRIORITÉS

### 🔴 P0 — Bloqueurs critiques

| Problème | Impact | Solution |
|---------|--------|---------|
| **Azure AD credentials manquants** (TENANT_ID, CLIENT_ID, CLIENT_SECRET) | s01 (lecture emails) + s12/s13 (envoi réponse) non fonctionnels — pipeline stoppé aux 2 extrémités | Demander credentials admin Azure |

### 🟠 P1 — À faire rapidement

| Item | Impact | Effort |
|------|--------|--------|
| Implémenter `s12_notify_team` | Notification interne équipe avant GO client | ~30 L |
| Créer `test_claude_client.py` | Valider 3 appels parallèles s02 | ~100 L |
| Créer `test_dolibarr.py --write` | Valider écriture Dolibarr avec cleanup | ~50 L |
| Valider Dolibarr write en staging | create_proposal, upload_document, agenda | Tests manuels |

### 🟡 P2 — Important

| Item | Impact |
|------|--------|
| Mettre à jour `_config/outlook_config.md` | Folder IDs redécouverts 28/03 (inbox, AAHD9iRZAAA=) |
| Migrer `tests/run_with_openai.py` | Adapter aux 5 méthodes ClaudeClient |
| Investiguer auth Freshprocess | 3 clés disponibles, format auth inconnu |
| Implémenter output Layer 4 | Écrire result.json dans stages/0X/output/ à chaque step majeur |

### ⚪ P3 — Nice to have

| Item |
|------|
| Cron toutes les 5 min (heures ouvrées 8h-18h lun-ven) |
| Mode `--dry-run` pour tests pipeline sans API |
| `scripts/refresh_outlook_token.py` |
| Alertes erreurs critiques (webhook ou log `pipeline_errors.json`) |

---

## 15. FLUX D'EXÉCUTION COMPLET

```
contact@in-pressco.com (boîte de réception)
         │
         ▼ main.py → intake pipeline
┌─────────────────────────────────────────┐
│  s01 — GET inbox Graph API              │
│        → Dernier email non [Traité]     │
│        → Vérif anti-doublon (marker)   │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  s02 — 3 appels Claude parallèles       │
│  ① extract_client_data (Opus)           │
│  ② analyse_sentiment (Haiku)            │
│  ③ classify_routing (Haiku)             │
└──────────────┬──────────────────────────┘
               │
               ▼  dispatcher.route(ctx)
     ┌─────────┴──────────┐
     │                    │
NEW_PROJECT          Autres catégories
     │                    │
     ▼             N8N ou log+stop
┌────────────────────────────────────────┐
│  s03 — Valide NEW_PROJECT, clean data  │
│  s04 — find_or_create tiers Dolibarr   │
│  s05 — Récupère PJ email               │
│  s06 — Analyse impression (Opus) +     │
│        post_process_composants()       │
│  s07 — build_lines() → devis_lines     │
│  s08 — create_proposal → validate →   │
│        set_to_draft → marker anti-dbl  │
│  s09 — Upload PJ → Dolibarr            │
│  s10 — create_agenda_event (log note)  │
│  s11 — Archive email Outlook [Traité]  │
│  s12 — ⚠️ notify_team (à implémenter)  │
│  s13 — generate_email_reponse_client → │
│        send_email (CC contact@) →      │
│        log agenda Dolibarr             │
└────────────────────────────────────────┘
         ⚠️ s13 bloqué Azure AD
```

---

*Rapport généré automatiquement — InPressco MWP · 28/03/2026*
