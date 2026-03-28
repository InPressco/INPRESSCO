---
name: agenda-inpressco
description: >
  Skill de gestion de l'agenda et de la planification pour In'Pressco. Déclencher SYSTÉMATIQUEMENT dès qu'un RDV, une relance, un rappel ou une échéance doit être créé, consulté, modifié ou synchronisé : "fixe un RDV avec ce client", "rappelle-moi de relancer le devis dans 5 jours", "quels sont les RDV de la semaine", "planifie une relance BAT pour jeudi", "ajoute une note d'échéance sur cette commande", "mets dans le calendrier Outlook", "planifie une réunion pour l'équipe", "ajoute au planning de Paola", "événement sans assignation", "bloc de production toute la journée", "ajoute dans Teams". Ce skill crée et synchronise les événements agenda dans Dolibarr ET dans Outlook 365 (Microsoft Graph API), avec ou sans assignation à un membre de l'équipe. Il gère la création, la mise à jour, la suppression et la consultation des événements dans les deux systèmes simultanément.
---

# Agenda / Planning — In'Pressco
## Dual-sync Dolibarr ↔ Outlook 365

## Rôle
Créer, consulter et synchroniser les événements agenda dans **Dolibarr** et **Outlook 365 / Microsoft 365** — RDV clients, relances, rappels, jalons de production, événements d'équipe. Un événement créé ici peut être poussé dans les deux systèmes simultanément.

---

## Décision de synchronisation

Pour chaque événement, appliquer la règle suivante :

| Contexte | Dolibarr | Outlook 365 |
|----------|----------|-------------|
| Relance / log interne lié à un document | ✅ | ❌ |
| RDV client avec contact externe | ✅ | ✅ |
| Réunion équipe (avec/sans assignation) | ✅ | ✅ |
| Bloc de production / jalons | ✅ | ✅ optionnel |
| Rappel personnel utilisateur | ❌ | ✅ |
| Demande explicite "mets dans Outlook" | ✅ | ✅ |

→ **Par défaut : toujours créer dans Dolibarr**. Ajouter Outlook si RDV, réunion, ou si l'utilisateur le demande.

---

## Types d'événements Dolibarr

| Type | Code Dolibarr | Usage |
|------|--------------|-------|
| RDV client | `RDV` | Rendez-vous physique ou téléphonique |
| Relance | `AC_OTH_AUTO` | Relance devis, BAT, impayé |
| Rappel interne | `AC_OTH_AUTO` | Todo équipe, action à planifier |
| Échange loggué | `AC_MAILRECEIVED` | Email reçu, appel, échange noté |
| Action réalisée | `AC_OTH_AUTO` | Validation, livraison, décision |
| Échéance | `AC_OTH_AUTO` | Date limite livraison, paiement |

---

## Référentiel équipe InPressco

| Prénom | ID Dolibarr (usertodo) | Email Outlook | Calendrier partagé |
|--------|------------------------|---------------|--------------------|
| Paola | 1 | paola@inpressco.fr | Oui |
| _(ajouter membres)_ | — | — | — |
| _(non assigné)_ | null | — | calendrier général |

> **Événement non assigné** : usertodo = null (Dolibarr) → calendrier partagé général (Outlook).

---

## PARTIE 1 — Dolibarr

### Création d'un événement

```
POST /agendaevents
```

Champs du payload :

```
type_code     : RDV | AC_OTH_AUTO | AC_MAILRECEIVED
label         : Titre court (obligatoire)
note          : Description détaillée (facultatif)
datep         : Timestamp Unix début (Europe/Paris)
datep2        : Timestamp Unix fin (si applicable)
fulldayevent  : 0 = horaire précis · 1 = journée entière
socid         : ID tiers lié (facultatif)
elementtype   : propal | commande | facture | vide si général
fk_element    : ID du document lié (facultatif)
userownerid   : 166 (utilisateur système InPressco — toujours)
usertodo      : ID collaborateur assigné | null si non assigné
done          : 0 = à faire · 1 = réalisé
```

### Exemples

**RDV client assigné à Paola**
```json
{
  "type_code": "RDV",
  "label": "RDV téléphonique — Agence Exemple",
  "note": "Discussion projet catalogue printemps. Contact : Marie Dupont",
  "datep": 1743084000,
  "datep2": 1743087600,
  "fulldayevent": 0,
  "socid": 42,
  "userownerid": 166,
  "usertodo": 1,
  "done": 0
}
```

