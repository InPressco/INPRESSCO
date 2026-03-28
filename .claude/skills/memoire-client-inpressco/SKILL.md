---
name: memoire-client-inpressco
description: >
  Skill de mémoire contextuelle client pour In'Pressco. Déclencher SYSTÉMATIQUEMENT dans TOUS ces cas : (1) dès qu'un nom de société, un email client ou une référence de tiers apparaît dans la conversation — même sans demande explicite ; (2) dès qu'un email entrant est analysé ou routé, AVANT toute réponse ; (3) dès qu'un autre skill est activé (inpressco-devis, inpressco-commerce, suivi-commande, reponse-client, notification-interne...) — ce skill doit alimenter les autres en contexte ; (4) quand l'utilisateur pose une question sur un client ou prospect, même vague ("il commande souvent ?", "c'est qui eux ?", "on a déjà travaillé avec eux ?"). Ce skill reconstitue le contexte complet d'un tiers : historique Dolibarr, charte graphique, visuels/BAT archivés, artefacts Claude sauvegardés, score de satisfaction, alertes actives. Il est le socle de personnalisation de toutes les réponses In'Pressco. Ne jamais répondre à froid à un client identifiable sans avoir activé ce skill.
---

# Mémoire client — In'Pressco

## Rôle
Reconstituer et maintenir le contexte complet d'un tiers pour que Claude ne réponde **jamais** "à froid". Chaque interaction avec un client connu doit être enrichie par son historique — volume de commandes, préférences matériaux, projets en cours, charte graphique, visuels produits, points de friction passés, interlocuteurs habituels.

---

## Déclenchement — règles étendues

Ce skill se déclenche **automatiquement et sans attendre** dès que l'un de ces signaux est détecté :

| Signal | Exemple |
|--------|---------|
| Nom de société mentionné | "Agence Exemple", "le client Dupont", "pour Martin SA" |
| Email identifiable dans la conv. | `m.dupont@agence-exemple.fr` dans un email collé |
| Référence Dolibarr | `DEV-2026-089`, `CMD-2026-012`, `FA-2026-XXX` |
| Activation d'un autre skill | inpressco-devis, inpressco-commerce, reponse-client, suivi-commande... |
| Question implicite sur un client | "ils commandent souvent ?", "c'est un bon client ?" |
| Email entrant routé | Dès que mail-routing ou analyse-sentiment-email s'active |

> **Règle d'or** : si un tiers est identifiable dans la conversation, ce skill est prioritaire avant toute autre action.

---

## Sources de données

Ce skill agrège les données depuis **cinq niveaux** :

**1. Dolibarr (via skill `dolibarr-query-inpressco`)** — données structurées
- Fiche tiers complète (coordonnées, codes, notes publiques et privées)
- Historique devis, commandes, factures
- Lignes et descriptifs des documents passés
- Événements agenda et échanges loggés
- Pièces jointes archivées
- Contacts et interlocuteurs

**2. Assets visuels (via skill `bdd-images-query-inpressco`)** — production graphique
- Visuels et BAT produits pour ce client
- Templates utilisés
- Références visuelles archivées

**3. Charte graphique (via skill `charte-graphique-inpressco`)** — identité visuelle
- Couleurs de marque (codes hex/Pantone)
- Typographies utilisées
- Logo et éléments graphiques connus
- Contraintes de mise en page signalées

**4. Artefacts Claude (via skill `projets-artefacts-inpressco`)** — productions sauvegardées
- Devis rédigés lors de sessions précédentes
- Emails et réponses préparés
- Briefs structurés et récapitulatifs projet
- Analyses tarifaires mémorisées

**5. Conversation en cours** — contexte immédiat
- Ce que le client vient d'exprimer
- Informations nouvelles non encore dans Dolibarr
- Ton et registre de communication détectés

---

## Processus de reconstitution du contexte

### Étape 1 — Identifier le tiers
```
Signal email → GET /thirdparties?sqlfilters=(t.email:=:'{email}')
Signal nom   → GET /thirdparties?sqlfilters=(t.nom:like:'%{nom}%')
Signal réf   → extraire socid depuis GET /proposals/ref/{ref}
Socid connu  → passer directement à l'étape 2
```
Si non trouvé dans Dolibarr → profil `NOUVEAU`, continuer avec les données de la conversation.
En cas d'homonymes → présenter les options à l'utilisateur avant de charger un contexte.

### Étape 2 — Charger l'historique complet (requêtes parallèles)
```
GET /thirdparties/{socid}                          → fiche + notes
GET /thirdparties/{socid}/contacts                 → interlocuteurs
GET /proposals?thirdparty_ids={socid}&limit=50     → tous les devis
GET /orders?thirdparty_ids={socid}&limit=50        → toutes les commandes
GET /invoices?thirdparty_ids={socid}&limit=50      → toutes les factures
GET /agendaevents?thirdparty_ids={socid}&limit=100 → historique échanges
```
En parallèle : interroger `bdd-images-query-inpressco`, `charte-graphique-inpressco`, `projets-artefacts-inpressco` si disponibles.

