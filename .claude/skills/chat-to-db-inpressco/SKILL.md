---
name: chat-to-db-inpressco
description: >
  Skill de structuration et persistance des données issues des conversations Claude pour In'Pressco. Déclencher SYSTÉMATIQUEMENT dès qu'une conversation produit des données exploitables qui doivent être sauvegardées : informations client collectées oralement ou par chat, briefs de projets exprimés en langage naturel, décisions prises en conversation, préférences exprimées, mises à jour de statut communiquées verbalement, informations nouvelles sur un tiers non encore dans Dolibarr. Utiliser aussi quand l'utilisateur dit "note ça", "enregistre", "retiens", "mets à jour", "sauvegarde cette info", ou quand une conversation contient des données structurables qui seraient perdues si non persistées. Ne jamais laisser une donnée utile disparaître dans le chat sans l'avoir structurée et routée vers la bonne destination.
---

# Chat → DB — In'Pressco

## Rôle
Extraire, structurer et router vers la bonne destination toutes les données utiles produites dans une conversation Claude. Ce skill est le pont entre le langage naturel et les bases de données du système — Dolibarr et base images. Il ne crée pas lui-même les enregistrements mais prépare les payloads structurés et déclenche les workflows ou skills d'écriture appropriés.

---

## Principe fondamental

Toute conversation Claude peut contenir des données qui ont de la valeur au-delà de la session :

- Un client qui donne ses coordonnées → fiche tiers Dolibarr
- Un brief exprimé oralement → données pour un devis
- Une préférence exprimée → note sur le tiers
- Une décision de statut → mise à jour document Dolibarr
- Une information sur un projet → agenda event ou note
- Un visuel validé ou refusé → métadonnée base images

Sans ce skill, ces données restent dans le chat et disparaissent.

---

## Types de données détectables

### Données tiers (client / fournisseur)
Expressions déclenchantes :
- "Je m'appelle X, je suis de la société Y"
- "Mon email c'est...", "vous pouvez me joindre au..."
- "Notre adresse est...", "notre SIREN est..."
- "C'est pour le compte de..."

→ Destination : `POST /thirdparties` (création) ou `PUT /thirdparties/{id}` (mise à jour) via workflow approprié

### Brief de projet / devis
Expressions déclenchantes :
- "Je voudrais commander...", "on a besoin de..."
- "C'est pour un tirage de X exemplaires..."
- "Format A5, couché mat, 4 couleurs..."
- "Livraison pour le...", "budget autour de..."

→ Destination : skill `inpressco-devis` avec les données pré-structurées

### Préférences et notes client
Expressions déclenchantes :
- "On préfère toujours le couché mat"
- "Ne pas appeler le matin"
- "Le décideur final c'est..."
- "Ils sont très sensibles aux délais"
- "Client difficile sur les prix"

→ Destination : `note_public` ou `note_private` du tiers Dolibarr via workflow dépôt

### Mises à jour de statut
Expressions déclenchantes :
- "Le client a validé le BAT"
- "Ils ont signé le devis"
- "La commande est livrée"
- "Ils annulent finalement"
- "Ils repoussent à septembre"

→ Destination : changement de statut sur le document Dolibarr concerné + agenda event

### Décisions et échanges à logguer
Expressions déclenchantes :
- "On a convenu que...", "on s'est mis d'accord sur..."
- "Ils demandent un délai supplémentaire"
- "RDV fixé pour le..."
- "Rappeler le X à propos de..."

→ Destination : agenda event Dolibarr lié au tiers ou au document

### Données base images
Expressions déclenchantes :
- "Ce visuel est validé pour Instagram"
- "Cette image ne correspond pas à notre charte"
- "Utiliser ce visuel pour la prochaine campagne"
- "Archiver ce BAT comme référence"

→ Destination : métadonnées base images (tags, statut, client associé)

---

## Processus d'extraction et structuration

### Étape 1 — Détection
Scanner la conversation à la recherche de données persistables :
- Entités nommées : noms, emails, téléphones, adresses, références
- Données techniques : formats, quantités, grammages, finitions
- Statuts et décisions : validé, annulé, livré, reporté
- Dates et échéances : livraison, RDV, relance
- Préférences : habitudes, contraintes, interlocuteurs

