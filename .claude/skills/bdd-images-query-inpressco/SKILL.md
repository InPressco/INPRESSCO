---
name: bdd-images-query-inpressco
description: >
  Skill de recherche et consultation de la base de données images pour In'Pressco — imprimeur façonnier. Déclencher SYSTÉMATIQUEMENT dès qu'un visuel existant doit être retrouvé, consulté, vérifié ou listé, et AVANT toute génération d'image. Triggers immédiats : "est-ce qu'on a déjà un visuel pour ce client", "retrouve le logo d'Agence Exemple", "quels visuels Instagram on a pour la campagne printemps", "cherche le BAT de référence pour ce projet", "liste les images validées pour ce tiers", "avez-vous déjà fait un visuel pour X", "on a des templates disponibles ?", "montre-moi les assets de ce client". Déclencher aussi chaque fois qu'un autre skill veut générer une image — ce skill est le garde-fou anti-doublon. Ne jamais générer une nouvelle image sans avoir d'abord interrogé cette base.
---

# BDD Images Query — In'Pressco

## Rôle
Interroger la base de données images InPressco en **lecture seule** pour :
- Retrouver des visuels existants **avant** toute génération
- Vérifier la disponibilité d'un asset ou d'un template
- Lister les ressources graphiques associées à un tiers, une campagne ou une commande Dolibarr

> ⚠️ Ce skill est en **lecture seule**. Pour archiver ou modifier des métadonnées, utiliser le skill `archiveur-inpressco`.

---

## Comment la base est stockée

Les images InPressco sont archivées comme **pièces jointes sur les objets Dolibarr** (commandes, devis, tiers) et/ou dans un **dossier fichiers partagé** accessible via l'API Dolibarr.

### Méthodes d'interrogation disponibles

**1. Pièces jointes sur un tiers (socid connu)**
```
GET /api/index.php/thirdparties/{socid}/attachments
```

**2. Pièces jointes sur une commande**
```
GET /api/index.php/orders/{id}/attachments
```

**3. Pièces jointes sur un devis**
```
GET /api/index.php/proposals/{id}/attachments
```

**4. Recherche par notes/tags dans les objets Dolibarr**
→ Utiliser le skill `dolibarr-query-inpressco` pour retrouver d'abord le socid ou la ref, puis interroger les pièces jointes.

> Si la base images est un dossier fichier partagé séparé (ex. NAS ou Google Drive), adapter la méthode d'accès selon la configuration de l'atelier.

---

## Structure et métadonnées

### Catégories principales

| Catégorie | Contenu |
|-----------|---------|
| `generated_ai` | Visuels générés par Claude / IA (posts, campagnes) |
| `photo_produit` | Photos d'imprimés livrés (catalogue, flyers) |
| `asset_graphique` | Logos, chartes, éléments graphiques client |
| `reference_bat` | BAT archivés comme référence validée |
| `template` | Gabarits réutilisables (Instagram, devis, etc.) |

### Convention de nommage InPressco
```
{TYPE}_{Client}_{REF-ou-CAM}_{AAAAMMJJ}_{version}.{ext}
Exemples :
  VISUEL_AgenceExemple_CAM-Printemps_20260315_vFINAL.jpg
  BAT_ClientABC_CMD-2026-038_20260310_v2.pdf
  LOGO_MonClient_20260101_v1.svg
```

### Métadonnées déductibles du nom de fichier + contexte Dolibarr
```
nom_fichier       : nom conforme convention InPressco
categorie         : generated_ai | photo_produit | asset_graphique | reference_bat | template
tiers_associe     : socid ou nom du client
ref_dolibarr      : référence commande ou devis
date_creation     : date dans le nom ou date de dépôt
statut            : brouillon | validé | archivé | refusé (déduit du suffixe vFINAL, v1, etc.)
format            : jpg | png | svg | ai | pdf | webp
auteur            : claude | paola | nicolas | externe
tags              : extraits du nom, notes Dolibarr, ou renseignés manuellement
```

---

## Processus de recherche

### Étape 1 — Analyser la demande et identifier les filtres

| Demande | Stratégie |
|---------|-----------|
| "Visuel pour Agence Exemple" | → recherche par tiers (socid) |
| "BAT du catalogue de mars" | → recherche par ref Dolibarr + catégorie `reference_bat` |
| "Posts Instagram printemps" | → recherche par tags [instagram, printemps] + catégorie `generated_ai` |
| "Logo du client X" | → recherche par tiers + catégorie `asset_graphique` |
| "Templates disponibles" | → lister catégorie `template` sans filtre tiers |
| "Assets de la commande CMD-2026-038" | → recherche par ref_dolibarr |

