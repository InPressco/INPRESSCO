---
name: analyse-transversale-inpressco
description: >
  Skill d'analyse transversale des données Dolibarr pour In'Pressco — imprimeur-façonnier. Déclencher SYSTÉMATIQUEMENT dès qu'une question porte sur des tendances, performances, comportements clients ou anomalies Dolibarr, même formulée vaguement. Déclencheurs : "quels sont nos clients les plus actifs", "détecte les anomalies", "tendance de nos devis ce trimestre", "analyse notre mix produit", "qui n'a pas commandé depuis 6 mois", "délai moyen de transformation", "taux de conversion", "notre pipeline", "bilan commercial", "qui relancer en priorité", "où sont nos pertes". Ce skill CROISE les données (plusieurs types d'objets Dolibarr) pour produire des insights actionnables — différent de dolibarr-query (lecture d'un objet précis) et de controleur-gestion (analyse financière pure). Spécifique imprimerie : délais BAT, mix format/finition, saisonnalité campagnes marketing.
---

# Analyse Transversale Dolibarr — In'Pressco

## Rôle
Analyser l'ensemble des données Dolibarr de façon transversale pour détecter des tendances, motifs, anomalies et opportunités. Ce skill croise les types d'objets (devis + commandes + factures + agendas) pour produire des insights commerciaux et opérationnels actionnables — formulés en recommandations, pas en data brute.

**Différence clé avec les autres skills :**
- `dolibarr-query-inpressco` → lit un objet précis (une commande, un devis)
- `controleur-gestion-inpressco` → analyse les flux financiers (tréso, CA, facturation)
- **Ce skill → croise les données pour détecter schémas, tendances et anomalies**

---

## Types d'analyses disponibles

### 1. Analyse commerciale
- **Mix produit In'Pressco** : formats (A4, A5, carré, DL…), finitions (pelliculage, vernis, dorure, découpe) répartis sur les devis/commandes
- **Saisonnalité** : périodes de fort/faible activité — rentrée (août-sept), Noël (oct-nov), printemps (mars-avril pour catalogues)
- **Taux de conversion** devis → commande : par période, par type de produit, par client
- **Délai de transformation** : temps moyen entre création du devis et signature de la commande
- **Panier moyen** : évolution du montant moyen, par segment client, par type de produit

### 2. Analyse client
- **Segmentation RFM** : clients Champions / Fidèles / Prometteurs / À risque / Perdus (voir algorithme ci-dessous)
- **Clients à risque** : inactivité > seuil, décrochage du volume, impayés chroniques
- **Clients à potentiel de montée en gamme** : produits In'Pressco non encore commandés (ex : client flyers mais pas catalogues)
- **Concentration** : part du CA portée par les top 5 clients — risque de dépendance
- **Prospects froids** : devis envoyés > 60j sans réponse, jamais transformés en commande

### 3. Analyse des devis
- **Devis orphelins** : ouverts depuis > 30j sans statut (ni signé, ni refusé, ni relancé)
- **Taux de refus / perte** : devis classés "perdus", délai avant perte, motifs détectables
- **Volumes en attente** : montant total HT des devis non signés (pipe potentiel)
- **Benchmark formats** : formats et finitions les plus demandés sur la période

### 4. Analyse opérationnelle — Spécifique imprimerie
- **Délais BAT** : temps entre envoi du BAT et validation client — identifier les clients lents qui bloquent la prod
- **Délais de production** : temps entre commande validée et livraison, par type de produit et finition
- **Retards** : commandes hors délai, clients concernés fréquemment
- **Anomalies** : commandes à 0€, factures sans commande liée, devis dupliqués, factures en double