**Bloc de production non assigné (journée entière)**
```json
{
  "type_code": "AC_OTH_AUTO",
  "label": "Production BAT — CMD-2026-112",
  "note": "Fabrication en cours — ne pas planifier livraisons ce jour",
  "datep": 1743516000,
  "fulldayevent": 1,
  "elementtype": "commande",
  "fk_element": 112,
  "userownerid": 166,
  "usertodo": null,
  "done": 0
}
```

**Relance devis (Dolibarr uniquement)**
```json
{
  "type_code": "AC_OTH_AUTO",
  "label": "Relance DEV-2026-089 — sans réponse depuis 7j",
  "note": "Devis envoyé le 19/03 — relancer par email ou téléphone",
  "datep": 1743343200,
  "fulldayevent": 1,
  "socid": 42,
  "elementtype": "propal",
  "fk_element": 142,
  "userownerid": 166,
  "usertodo": null,
  "done": 0
}
```

### Mise à jour et suppression

```
PUT    /agendaevents/{id}   → mettre à jour (même payload, champs modifiés)
DELETE /agendaevents/{id}   → supprimer
```

Pour marquer réalisé : PUT avec done=1

### Consultation

```
Agenda du jour
→ GET /agendaevents?datestart={debut_jour}&dateend={fin_jour}

Agenda de la semaine
→ GET /agendaevents?datestart={lundi}&dateend={dimanche}

Événements d'un tiers
→ GET /agendaevents?thirdparty_ids={socid}&limit=50

Événements d'un document
→ GET /agendaevents?elementtype=propal&fk_element={id}

Événements d'un collaborateur
→ GET /agendaevents?usertodo={user_id}&done=0

Événements non assignés
→ GET /agendaevents?usertodo=0&done=0

Relances en attente
→ GET /agendaevents?done=0&dateend={now}
```

---

## PARTIE 2 — Outlook 365 (Microsoft Graph API)

### Authentification

Utiliser le token OAuth2 Microsoft Graph disponible dans la configuration InPressco.

```
Base URL : https://graph.microsoft.com/v1.0
Scope    : Calendars.ReadWrite
```

### Sélection du calendrier cible

```
Collaborateur assigné (ex: Paola)
→ POST /users/paola@inpressco.fr/events

Calendrier partagé général (non assigné)
→ POST /groups/{group_id}/calendar/events
  OU /users/calendrier-general@inpressco.fr/events
```

### Création d'un événement Outlook

```json
{
  "subject": "RDV téléphonique — Agence Exemple",
  "body": {
    "contentType": "HTML",
    "content": "Discussion projet catalogue printemps.<br/>Ref Dolibarr : agendaevent#456"
  },
  "start": {
    "dateTime": "2026-04-03T14:00:00",
    "timeZone": "Romance Standard Time"
  },
  "end": {
    "dateTime": "2026-04-03T15:00:00",
    "timeZone": "Romance Standard Time"
  },
  "isAllDay": false,
  "attendees": [
    {
      "emailAddress": { "address": "client@exemple.fr", "name": "Contact Client" },
      "type": "required"
    }
  ],
  "location": {
    "displayName": "Téléphonique / Atelier In'Pressco"
  },
  "categories": ["InPressco", "RDV Client"],
  "isReminderOn": true,
  "reminderMinutesBeforeStart": 15
}
```

**Événement journée entière (isAllDay=true) :**
- start.dateTime = "2026-04-03T00:00:00"
- end.dateTime   = "2026-04-04T00:00:00" (J+1 obligatoire pour Outlook)

### Mise à jour et suppression Outlook

```
PATCH  /users/{email}/events/{event_id}   → mise à jour partielle
DELETE /users/{email}/events/{event_id}   → suppression
```

### Catégories Outlook recommandées

| Catégorie | Usage |
|-----------|-------|
| InPressco | Tag général — toujours présent |
| RDV Client | Rendez-vous avec tiers externe |
| Production | Jalons de fabrication |
| Relance | Relances commerciales |
| Réunion Équipe | Meetings internes |
| Échéance | Dates limites |

---

## PARTIE 3 — Processus de création combiné

### Étape 1 — Comprendre la demande

```
"RDV jeudi 14h avec Agence Exemple pour Paola"
→ Dolibarr : type=RDV, usertodo=1, socid=Agence Exemple
→ Outlook   : /users/paola@inpressco.fr/events, 14h–15h

"Bloc production CMD-2026-112 lundi toute la journée"
→ Dolibarr : type=AC_OTH_AUTO, usertodo=null, fulldayevent=1
→ Outlook   : calendrier général, isAllDay=true, catégorie=Production

"Relance DEV-2026-089 dans 5 jours"
→ Dolibarr uniquement (log interne, pas de sync Outlook)
```

