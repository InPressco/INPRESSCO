---
name: suivi-commande-inpressco
description: >
  Skill de suivi et communication du statut des commandes pour In'Pressco — imprimeur-façonnier. Déclencher SYSTÉMATIQUEMENT dès qu'une commande est mentionnée dans un contexte de production, suivi, mise à jour ou relance : "où en est la commande", "la production a avancé ?", "quand est-ce que ce sera livré", "le BAT a été validé", "on a reçu les fichiers", "la commande est partie", "le client a reçu sa livraison", "il n'a pas répondu au BAT", "on est en retard sur", "mets à jour le statut", "quel est l'état de", "aucune nouvelle du client", "la commande est en attente depuis". Déclencher aussi en proactif dès qu'un email entrant mentionne une référence de commande ou un statut de production. Ce skill interroge Dolibarr pour l'état réel, met à jour le statut si un événement est signalé, logue l'historique en agenda, détecte les retards et blocages, génère les alertes internes, et prépare la communication client adaptée via le skill reponse-client.
---

# Suivi commande — In'Pressco

## Rôle
Centraliser le suivi des commandes en production : lire le statut réel dans Dolibarr, enregistrer chaque événement de production, détecter les blocages et retards, alerter l'équipe au bon moment, et déclencher la communication client adaptée.

> ⚠️ Ne jamais supposer un statut. Toujours interroger Dolibarr avant de répondre.

---

## Référentiel des statuts InPressco

La combinaison **type de document + statut Dolibarr + sous-statut** donne le sens métier exact. C'est la source de vérité — ne jamais interpréter autrement.

---

### DEVIS

| Statut Dolibarr | Sous-statut | Signification InPressco | Libellé affiché |
|-----------------|-------------|------------------------|-----------------|
| `0` Brouillon | — | Devis en cours de rédaction, non envoyé | **À l'étude** |
| `1` Validé | — | Devis finalisé et envoyé au client | **Devis envoyé** |
| `2` Accepté | — | Client a accepté le devis | **Devis accepté** |
| `3` Refusé | — | Client a refusé le devis | **Devis refusé** |
| `-1` Annulé | — | Devis annulé | **Annulé** |

---

### COMMANDE

| Statut Dolibarr | Sous-statut Dolibarr | Signification InPressco | Libellé affiché |
|-----------------|---------------------|------------------------|-----------------|
| `0` Brouillon | — | Commande créée, fichiers client non encore reçus | **En attente de fichiers** |
| `1` Validée | rien / vide | Commande reçue, fichiers en cours de traitement — BAT en préparation | **Fichiers en traitement** |
| `1` Validée | `traité` | BAT préparé et envoyé au client — en attente de validation | **BAT envoyé — attente retour** |
| `1` Validée | `approuvé` | BAT validé par le client — lancé en production (impression + façonnage) | **En production** |
| `2` En cours | — | Production terminée — préparation et conditionnement du colis | **Préparation colis** |
| `3` Livré | — | Commande expédiée — partie de chez InPressco | **Parti de chez nous** |
| `-1` Annulée | — | Commande annulée — alerter l'équipe immédiatement | **Annulée** |

> Le sous-statut Dolibarr est le champ `availability` ou tag interne selon la configuration. À vérifier via `GET /orders/{id}` → champ `availability` ou `note_private` selon setup.

---

### Lecture combinée — algorithme de décodage

```
Pour toute commande, lire dans l'ordre :

1. type = "commande" ou "devis" ?
   GET /orders/{id} ou GET /proposals/{id}

2. statut = champ "statut" de l'objet

3. Pour les commandes statut=1 uniquement :
   lire le sous-statut (champ availability ou dernier agenda event)
   -> vide/rien   = "Fichiers en traitement"
   -> "traité"    = "BAT envoyé — attente retour"
   -> "approuvé"  = "En production"

4. Croiser avec tableau ci-dessus pour obtenir le libellé InPressco exact
```

---

### Transitions de statut — quand et comment mettre à jour

| Événement terrain | Type doc | Avant | Après | Action API |
|-------------------|----------|-------|-------|------------|
| Devis rédigé | Devis | — | Brouillon `0` | Création |
| Devis envoyé au client | Devis | `0` | Validé `1` | PUT statut=1 |
| Client accepte le devis | Devis | `1` | Accepté `2` → créer commande | PUT statut=2 + POST /orders |
| BC reçu, fichiers attendus | Commande | — | Brouillon `0` | Création |
| Fichiers reçus, BAT en cours | Commande | `0` | Validée `1` + sous-statut vide | PUT statut=1 |
| BAT envoyé au client | Commande | `1` vide | `1` + sous-statut `traité` | PUT availability=traité + logger agenda |
| Client valide le BAT | Commande | `1` traité | `1` + sous-statut `approuvé` | PUT availability=approuvé + notifier Nicolas |
| Client refuse le BAT | Commande | `1` traité | `1` + sous-statut vide (retour préparation) | PUT availability=vide + logger refus + incrémenter version BAT |
| Production terminée, colis en préparation | Commande | `1` approuvé | En cours `2` | PUT statut=2 |
| Commande expédiée | Commande | `2` | Livré `3` | PUT statut=3 + email client |

