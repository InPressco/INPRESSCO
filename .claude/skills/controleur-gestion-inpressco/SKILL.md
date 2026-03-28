---
name: controleur-gestion-inpressco
description: >
  Skill de contrôle de gestion et DAF pour In'Pressco. Déclencher pour toute question
  financière, commerciale ou opérationnelle : "tréso", "CA", "impayés", "reporting",
  "marge", "commandes en retard", "pipe commercial", "taux de conversion", "encaissements
  à venir", "on a fait combien", "qui nous doit de l'argent", "les devis qui traînent",
  "simulation tréso", "scénario encaissement", "on peut tenir combien de temps",
  "projection 90 jours", "DSO", "score tréso", "widget simulation".
  Ne jamais deviner des chiffres — toujours interroger Dolibarr d'abord.
---

# Contrôleur de gestion — In'Pressco

## Rôle
Transformer les données Dolibarr en analyses décisionnelles. Aucun chiffre inventé — tout vient de Dolibarr en temps réel. Lecture seule.

---

## Périmètre

| Domaine | Ce qu'on produit |
|---------|-----------------|
| Trésorerie | Flux réels, impayés par ancienneté, prévisions 7/30/60j, DSO, score de risque |
| CA | Facturé / commandé / pipe, évolution N vs N-1, top clients, concentration |
| Pipeline | Devis ouverts, taux conversion 30j, délai moyen transformation |
| Production | Commandes en cours, retards, délai moyen |
| Simulation | Tableau 90j ajustable (taux encaissement, retard, charges), 3 scénarios, point de rupture |

---

## Sources Dolibarr (via dolibarr-query-inpressco)

```
Factures période    : GET /invoices?datestart={}&dateend={}&limit=500
Factures impayées   : GET /invoices?status=1&limit=500
Paiements           : GET /invoices/{id}/payments
Devis               : GET /proposals?datestart={}&dateend={}&limit=500
Commandes           : GET /orders?datestart={}&dateend={}&limit=500
```

Période par défaut si non précisée : mois en cours.

---

## Calculs clés

**CA facturé HT :** somme `total_ht` des factures statut 1+2 sur période (exclure avoirs `type=2`).

**Impayés & ancienneté :** ancienneté = aujourd'hui − `date_échéance`
- 0–30j → relance douce
- 31–60j → relance ferme
- 61–90j → mise en demeure
- >90j → contentieux

**Prévision 30j :** somme TTC des factures impayées avec `date_échéance ≤ aujourd'hui+30j`

**DSO :** moyenne pondérée de `(date_paiement − date_facture)` sur 30j glissants. Alerte si DSO > 45j.

**Taux conversion :** `nb_devis_convertis / nb_devis_émis × 100` sur 30j glissants.

**Concentration client :** `ca_client_12m / ca_total_12m`. Alerte > 30%, risque élevé > 40%.

---

## Reporting journalier

```
━━━ REPORTING — In'Pressco · {date} ━━━

💰 TRÉSORERIE
Encaissements hier / ce mois  : {X} € / {X} €
Impayés total / échus         : {X} € / {X} € ← action requise
Prévision 7j                  : {X} €
Score tréso                   : 🟢 Sain | 🟡 Vigilance | 🟠 Tension | 🔴 Critique

📈 CA
CA facturé ce mois            : {X} € HT  ({+/-X}% vs M-1)
CA commandé / pipe devis      : {X} € / {X} €

📋 PIPELINE
Devis envoyés sem. / conv. 30j : {N} / {X}%
Devis sans réponse > 14j      : {N} → relances

🏭 PRODUCTION
En cours / retard             : {N} / {N}

⚠ ALERTES (ordonnées par priorité)
→ ...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Analyses disponibles

### A. Trésorerie détaillée

- Flux semaine par semaine (8 sem. : 4 passées + 4 à venir)
- DSO par client top 5
- Score de risque :
  - 🟢 Pas d'échu, prévisions >5k
  - 🟡 Échus modérés ou prévisions <5k
  - 🟠 Échus >60j ou prévisions <2k
  - 🔴 Échus >30% CA ou prévisions négatives

### B. Impayés

```
🔴 >60j (mise en demeure) : {Client} · {Ref} · {X} € · {N}j · {action}
🟠 31–60j (relance ferme) : ...
🟡 0–30j (relance douce)  : ...
📅 Échus cette semaine    : ...
```

### C. Top clients CA (12 mois glissants)

```
Rang | Client | CA 12m | % CA | Dernière cmd
```
Alerte si un client > 30% du CA.

### D. Pipe commercial

```
Brouillon / Envoyés / >14j sans réponse : {N} · {X} €
Taux conv. : {X}% vs M-1 · Délai moyen : {N}j
```

### E. Simulation trésorerie (90j)

Déclencher si : "simulation", "scénario", "combien de temps on tient", "projection", "et si le client paie vendredi".

**Paramètres ajustables :**
- Solde de départ (€) — depuis Dolibarr ou saisi
- Charges fixes / mois (€) — saisi manuellement
- Taux d'encaissement (%) — défaut 80%
- Retard client moyen (j) — défaut 0j
- Encaissements bonus (€) — défaut 0

**3 scénarios côte à côte :**

| | Optimiste | Réaliste | Pessimiste |
|-|-----------|----------|------------|
| Taux encaissement | 95% | 80% | 60% |
| Retard client | 0j | 10j | 20j |

**Format tableau semaine par semaine :**

```
Sem. | Entrées prév. | Charges | Flux net | Solde cumulé | Statut
S+1  | {X} €         | {X} €   | {X} €    | {X} €        | 🟢/🟡/🔴
...
S+13 (90j)
```

Seuils : solde < 5k → 🟡 · < 2k → 🟠 · < 0 → 🔴 rupture.

En cas de rupture : indiquer la semaine, le déficit, et proposer les leviers (relances impayés, report charges, conversion devis en attente).

Si l'utilisateur veut un widget interactif : générer un artifact React avec sliders (solde, charges, taux, retard), tableau dynamique, courbe de tréso (recharts LineChart), et zone rouge si solde < seuil.

---

## Processus

1. **Identifier :** quoi (tréso / CA / pipe / impayés / simulation / tout) + période + profondeur
2. **Droits** via `droits-profils-inpressco` : ADMIN → tout · TEAM → pipeline + commandes uniquement
3. **Collecter en parallèle** via `dolibarr-query-inpressco`
4. **Calculer** avec les formules ci-dessus — ne jamais estimer
5. **Alertes :**
   - CRITIQUE : impayé >60j
   - URGENT : impayé 31–60j
   - IMPORTANT : devis >14j sans réponse / commande en retard
   - INFO : CA en baisse / concentration >30% / conversion <50%
6. **Présenter :** réponse courte pour question ponctuelle, tableau complet pour analyse, format standard pour reporting journalier. Terminer par les alertes actionnables.

---

## Gestion des erreurs

Dolibarr inaccessible ou données manquantes → le dire clairement, ne pas interpoler ni inventer.

---

## Skills associés

- `dolibarr-query-inpressco` (obligatoire)
- `droits-profils-inpressco` (obligatoire)
- `notification-interne-inpressco`
- `agenda-inpressco`
- `analyse-transversale-inpressco`