### Étape 2 — Résoudre les entités
- Tiers → `dolibarr-query-inpressco` pour le socid
- Document → `dolibarr-query-inpressco` pour l'id et la référence
- Collaborateur → référentiel équipe (table ci-dessus)
- Date → timestamp Unix pour Dolibarr · ISO 8601 pour Outlook (timezone Europe/Paris = Romance Standard Time)

### Étape 3 — Créer dans Dolibarr
```
POST /agendaevents → noter l'ID retourné (ex: 456)
```

### Étape 4 — Créer dans Outlook si applicable
```
POST vers le bon calendrier
→ Inclure "Ref Dolibarr : agendaevent#456" dans le body
→ Noter l'ID Outlook retourné (ex: AAMkAD...)
```

### Étape 5 — Confirmer à l'utilisateur
Afficher le récapitulatif avec les deux IDs si sync double.

---

## Détection automatique de relances à planifier

| Situation | Délai | Sync Outlook |
|-----------|-------|-------------|
| Devis envoyé sans réponse | +7 jours | ❌ |
| BAT envoyé sans réponse | +5 jours ouvrés | ❌ |
| Facture non payée | +3 jours après échéance | ❌ |
| Brief reçu sans suite | +3 jours | ❌ |
| RDV passé sans CR | +1 jour | ✅ |

---

## Schéma JSON de sortie

```json
{
  "evenement": {
    "type": "RDV | relance | rappel | bloc | log",
    "label": "RDV Agence Exemple",
    "date": "2026-04-03",
    "heure": "14h00–15h00",
    "tiers": "Agence Exemple SARL",
    "document": null,
    "assigne_a": "Paola",
    "dolibarr": { "id": 456, "statut": "créé" },
    "outlook": {
      "id": "AAMkAD...",
      "calendrier": "paola@inpressco.fr",
      "statut": "créé"
    }
  }
}
```

---

## Présentation à l'utilisateur

### Création réussie (double sync)
```
✓ Événement créé dans Dolibarr et Outlook 365

RDV téléphonique — Agence Exemple
Date    : Jeudi 3 avril 2026 · 14h00–15h00
Assigné : Paola
Outlook : calendrier Paola · rappel 15 min avant
Dolibarr: #456 lié au tiers Agence Exemple SARL
```

### Création Dolibarr seul (relance interne)
```
✓ Relance planifiée dans l'agenda Dolibarr

Relance : DEV-2026-089 — Agence Exemple
Date    : Mercredi 2 avril 2026 (journée)
Note    : Devis sans réponse depuis 7 jours
```

### Vue agenda du jour
```
Agenda du jeudi 3 avril 2026 :

09h00 — RDV téléphonique Dupont SARL [Paola] 📅 Outlook
         → Discussion brief packaging automne

Journée — Production BAT CMD-2026-112 [non assigné] 📅 Outlook
         → Fabrication en cours

Journée — ⚠ Relance : DEV-2026-089 (sans réponse 7j) [Dolibarr]
```

---

## Gestion des erreurs

| Erreur | Action |
|--------|--------|
| Dolibarr KO | Créer dans Outlook seul · alerter via notification-interne-inpressco |
| Outlook KO / token expiré | Créer dans Dolibarr seul · informer l'utilisateur · proposer retry |
| Les deux KO | Logger · alerter équipe |
| Collision agenda détectée | Signaler · proposer créneaux alternatifs |

---

## Notes importantes

- Dates : **Europe/Paris** → Dolibarr: timestamp Unix · Outlook: "Romance Standard Time"
- Chaque événement Dolibarr référence l'ID Outlook dans sa `note` si sync double
- Chaque événement Outlook inclut `Ref Dolibarr : agendaevent#ID` dans son body
- `usertodo = null` = événement général non assigné, visible par toute l'équipe dans Dolibarr
- Les skills `suivi-commande` et `reponse-client` utilisent ce skill pour logger les actions importantes
- Les relances planifiées déclenchent `notification-interne-inpressco` à la date prévue
- Profil CLIENT → aucun accès à l'agenda (données internes)
- Avant de fixer un RDV, consulter l'agenda du collaborateur pour vérifier la disponibilité
