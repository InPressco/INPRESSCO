---
name: droits-profils-inpressco
description: >
  Skill de gestion des droits et profils utilisateurs pour In'Pressco. Déclencher SYSTÉMATIQUEMENT en début de toute interaction avant d'activer un workflow ou un skill sensible, dès qu'un utilisateur se présente, envoie une demande, ou que Claude doit décider quelles actions sont autorisées. Ce skill identifie le profil de l'interlocuteur (client externe, équipe InPressco, admin) et adapte en conséquence les actions disponibles, le niveau d'information partagé, et les validations requises. Ne jamais déclencher un workflow Dolibarr ou une action de modification de données sans avoir d'abord établi le profil via ce skill.
---

# Droits / Profils — In'Pressco

## Rôle
Identifier l'interlocuteur, lui attribuer un profil, et conditionner toutes les actions Claude en fonction de ses droits. Ce skill est la porte d'entrée de sécurité du système — il doit être résolu avant toute action sur Dolibarr, la base images, ou les workflows.

---

## Profils disponibles

| Profil | ID | Description | Signal |
|--------|----|-------------|--------|
| Client externe | `CLIENT` | Prospect ou client, pas de compte InPressco | Email non @inpressco.fr, formulaire site/shop, appel entrant |
| Équipe InPressco | `TEAM` | Collaborateur interne (production, commercial, admin) | Email @inpressco.fr ou canal interne authentifié |
| Admin | `ADMIN` | Dirigeant ou responsable système | Déclaration explicite + canal interne, ou code admin confirmé |
| Inconnu | `UNKNOWN` | Profil non déterminable | Aucun signal clair disponible |

---

## Matrice des droits par profil

| Action | CLIENT | TEAM | ADMIN |
|--------|--------|------|-------|
| Demander un devis | ✅ | ✅ | ✅ |
| Consulter ses propres devis / commandes | ✅ | ✅ | ✅ |
| Consulter les devis d'autres tiers | ❌ | ✅ | ✅ |
| Créer / modifier un enregistrement Dolibarr | ❌ | ✅ confirmation | ✅ direct |
| Déposer une PJ sur une commande | ✅ (ses docs) | ✅ | ✅ |
| Accéder à la base images | ❌ | ✅ lecture | ✅ lecture + écriture |
| Déclencher un workflow interne | ❌ | ✅ | ✅ |
| Modifier les paramètres Dolibarr | ❌ | ❌ | ✅ |
| Voir les tarifs fournisseurs | ❌ | ✅ | ✅ |
| Exporter des données clients | ❌ | ❌ | ✅ |

---

## Processus d'identification du profil

**Étape 1 — Vérifier le canal d'entrée**
```
Canal shop                 → CLIENT (commande e-commerce)
Canal site web / formulaire → CLIENT
Canal email @inpressco.fr  → TEAM (ou ADMIN si déclaré)
Canal WhatsApp / vocal / physique → analyse contexte étape 2
Canal interface interne Claude → TEAM par défaut, confirmer si ADMIN
```

**Étape 2 — Analyser le contenu et le contexte**
```
Présence d'un code ou mot-clé admin connu    → escalader vers ADMIN
Référence à un devis/commande personnel       → renforcer CLIENT
Vocabulaire métier interne (outils, process InPressco) → renforcer TEAM
Aucun signal                                  → UNKNOWN, demander confirmation
```

**Étape 3 — Confirmer si ambiguïté**

Si le profil est `UNKNOWN` ou si une action sensible est demandée par un profil `CLIENT` non vérifié :
```
Avant de continuer, pouvez-vous me confirmer votre nom et votre entreprise ?
```
Ne jamais bloquer une simple demande de devis — le profil `CLIENT` suffit pour les actions non sensibles.

---

## Règles de comportement par profil

### CLIENT
- Répondre avec le ton commercial du skill `inpressco-commerce`
- Ne jamais mentionner les tarifs fournisseurs, marges, ou données internes
- Toute demande de modification de données → rediriger vers l'équipe
- Accès lecture limité à ses propres documents (via référence Dolibarr connue)
- En cas de doute sur l'identité → demander confirmation avant toute consultation