---

## Processus — Consultation statut (lecture)

```
1. Chercher la commande :
   GET /orders?ref={ref}   <- par référence
   GET /orders?socid={id}  <- toutes les commandes d'un client

2. Lire le statut et les données clés :
   GET /orders/{id}
   -> statut, date_commande, date_livraison_prevue, note_private

3. Récupérer l'historique des jalons :
   GET /agendaevents?elementtype=commande&fk_element={id}&sortfield=datep&sortorder=ASC

4. Vérifier les documents liés :
   GET /documents?modulepart=commande&id={id}
   -> BAT en PJ ? Version BAT courante ?

5. Synthétiser et présenter (voir section Présentation)
```

---

## Processus — Mise à jour de statut (écriture)

```
1. Identifier le jalon depuis la conversation (ou l'email)

2. Logger le jalon en agenda Dolibarr :
   POST /agendaevents
   {
     "type_code": "AC_OTH_AUTO",
     "label": "[JALON] — {description courte}",
     "datep": "{date_iso}",
     "elementtype": "commande",
     "fk_element": {id_commande},
     "note": "{details : version BAT, transporteur, n° suivi...}"
   }

3. Si jalon = EXPÉDIÉE -> PUT /orders/{id} avec statut=2
   Si jalon = ANNULÉE  -> PUT /orders/{id} avec statut=-1
   Autres jalons -> note_private uniquement (Dolibarr ne supporte pas plus de statuts natifs)

4. Déclencher les actions associées au jalon (voir tableau jalons)
```

---

## Gestion du cycle BAT

Le BAT est le point de blocage le plus fréquent chez InPressco. Traiter avec attention.

```
BAT_ENVOYÉ :
  -> Logger date d'envoi
  -> Créer un rappel agenda à J+2 ouvrés : "Relance BAT si pas de retour"
  -> Archiver le fichier BAT (version N) via skill archiveur

BAT_VALIDÉ :
  -> Logger + notifier Nicolas
  -> Mettre à jour note_private : "BAT v{N} validé le {date}"
  -> Lancer jalon EN_IMPRESSION

BAT_REFUSÉ :
  -> Logger + notifier équipe (Paola + Nicolas)
  -> Demander à l'utilisateur le détail des corrections
  -> Incrémenter le numéro de version BAT
  -> Préparer message client via skill reponse-client (ton neutre, demander précisions)

BAT_SANS_RÉPONSE (> 3 jours ouvrés) :
  -> Alerte via notification-interne-inpressco
  -> Proposer relance client via skill reponse-client
  -> Logger la tentative de relance
```

---

## Alertes automatiques

Générer une alerte via `notification-interne-inpressco` dans ces cas :

| Situation (statut bloqué) | Niveau | Destinataire | Délai déclencheur |
|---------------------------|--------|-------------|-------------------|
| Commande `0` (en attente fichiers) sans évolution | Modéré | Paola | > 3j ouvrés après création |
| Commande `1` sous-statut vide — pas de BAT envoyé | Modéré | Paola | > 5j sans passage à `traité` |
| Commande `1` sous-statut `traité` — pas de retour BAT | Modéré | Paola | > 3j ouvrés sans réponse |
| Commande `1` sous-statut `traité` — 2ème BAT refusé | Modéré | Paola | Immédiat |
| Commande `2` (prépa colis) bloquée | Critique | Paola + Nicolas | > 1j |
| Date livraison prévue dépassée — statut pas encore `3` | Critique | Paola + Nicolas | Jour J+1 |
| Annulation détectée (statut `-1`) | Critique | Toute l'équipe | Immédiat |

---

## Communication client par jalon

| Jalon | Via skill reponse-client | Contenu clé |
|-------|--------------------------|------------|
| `BAT_ENVOYÉ` | Oui — email avec BAT en PJ | Délai de réponse attendu, instructions validation |
| `EXPÉDIÉE` | Oui — email confirmation | Transporteur + n° de suivi si disponible |
| `LIVRÉE` | Oui si non déjà envoyé | Confirmation + proposition satisfaction |
| `BAT_REFUSÉ` | Non — communication interne seulement | — |
| `BAT_SANS_RÉPONSE` | Oui — relance douce | Rappel + contact direct Paola si urgence |