### Étape 3 — Analyser et qualifier

**Profil commercial**
- Ancienneté (date premier devis / commande)
- Volume : nombre de commandes, montant cumulé HT
- Fréquence : régulier / occasionnel / inactif (dernière commande > 12 mois)
- Segment : petit compte / compte moyen / grand compte
- Taux de conversion devis → commande

**Préférences techniques détectées**
- Formats récurrents (A5, A4, A3, plié...)
- Supports récurrents (couché mat, couché brillant, offset, kraft...)
- Finitions récurrentes (pelliculage mat/brillant, vernis sélectif, dorure...)
- Quantités habituelles
- Délais habituellement demandés

**Score de satisfaction (déduit de l'historique)**
- `⭐⭐⭐ EXCELLENT` : taux conversion > 70%, commandes régulières, aucun litige
- `⭐⭐ BON` : taux conversion 40–70%, quelques relances nécessaires
- `⭐ FRAGILE` : taux conversion < 40%, litiges ou frictions signalés, impayés passés
- `❓ INCONNU` : historique insuffisant (< 2 interactions)

Points de friction détectés (à signaler explicitement) :
- Retards de paiement passés
- Litiges qualité ou délai signalés dans notes/agenda
- BAT refusés ou multiples allers-retours
- Devis systématiquement renégociés

**Interlocuteurs**
- Contact principal (nom, email, poste)
- Contacts secondaires connus
- Décideur vs prescripteur

**Alertes actives**
- 🔴 CRITIQUE : Factures impayées (`remaintopay > 0`) ou litige en cours
- 🟠 URGENTE : BAT en attente de validation depuis > 5 jours
- 🟡 ATTENTION : Devis en attente de signature depuis > 30 jours
- 🔵 INFO : Relances programmées, RDV à venir

**Statut relationnel**
- `ACTIF` : commande dans les 6 derniers mois
- `TIÈDE` : dernière commande entre 6 et 18 mois
- `INACTIF` : aucune commande depuis > 18 mois
- `PROSPECT` : devis émis, jamais commandé
- `NOUVEAU` : aucun historique Dolibarr

---

## Schéma JSON de sortie (contexte client)

```json
{
  "tiers": {
    "socid": "42",
    "nom": "Agence Exemple SARL",
    "code_client": "CU2026-0042",
    "email": "contact@agence-exemple.fr",
    "phone": "04 XX XX XX XX",
    "ville": "Lyon",
    "contact_principal": {
      "nom": "Marie Dupont",
      "poste": "Directrice artistique",
      "email": "m.dupont@agence-exemple.fr"
    },
    "note_public": "Client fidèle — délais courts fréquents",
    "note_private": "Sensible au prix — toujours demander validation avant lancement"
  },
  "profil_commercial": {
    "statut": "ACTIF",
    "anciennete": "3 ans (premier devis : mars 2023)",
    "nb_devis": 12,
    "nb_commandes": 8,
    "taux_conversion": "67%",
    "montant_cumule_ht": "18 450 €",
    "derniere_commande": "2026-01-14",
    "segment": "compte moyen",
    "score_satisfaction": "⭐⭐ BON",
    "points_de_friction": ["relances BAT fréquentes (x3 en 2025)"]
  },
  "preferences_techniques": {
    "formats": ["A5 fermé", "A4 fermé"],
    "supports": ["couché mat 170g", "couché brillant 135g"],
    "finitions": ["pelliculage mat", "vernis sélectif"],
    "quantites_habituelles": ["500", "1000"],
    "delais": "souvent urgents (< 10 jours)"
  },
  "charte_graphique": {
    "disponible": true,
    "couleurs": ["#1A2B5F", "#E8C84A"],
    "typographies": ["Montserrat Bold", "Open Sans Regular"],
    "source": "charte-graphique-inpressco"
  },
  "assets_visuels": {
    "nb_visuels_archives": 5,
    "derniers_bat": ["BAT_CatalogueA5_v3_2025-11.pdf", "BAT_FlyerA6_2026-01.pdf"],
    "source": "bdd-images-query-inpressco"
  },
  "artefacts_claude": {
    "disponibles": true,
    "liste": ["Devis_AgenceExemple_Catalogue2026 (15/03)", "Brief_Campagne_Printemps (10/03)"],
    "source": "projets-artefacts-inpressco"
  },
  "en_cours": {
    "devis_ouverts": [
      {
        "ref": "DEV-2026-089",
        "date": "2026-03-10",
        "montant_ht": "1 250 €",
        "statut": "validé — en attente signature"
      }
    ],
    "commandes_actives": [],
    "factures_impayees": []
  },
  "alertes": [
    {
      "niveau": "🟡 ATTENTION",
      "type": "DEVIS_EN_ATTENTE",
      "message": "DEV-2026-089 validé depuis 16 jours sans retour",
      "action_suggeree": "Relancer Marie Dupont par email"
    }
  ],
  "historique_recent": [
    "15/03 — Devis DEV-2026-089 envoyé (catalogue A5 500ex)",
    "10/03 — Email brief reçu et routé",
    "14/01 — Commande CMD-2026-012 livrée (flyers A6 1000ex)"
  ]
}
```

---

## Présentation à l'utilisateur

### Mode COMPACT — cas simples (question rapide, contexte secondaire)
```
Agence Exemple SARL · Client actif · ⭐⭐ BON · 8 commandes · 18 450 € HT
Contact : Marie Dupont · Habitudes : A5, couché mat, 500–1000ex, délais courts
🟡 DEV-2026-089 en attente signature depuis 16j
```

### Mode FICHE — cas complets (nouveau brief, devis à préparer, réponse client)
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  AGENCE EXEMPLE SARL — Client actif depuis 3 ans
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Contact    Marie Dupont (DA) · m.dupont@agence-exemple.fr
  Historique 8 commandes · 18 450 € HT · Taux conversion 67%
  Satisfaction ⭐⭐ BON · ⚠️ relances BAT fréquentes (x3 en 2025)

  Habitudes techniques
  → Formats   : A5 fermé, A4 fermé
  → Supports  : couché mat 170g, couché brillant 135g
  → Finitions : pelliculage mat, vernis sélectif
  → Quantités : 500–1000ex · Délais : souvent urgents

  Charte graphique  ✓ disponible (#1A2B5F · #E8C84A · Montserrat)
  Visuels archivés  5 fichiers · BAT_CatalogueA5_v3, BAT_FlyerA6
  Artefacts Claude  Devis_Catalogue2026 (15/03), Brief_Printemps (10/03)

  En cours
  → 🟡 DEV-2026-089 · 1 250 € HT · en attente signature depuis 16j

  Dernière commande  CMD-2026-012 · flyers A6 1000ex · livrée 14/01
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Mode ALERTE — signal critique (🔴 ou 🟠), affiché EN PREMIER
```
🔴 ALERTE AVANT DE POURSUIVRE
[Nom société] a [N] facture(s) impayée(s) :
→ FA-2026-XXX · [montant] € · échue le [date]
Signaler à l'équipe avant de continuer ? (oui / non)
```

### Client nouveau — aucun historique
```
Nouveau prospect — aucun historique Dolibarr.
Pas de charte, ni de visuels, ni d'artefacts connus.
Profil construit à partir des informations de la conversation.
```

**Règle de choix de mode** : compact si la demande est une question simple ou une vérification rapide ; fiche complète si un devis, une réponse client ou un brief doit être produit.

---

## Utilisation du contexte par les autres skills

- **`inpressco-devis`** : pré-remplir formats/supports habituels, charger charte, signaler BAT similaire existant
- **`inpressco-commerce`** : personnaliser ton, adapter fourchette tarifaire, mentionner projets précédents
- **`reponse-client` + `analyse-sentiment-email`** : prénom contact, points de friction, registre relationnel
- **`droits-profils`** : confirmer profil CLIENT actif vs nouveau prospect
- **`notification-interne`** : alerter équipe si alerte 🔴 ou 🟠 active
- **`bdd-images-query-inpressco`** : passer socid pour filtrer les visuels du client

---

## Règles de confidentialité

- Le contexte complet (notes privées, alertes impayés, score de friction) est réservé aux profils `TEAM` et `ADMIN`
- Un profil `CLIENT` ne reçoit que ses propres informations — jamais les notes internes
- Les `note_private` Dolibarr ne sont **jamais** transmises dans une réponse sortante client
- Les alertes impayés sont signalées à l'équipe mais **ne sont jamais mentionnées au client** sauf instruction explicite
- Les points de friction sont utilisés pour adapter le comportement interne uniquement

---

## Notes importantes

- Ce skill est **passif** — il enrichit le contexte, il ne prend pas de décision
- Il est appelé **automatiquement** dès qu'un tiers est identifiable, avant toute réponse
- Si Dolibarr est inaccessible → continuer avec les données de la conversation, signaler l'indisponibilité
- Si `bdd-images-query`, `charte-graphique` ou `projets-artefacts` sont inaccessibles → noter "non disponible", ne pas bloquer
- Le contexte est valable pour la durée de la conversation — ne pas rappeler Dolibarr à chaque message si le socid est déjà résolu
- Les préférences techniques sont **déduites** des commandes passées — elles peuvent évoluer
- En cas de doute sur l'identité (homonymes) → présenter les options avant de charger un contexte