### Étape 2 — Résoudre le tiers si nécessaire
Si le client est mentionné par nom mais que le socid est inconnu :
→ Appeler `dolibarr-query-inpressco` pour retrouver le socid avant d'interroger les pièces jointes.

### Étape 3 — Interroger la base
Utiliser la ou les méthodes API disponibles selon les filtres identifiés.
Combiner plusieurs appels si nécessaire (ex. : pièces jointes du tiers + pièces jointes d'une commande liée).

### Étape 4 — Filtrer et trier les résultats
- Filtrer par catégorie, statut, tags si applicable
- Trier : **validé en premier**, puis par date décroissante
- Limiter à **10 résultats** par défaut ; proposer d'affiner si > 10

### Étape 5 — Recommandation selon statut

| Statut trouvé | Action recommandée |
|---------------|-------------------|
| `validé` | Proposer de réutiliser l'existant |
| `brouillon` | Proposer de finaliser avant de regénérer |
| `refusé` | Signaler — ne jamais réutiliser sans validation explicite |
| `archivé` | Proposer comme référence historique uniquement |
| Aucun résultat | Confirmer qu'on peut générer un nouveau visuel |

---

## Gestion des droits d'accès

| Profil | Accès |
|--------|-------|
| `CLIENT` | Uniquement les assets associés à son propre socid |
| `TEAM` | Accès complet à toute la base images |
| `ADMIN` | Accès complet + métadonnées techniques |

> Si le profil n'est pas connu, vérifier via le skill `droits-profils-inpressco` avant d'exposer des assets d'autres clients.

---

## Format de sortie

### Résultats trouvés — présentation utilisateur
```
📁 3 visuels trouvés — Agence Exemple · Campagne printemps

1. VISUEL_AgenceExemple_CAM-Printemps_20260315_vFINAL.jpg
   ✅ Validé · 1080×1080px · 15/03/2026
   Tags : instagram, printemps, catalogue

2. VISUEL_AgenceExemple_CAM-Printemps_20260310_v2.jpg
   📦 Archivé · 1080×1080px · 10/03/2026

3. VISUEL_AgenceExemple_CAM-Printemps_20260308_v1.jpg
   ❌ Refusé · 1080×1080px · 08/03/2026

→ Le visuel validé du 15/03 est disponible pour réutilisation.
   [Utiliser ce visuel] [Générer un nouveau] [Voir les détails]
```

### Aucun résultat
```
Aucun visuel trouvé pour ce critère dans la base images.

→ Souhaitez-vous générer un nouveau visuel ?
   [Générer via IA] [Annuler]
```

### JSON interne (pour enchaînement avec d'autres skills)
```json
{
  "recherche": {
    "criteres": {
      "tiers": "Agence Exemple SARL",
      "socid": 42,
      "categorie": "generated_ai",
      "tags": ["instagram", "printemps"],
      "statut": "validé"
    },
    "nb_resultats": 3,
    "statut": "found"
  },
  "resultats": [
    {
      "nom_fichier": "VISUEL_AgenceExemple_CAM-Printemps_20260315_vFINAL.jpg",
      "categorie": "generated_ai",
      "statut": "validé",
      "date_creation": "2026-03-15",
      "dimensions": "1080x1080",
      "tags": ["instagram", "printemps", "catalogue"],
      "note": "Visuel carré Instagram campagne printemps 2026",
      "tiers_associe": "Agence Exemple SARL",
      "ref_dolibarr": "CMD-2026-038",
      "url_dolibarr": "/document.php?modulepart=commande&file=..."
    }
  ],
  "recommandation": "réutiliser | finaliser_brouillon | regénérer | générer_nouveau"
}
```

---

## Règles absolues

1. **Toujours appeler ce skill avant** tout skill de génération d'image — prérequis non négociable
2. Un visuel `refusé` ne doit **jamais** être réutilisé sans validation explicite de l'équipe
3. Ce skill est en **lecture seule** — les modifications passent par `archiveur-inpressco`
4. Si le socid est inconnu, passer d'abord par `dolibarr-query-inpressco`
5. En cas d'erreur API, signaler via `gestion-erreurs-inpressco` et proposer une recherche manuelle

---

## Skills liés

| Skill | Relation |
|-------|----------|
| `archiveur-inpressco` | Dépôt et mise à jour des métadonnées (écriture) |
| `dolibarr-query-inpressco` | Résolution du socid ou de la ref avant recherche |
| `droits-profils-inpressco` | Vérification des droits d'accès |
| `gestion-erreurs-inpressco` | Gestion des erreurs API |