### Étape 2 — Classification
Déterminer la destination de chaque donnée :

| Donnée | Destination |
|--------|-------------|
| Coordonnées tiers nouvelles ou manquantes | Dolibarr / fiche tiers |
| Brief complet ou partiel | skill `inpressco-devis` |
| Note ou préférence | `note_private` ou `note_public` Dolibarr |
| Changement de statut | workflow statut + agenda event |
| RDV ou rappel | agenda event Dolibarr |
| Décision / échange | agenda event `AC_OTH_AUTO` |
| Visuel / image | base images (métadonnées) |

### Étape 3 — Structuration du payload
Transformer le langage naturel en données structurées :

**Exemple — brief oral → payload devis**

Input : *"500 flyers A6 recto-verso, couché brillant 135g, livraison vendredi"*

```json
{
  "produit": "flyer",
  "format_ferme": { "largeur": 105, "hauteur": 148 },
  "quantite": 500,
  "impression": "recto-verso",
  "support": "couché brillant",
  "grammage": 135,
  "date_livraison": "2026-03-29",
  "confiance": {
    "format": "high",
    "quantite": "high",
    "support": "high",
    "date": "medium"
  }
}
```

**Exemple — préférence → note Dolibarr**

Input : *"Ils préfèrent qu'on ne contacte pas Nicolas, c'est Marie le bon interlocuteur"*

```json
{
  "type": "note_private",
  "socid": "{socid_résolu}",
  "contenu": "Interlocuteur privilégié : Marie. Ne pas contacter Nicolas directement.",
  "date": "{today}"
}
```

**Exemple — validation BAT → agenda event**

Input : *"Le client vient de valider le BAT par téléphone"*

```json
{
  "type_code": "AC_OTH_AUTO",
  "label": "BAT validé par le client",
  "note": "Validation orale reçue par téléphone. Lancer la production.",
  "elementtype": "commande",
  "fk_element": "{id_commande}",
  "socid": "{socid}",
  "datep": "{now_epoch}",
  "done": 1
}
```

### Étape 4 — Validation avant persistance
Avant d'écrire quoi que ce soit :
- Afficher le résumé structuré à l'utilisateur
- Demander confirmation si la donnée est sensible ou irréversible
- Signaler les données incomplètes ou incertaines (confiance `low`)
- Ne jamais écraser une donnée existante sans avertir

### Étape 5 — Router vers le bon effecteur

| Type | Effecteur |
|------|-----------|
| Données tiers | workflow création/mise à jour tiers |
| Brief | skill `inpressco-devis` (avec payload pré-rempli) |
| Note | skill `archiveur` ou workflow dépôt Dolibarr |
| Statut | workflow action Dolibarr |
| Agenda | `POST /agendaevents` via workflow |
| Base images | skill `bdd-images-query-inpressco` + `archiveur` |

---

## Niveaux de confiance

Chaque champ extrait porte un niveau de confiance :

| Niveau | Critère | Comportement |
|--------|---------|--------------|
| `high` | Explicitement énoncé, non ambigu | Persister directement après confirmation |
| `medium` | Déduit du contexte, probable | Persister avec mention "déduit" |
| `low` | Incertain, à vérifier | Demander confirmation avant persistance |
| `missing` | Non mentionné, champ requis | Demander à l'utilisateur avant persistance |

---

## Schéma JSON de sortie

```json
{
  "extraction": {
    "source": "conversation | email | vocal | formulaire",
    "session_id": "{id_conversation}",
    "date": "{timestamp}",
    "nb_entites_detectees": 4
  },
  "entites": [
    {
      "type": "tiers | brief | note | statut | agenda | image",
      "destination": "dolibarr_tiers | dolibarr_note | dolibarr_agenda | devis | base_images",
      "payload": {},
      "confiance_globale": "high | medium | low",
      "champs_incertains": ["date_livraison"],
      "action_requise": "confirmer | compléter | persister_auto"
    }
  ],
  "alertes": [
    {
      "type": "CHAMP_MANQUANT | AMBIGUÏTÉ | DOUBLON_POTENTIEL",
      "message": "Format non précisé — A5 déduit de l'historique client",
      "champ": "format_ferme"
    }
  ]
}
```

