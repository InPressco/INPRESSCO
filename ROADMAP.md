# Roadmap sprints — Sprint 1 → 10 — 2026-03-31
*Généré par SAGA1o8 Audit v1 + /roadmap-sprint*

---

## Contexte

Pipeline inpressco-mwp opérationnel (Flux A/B/C) mais porteur de dette structurelle identifiée par audit.
SYSTEME-MWP (successeur) est à S6 — agent-devis-nouveau validé prochainement sur email réel.
Objectif de ce plan : stabiliser inpressco-mwp pour la transition, corriger les bugs fonctionnels, préparer la migration.

---

## Audit SAGA1o8 — Rappel des scores

| Dimension              | Score | Statut |
|------------------------|-------|--------|
| Intégrité structurelle |  2/5  | 🟠 |
| Écologie du code       |  2/5  | 🟠 |
| Résilience évaluative  |  3/5  | 🟡 |
| Robustesse agentique   |  2/5  | 🟠 |

**Score global : 2.3/5** — Fonctionnel en production mais dette structurelle active.
Point d'explosion le plus proche : `src/steps/flux_a/steps.py` (757 lignes, 13 steps mélangés, couplage total).

---

## Contradictions actives (TRIZ)

**CONTRADICTION #1**
Tension    : le pipeline veut être autonome ET rester sous contrôle humain
Coût actuel : s13 (envoi client) existe mais n'est jamais appelée — email client envoyé manuellement
Explosion à : dès qu'un devis arrive à volume, le GO humain devient goulot d'étranglement
Résolution : formaliser le GOchain comme contrat explicite (événement Dolibarr done=0 → GO → s13)

**CONTRADICTION #2**
Tension    : vitesse de développement ET cohérence structurelle
Coût actuel : Flux A = 757 lignes dans 1 fichier, 13 steps mélangés — tout modifier = risquer tout casser
Explosion à : au premier sous-traitant supplémentaire ou nouveau flux métier
Résolution : décomposer en sous-modules avant d'ajouter des fonctionnalités

**CONTRADICTION #3**
Tension    : résilience (fallbacks Outlook) ET intégrité de config (IDs en config.py)
Coût actuel : le fallback par nom compense une config fragile — double logique implicite
Explosion à : si Outlook renomme un dossier, le fallback résout silencieusement en créant un doublon
Résolution : config.py = source de vérité + script de vérification IDs au démarrage

---

## Blocs de travail

| Bloc | Périmètre | Dépendances |
|------|-----------|-------------|
| **Fonctionnel** | Bugs actifs : s13 orpheline, GOchain implicite | — |
| **Architecture** | Découpage Flux A + injection clients | — |
| **Config** | Rate-limit configurable, IDs Outlook vérifiés | — |
| **Robustesse** | Validation API (Pydantic), retry HTTP, cache token | Architecture |
| **Migration** | Transition vers SYSTEME-MWP agent-devis-nouveau | SYSTEME-MWP S7+ |

---

## Plan 10 sprints

| Sprint | Titre | Bloc | Livrable attendu | Priorité |
|--------|-------|------|------------------|----------|
| 1 | GOchain — formaliser le contrôle humain avant envoi client | Fonctionnel | s13 appelable via événement Dolibarr done=0 ; doc GOchain dans CONTEXT.md | 🔴 Critique |
| 2 | Injection clients — supprimer les instanciations dans les steps | Architecture | OutlookClient / DolibarrClient / ClaudeClient injectés via ctx.clients ; 0 instanciation dans les steps | 🔴 Critique |
| 3 | Config rate-limit — externaliser les 13s hardcodés | Config | `CLAUDE_RATE_LIMIT_DELAY_S`, `CLAUDE_CALLS_PER_EMAIL`, `PIPELINE_POLLING_S` dans config.py ; 0 `sleep(13)` dans le code | 🟠 Majeur |
| 4 | Découpage Flux A — éclater steps.py en 7 sous-modules | Architecture | `intake.py`, `routing.py`, `client.py`, `analysis.py`, `devis.py`, `archive.py`, `notify.py` — 757L → 7 × ~100L | 🟠 Majeur |
| 5 | Validation API — Pydantic sur réponses Dolibarr + Outlook | Robustesse | `ProposalResponse`, `ThirdpartyResponse`, `MessageResponse` — 0 dict non validé sur chemin critique | 🟠 Majeur |
| 6 | Tests chemins critiques — s02, s04, s08 avec mocking | Robustesse | Mocking ClaudeClient + DolibarrClient ; couverture s02/s04/s08 ≥ 80% ; CI passe en local | 🟡 Mineur |
| 7 | Cache token MSAL + retry HTTP Outlook | Robustesse | Token mis en cache (TTL 55min) ; retry 3× sur 429/503 Outlook ; temps s01 < 500ms | 🟡 Mineur |
| 8 | Vérification IDs Outlook au démarrage | Config | Script `tools/verify_outlook_ids.py` ; alerte si ID config.py périmé ; 0 fallback silencieux | 🟡 Mineur |
| 9 | Migration Flux A → agent-devis-nouveau SYSTEME-MWP | Migration | Flux A désactivé pour NEW_PROJECT ; routage vers SYSTEME-MWP via SDK ; Flux B/C restent actifs | 🔵 Secondaire |
| 10 | Dépréciation inpressco-mwp Flux A/B | Migration | Flux B migré ; seul Flux C (fournisseurs) reste dans inpressco-mwp jusqu'à SYSTEME-MWP S10+ | — |

---

## Angles morts adressés par ce plan

- s13 jamais appelée → Sprint 1
- Délais 13s hardcodés → Sprint 3
- Flux A monolithe 757 lignes → Sprint 4
- Couplage clients dans steps (non testable) → Sprint 2
- Pas de validation API → Sprint 5
- Cache token absent → Sprint 7
- Fallback Outlook silencieux → Sprint 8

---

## Angles morts hors scope (intentionnels)

| Angle mort | Raison |
|------------|--------|
| Refactoring Flux B/C complet | SYSTEME-MWP les absorbera — effort non rentable |
| Queue distribuée (Redis, RabbitMQ) | Volume actuel < 20 emails/jour — over-engineering |
| Schéma Pydantic Dolibarr complet | API Dolibarr change peu — scope limité aux chemins critiques |
| Monitoring Prometheus | Dashboard FastAPI existant suffit pour le volume actuel |

---

## Hypothèses

- SYSTEME-MWP reste en développement actif — migration possible dès Sprint 9
- Le volume email reste < 30/jour pendant la durée du plan
- L'API Dolibarr ne change pas de version majeure
- Claude rate limits stables (5 req/min Opus)
- Outlook Graph API token TTL = 60min (standard Azure AD)

---

*SAGA1o8 Audit v1 — inpressco-mwp — 2026-03-31*