> Tous les emails client passent obligatoirement par reponse-client-inpressco — ne jamais rédiger un email client en dehors de ce skill.

---

## Transition livraison vers facturation

Dès que le jalon LIVRÉE est enregistré :

```
1. Vérifier si une facture est déjà émise :
   GET /invoices?socid={id}&status=1  <- factures validées liées à ce tiers

2. Si aucune facture trouvée pour cette commande :
   -> Proposer à l'utilisateur : "La livraison est confirmée. Voulez-vous que je génère la facture ?"
   -> Si oui : déclencher skill generation-pdf-inpressco avec les données de la commande

3. Logger la proposition en agenda : "Facturation proposée le {date}"
```

---

## Présentation à l'utilisateur

### Vue statut interne (équipe)
```
CMD-2026-045 — Agence Exemple SARL
Catalogue A5 24p · 1 000 ex · Couché mat 135g · Livraison prévue : 28/03

Statut Dolibarr : Validée (1) · Sous-statut : traité
Libellé InPressco : BAT envoyé — attente retour
Depuis le : 20/03 · Aucune réponse depuis 6 jours ouvrés — relance recommandée

Historique :
-> 10/03  Commande créée (brouillon) — en attente de fichiers
-> 11/03  Fichiers reçus — commande validée, BAT en traitement
-> 20/03  BAT v1 envoyé (sous-statut → traité)

Actions disponibles :
[Relancer le client]  [Marquer BAT validé → approuvé]  [Marquer BAT refusé → retour traitement]  [Voir PJ]
```

### Vue multi-commandes (client avec plusieurs commandes en cours)
```
Commandes en cours — Agence Exemple SARL

1. CMD-2026-045 · Catalogue A5      · BAT envoyé — attente retour (6j)   [Validée / traité]
2. CMD-2026-038 · Flyers             · En production                       [Validée / approuvé]
3. CMD-2026-031 · Cartes de visite   · Préparation colis                   [En cours]
4. CMD-2026-022 · Plaquette          · Parti de chez nous · 25/03          [Livré]

[Détailler une commande]
```

### Réponse client (générée via skill reponse-client)
```
Bonjour Marie,

Votre commande CMD-2026-045 est actuellement en cours de production.
La livraison est prévue pour le 28 mars.

[Phrase Paola]
```

---

## Schéma JSON interne (passage entre skills)

```json
{
  "commande": {
    "id": 145,
    "ref": "CMD-2026-045",
    "tiers": "Agence Exemple SARL",
    "tiers_id": 82,
    "statut_dolibarr": 1,
    "statut_dolibarr_label": "Validée",
    "sous_statut": "traité",
    "libelle_inpressco": "BAT envoyé — attente retour",
    "depuis": "2026-03-20",
    "produit": "Catalogue A5 24p · 1 000 ex · Couché mat 135g",
    "date_commande": "2026-03-10",
    "date_livraison_prevue": "2026-03-28",
    "jours_restants": -1,
    "en_retard": true
  },
  "transition_suivante": {
    "si_bat_valide": "PUT availability=approuvé → libellé = En production",
    "si_bat_refuse": "PUT availability=vide → libellé = Fichiers en traitement (BAT v2)"
  },
  "date_dernier_jalon": "2026-03-20",
  "historique": [
    "10/03 — Commande reçue et validée",
    "12/03 — Fichiers de production reçus",
    "20/03 — BAT v1 envoyé au client"
  ],
  "alerte": {
    "type": "BAT_EN_ATTENTE",
    "niveau": "modere",
    "message": "BAT v1 envoyé le 20/03 — aucune réponse depuis 6 jours ouvrés",
    "action_recommandee": "relancer_client"
  },
  "facturation": {
    "facture_emise": false,
    "proposer_facturation": false
  },
  "actions_disponibles": [
    "relancer_client",
    "marquer_bat_valide",
    "marquer_bat_refuse",
    "mettre_a_jour_statut",
    "voir_documents"
  ]
}
```

---

## Règles importantes

- **Toujours vérifier dans Dolibarr** avant de répondre — ne jamais supposer un statut.
- **Logger systématiquement** chaque jalon en agenda Dolibarr — c'est la traçabilité du dossier.
- **Profil CLIENT** — lecture de ses propres commandes uniquement, sans accès aux notes internes ni aux prix de revient.
- **Profil ÉQUIPE** — accès complet, mise à jour possible.
- **En cas de doute sur un jalon**, demander confirmation à l'utilisateur avant de logger.
- **BAT = priorité absolue** — tout BAT sans réponse depuis plus de 3 jours ouvrés doit générer une alerte.