---

## Présentation à l'utilisateur

### Données détectées — confirmation requise
```
Données détectées — confirmation requise

→ Nouveau tiers : Imprimerie Martin · martin@imprimerie.fr · 04 XX XX XX XX
   [Créer dans Dolibarr ?] [Modifier] [Ignorer]

→ Brief : 500 flyers A6 recto-verso couché brillant 135g · livraison vendredi
   [Lancer le devis] [Compléter d'abord] [Ignorer]

→ Note interne : interlocuteur = Marie (pas Nicolas)
   [Enregistrer sur la fiche] [Ignorer]
```

### Donnée incomplète — champ manquant
```
Le brief est presque complet, mais il manque :
→ Finition (pelliculage, vernis, aucune ?) — obligatoire pour le devis
→ Adresse de livraison — nécessaire si différente de l'adresse facturation

Pouvez-vous préciser ces points ?
```

### Confirmation de persistance
```
✓ Note enregistrée sur la fiche Agence Exemple (Dolibarr)
✓ Brief transmis au module devis — DEV-2026-XXX en création
✓ Événement agenda loggué : BAT validé le 26/03/2026
```

---

## Règles importantes

- **Ne jamais persister sans confirmation** pour les données de type création ou mise à jour Dolibarr
- **Persister automatiquement** uniquement les logs d'agenda (événements passés, non modifiables)
- **Signaler les doublons potentiels** avant création — appeler `dolibarr-query-inpressco` d'abord
- **Conserver les données non persistées** dans le contexte de la conversation jusqu'à résolution
- **Distinguer** ce qui va dans `note_public` (visible client sur PDF) vs `note_private` (interne uniquement)
- **Ne jamais inventer** de données manquantes — signaler et demander
- Les données `confiance: low` ne sont jamais persistées automatiquement

---

## Exemples complets

### Brief oral capturé en conversation

Utilisateur : *"Paola a appelé, Agence Exemple veut 1000 catalogues A5 24 pages couché mat pelliculage mat, pour le 15 avril"*

```json
{
  "tiers": { "nom": "Agence Exemple", "action": "identifier_existant" },
  "brief": {
    "produit": "catalogue",
    "format_ferme": { "largeur": 148, "hauteur": 210 },
    "nb_pages": 24,
    "quantite": 1000,
    "support": "couché mat",
    "finition": "pelliculage mat",
    "date_livraison": "2026-04-15",
    "confiance": { "format": "high", "quantite": "high", "date": "high" }
  }
}
```
→ Vérifier si Agence Exemple existe dans Dolibarr → lancer skill `inpressco-devis` avec payload pré-rempli

### Mise à jour statut verbale

*"CMD-2026-045 est livrée, tout s'est bien passé"*

```json
{
  "type": "statut",
  "ref": "CMD-2026-045",
  "nouveau_statut": 3,
  "agenda_event": {
    "label": "Commande livrée — retour positif client",
    "type_code": "AC_OTH_AUTO",
    "done": 1
  }
}
```
→ Mettre à jour statut commande + logger l'événement agenda

### Nouvelle information sur contact

*"En fait leur décideur c'est Thomas Renard, pas Marie"*

```json
{
  "type": "note",
  "socid": "{socid_agence_exemple}",
  "note_private": "Décideur : Thomas Renard. Marie est prescriptrice uniquement. Mise à jour 26/03/2026."
}
```
→ Mettre à jour `note_private` du tiers Dolibarr

---

## Notes importantes

- Ce skill est **complémentaire au skill `archiveur`** — Chat→DB structure et route les données textuelles, l'archiveur gère les fichiers et pièces jointes
- Il est **complémentaire au skill `extraction-tiers`** — `extraction-tiers` opère sur les emails entrants, Chat→DB opère sur les conversations Claude
- Les données persistées alimentent automatiquement le skill `memoire-client` lors des prochaines interactions
- En cas de conflit entre une donnée de la conversation et une donnée Dolibarr existante → **toujours signaler, jamais écraser silencieusement**