### 5. Analyse des fournisseurs
- **Volume par fournisseur** : répartition des factures (papier, façonnage, sous-traitance)
- **Délais de paiement** : respect des échéances fournisseurs
- **Concentration** : dépendance à un fournisseur unique (risque chaîne d'approvisionnement)

---

## Collecte de données (requêtes larges via dolibarr-query)

```
Devis sur N mois
→ GET /proposals?datestart={epoch}&limit=500&sortfield=date_creation&sortorder=DESC

Commandes sur N mois
→ GET /orders?datestart={epoch}&limit=500&sortfield=date_commande&sortorder=DESC

Factures sur N mois
→ GET /invoices?datestart={epoch}&limit=500

Tous les tiers actifs
→ GET /thirdparties?status=1&limit=500

Événements agenda (BAT, RDV, relances) sur N mois
→ GET /agendaevents?datestart={epoch}&limit=1000
```

Pour > 500 objets : paginer avec `page=0`, `page=1`… jusqu'à résultat vide.

---

## Algorithmes d'analyse

### Segmentation clients RFM (Récence / Fréquence / Montant)
Pour chaque tiers client avec au moins 1 devis ou commande :

```
R = jours depuis la dernière commande confirmée
F = nombre de commandes sur 12 mois
M = montant total HT commandes sur 12 mois

Segments In'Pressco :
CHAMPION      : R < 60j  · F ≥ 3  · M élevé      → chouchouter, upsell possible
FIDÈLE        : R < 120j · F ≥ 2                  → base solide, fidéliser
PROMETTEUR    : R < 90j  · F = 1  (nouveau actif)  → potentiel, accompagner
À_RISQUE      : R 120-365j · F ≥ 2 (était actif)  → réactiver en priorité
PERDU         : R > 365j ou 0 commande depuis 1 an → campagne reconquête
PROSPECT_FROID: devis envoyé > 90j, jamais signé   → décision go/no-go
```

### Détection d'anomalies
Anomalies prioritaires à détecter :
1. Devis avec `total_ht = 0` ou null → devis test ou erreur saisie
2. Commande sans devis lié → vente directe non tracée dans le pipe
3. Facture sans commande liée → émission directe, à vérifier
4. Tiers dupliqués → même email ou nom similaire
5. Commandes livrées sans facture émise → oubli facturation
6. Devis en statut "validé" depuis > 60j sans réponse → pipe bloqué
7. Factures avec `date_lim_reglement` dépassée et statut ≠ payée → impayés
8. Montants > 2 écarts-types de la moyenne du type de produit → anomalie prix
9. BAT envoyé depuis > 10j sans validation → blocage potentiel de prod

### Analyse saisonnalité In'Pressco
Pour chaque mois sur 24 mois :
→ `nb_devis`, `nb_commandes`, `ca_facture`

```
Périodes clés imprimerie :
FORTE  : août-sept (rentrée) · oct-nov (Noël) · mars-avril (catalogues printemps)
FAIBLE : juillet · fin décembre · début août
```
→ Comparer aux mêmes mois N-1
→ Identifier si la tendance est structurelle ou conjoncturelle

### Mix produit imprimerie
Extraire depuis les lignes de devis/commandes :
- `label` → détecter type : flyer, catalogue, brochure, carte de visite, affiche, packaging…
- `qty`, `total_ht`
- Regrouper par type + finition (pelliculage, vernis UV, dorure, découpe)
- Calculer : `nb_devis`, `taux_conversion`, `ca_moyen` par famille

→ Identifier les best-sellers et les formats sous-convertis (beaucoup devisés, peu commandés)

---

## Processus d'analyse

**Étape 1 — Définir le périmètre**
- Type d'analyse : commerciale | client | devis | opérationnelle | fournisseur | mix
- Période : 3m | 6m | 12m | 24m | personnalisée
- Granularité : global | par client | par produit | par mois
- Profil utilisateur : ADMIN (accès total) | TEAM (sans données financières détaillées)

**Étape 2 — Collecter en parallèle**
- Lancer requêtes via `dolibarr-query-inpressco` en simultané si possible
- Prioriser les jeux de données les plus larges en premier

**Étape 3 — Calculer et croiser**
- Agréger, joindre les objets liés, calculer les indicateurs dérivés (ratios, délais, écarts)

**Étape 4 — Détecter motifs et anomalies**
- Comparer aux moyennes historiques, identifier les aberrants, détecter les tendances

**Étape 5 — Produire les insights**
- Formuler les conclusions en langage actionnable — toujours terminer par des recommandations prescriptives priorisées

---

## Format de sortie

### Schéma JSON interne
```json
{
  "analyse": {
    "type": "segmentation_client | mix_produit | anomalies | tendances | bat | ...",
    "periode": "12 mois (mars 2025 – mars 2026)",
    "nb_objets_analyses": 247,
    "date_analyse": "2026-03-27"
  },
  "resultats": {
    "insights_principaux": [
      "67% du CA concentré sur 5 clients — risque de dépendance",
      "Taux de conversion en baisse : 72% T3 → 61% T4 2025",
      "Les catalogues A5 représentent 43% du volume devis"
    ],
    "anomalies_detectees": [
      {
        "type": "facture_sans_commande",
        "nb": 3,
        "detail": "FA-2026-045, FA-2026-067, FA-2026-089"
      }
    ],
    "segments_clients": {
      "champions": 4,
      "fideles": 12,
      "prometteurs": 3,
      "a_risque": 7,
      "perdus": 23,
      "prospects_froids": 15
    },
    "recommandations": [
      "⚡ URGENT : relancer les 7 clients 'à risque' (CA cumulé 34K€)",
      "🔍 Investiguer les 3 factures sans commande liée",
      "📊 Diversifier — Agence Exemple représente 31% du CA seule"
    ]
  }
}
```

### Présentation utilisateur — Segmentation clients
```
📊 SEGMENTATION CLIENTS — 12 mois (mars 2025 → mars 2026)

🏆 Champions (4 clients) — commandes régulières, fort CA
   → Agence Exemple · Dupont SARL · …
   → Action : proposer montée en gamme (packaging, finitions premium)

⚠ À risque (7 clients) — actifs avant, silencieux depuis 4+ mois
   → CA potentiel perdu si inaction : ~34K€ HT
   → Action : campagne de réactivation ciblée cette semaine

💤 Perdus (23 clients) — aucune commande depuis > 12 mois
   → Représentaient X€ HT — opportunité de reconquête

Insight clé : 67% du CA concentré sur 5 clients
⚠ Risque de dépendance — diversification recommandée
```

### Présentation utilisateur — Mix produit
```
📦 MIX PRODUIT — 6 mois

Top formats devisés :
1. Catalogues A5 — 43% des devis · taux conversion 78%
2. Flyers A6 — 31% des devis · taux conversion 52% ⚠ (trop faible)
3. Brochures A4 piqûre cheval — 18% · conversion 81%

Finitions phares : pelliculage mat (67%), vernis UV sélectif (28%)

Insight : les flyers A6 génèrent beaucoup de devis mais peu de commandes
→ Vérifier le positionnement prix ou les délais annoncés sur ce format
```

### Présentation utilisateur — Anomalies
```
🔍 3 anomalies détectées dans les données Dolibarr :

1. Factures sans commande liée (3)
   → FA-2026-045 · FA-2026-067 · FA-2026-089
   → Vérifier si commandes manquantes ou ventes directes non tracées

2. Devis ouverts depuis > 60j sans statut (5)
   → Relancer ou marquer comme perdus pour fiabiliser le pipe

3. Tiers potentiellement en doublon (2 paires)
   → "Agence Ex" et "Agence Exemple SARL" — même email ?
```

---

## Règles importantes

- **Accès ADMIN** → analyses complètes CA et données financières
- **Accès TEAM** → analyses opérationnelles (retards, anomalies, pipeline) sans détail financier
- Ce skill est en **lecture seule** — ne corrige pas les anomalies
- Les anomalies doivent être **vérifiées humainement** avant action corrective
- **Toujours préciser la période** d'analyse — jamais de contexte temporel sans date
- **Grands volumes** (> 500 objets) : paginer les requêtes via `dolibarr-query-inpressco`
- **Toujours terminer par des recommandations actionnables priorisées** — l'analyse sans recommandation n'a pas de valeur
- Complémentaire à `controleur-gestion-inpressco` : celui-ci analyse les flux financiers, ce skill analyse les comportements et modèles