### TEAM
- Accès complet aux workflows internes avec confirmation pour les actions destructives
- Peut initier tous les workflows sauf modification des paramètres système
- Réponses plus directes, sans le filtre commercial client
- Peut consulter les données de tous les tiers

### ADMIN
- Accès sans restriction à toutes les actions
- Pas de confirmation requise pour les opérations standard
- Confirmation requise uniquement pour les opérations irréversibles (suppression, export masse)
- Peut modifier les profils des autres utilisateurs

### UNKNOWN
- Mode lecture seule stricte
- Aucune action Dolibarr déclenchée
- Demander systématiquement une identification avant de continuer
- Logger la tentative d'accès non identifié

---

## Schéma JSON de sortie

```json
{
  "profil": {
    "id": "CLIENT | TEAM | ADMIN | UNKNOWN",
    "confidence": "high | medium | low",
    "signal": "Description du signal ayant déterminé le profil",
    "canal": "mail | site | shop | vocal | physique | interne | whatsapp"
  },
  "droits": {
    "lecture_dolibarr": true,
    "ecriture_dolibarr": false,
    "acces_base_images": false,
    "declenchement_workflows": false,
    "acces_donnees_tiers": false,
    "confirmation_requise": true
  },
  "action_suivante": "Description de l'action autorisée ou du blocage",
  "alerte": null
}
```

**Règles JSON :**
- `confidence: low` → toujours demander confirmation avant action sensible
- `confirmation_requise: true` pour `CLIENT` sur toute écriture Dolibarr
- `confirmation_requise: true` pour `TEAM` sur actions destructives
- `alerte` renseigné si profil `UNKNOWN` tente une action sensible

---

## Présentation à l'utilisateur

### Profil identifié avec confiance
Aucun affichage — le profil est résolu silencieusement et les droits sont appliqués.

### Profil incertain ou action bloquée
```
Avant de continuer, je dois confirmer votre identité pour cette action.
Pouvez-vous préciser votre nom et votre rôle ?
```

### Tentative d'accès non autorisée
```
Cette action n'est pas disponible pour votre profil.
Si vous pensez qu'il s'agit d'une erreur, contactez l'équipe InPressco.
```

---

## Exemples

### CLIENT (high)
```
Email depuis contact@clientexterne.fr — demande de devis 500 flyers
→ CLIENT (high) — domaine non InPressco, canal email, demande commerciale
→ Droits : lecture propres docs, pas d'écriture Dolibarr
→ Route vers inpressco-devis
```

### TEAM (high)
```
Email depuis production@inpressco.fr — "Archiver le BAT sur CMD-2026-112"
→ TEAM (high) — domaine @inpressco.fr
→ Droits : écriture Dolibarr, accès base images, workflow direct
```

### ADMIN (medium)
```
Interface interne — "Je suis Paola, je veux voir les marges sur les commandes de ce mois"
→ ADMIN (medium) — canal interne + déclaration nom dirigeant connu
→ Confirmation légère avant export données sensibles
```

### UNKNOWN → identification demandée
```
Message WhatsApp sans contexte — "Bonjour, où en est ma commande ?"
→ UNKNOWN (low) — aucun signal canal ou identité
→ Demander nom + référence commande avant toute consultation Dolibarr
```

---

## Notes importantes

- Ce skill ne bloque jamais une simple demande d'information générale (tarifs publics, délais standard) — le blocage s'applique uniquement aux données personnelles et aux actions d'écriture
- Le profil est réévalué à chaque session — pas de persistance automatique entre conversations (sauf si `memoire-client-inpressco` est actif et a déjà identifié le tiers)
- En cas de conflit entre signal canal et contenu → toujours prioriser le signal canal (un email @inpressco.fr reste TEAM même si le contenu ressemble à une demande client)
- Ce skill est appelé en amont par le routing engine — il ne se substitue pas aux skills métier, il les conditionne
