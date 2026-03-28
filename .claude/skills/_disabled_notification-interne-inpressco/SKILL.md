---
name: notification-interne-inpressco
description: >
  Skill d'alertes et notifications internes pour l'équipe In'Pressco. Déclencher SYSTÉMATIQUEMENT dès qu'une information doit être signalée à l'équipe en interne : nouvelle commande reçue, BAT validé par un client, impayé détecté, devis en attente depuis trop longtemps, erreur workflow, action urgente requise. Déclencher aussi dès que l'utilisateur dit "préviens l'équipe", "alerte Paola", "notifie Nicolas", "envoie un message à la prod", "préviens Mikaël", "informe Jean-Paul", "alerte Valérie", "notifie Chloé", "notifie en interne", "envoie un email à l'équipe". Ce skill identifie le bon destinataire selon l'événement, rédige le message approprié, l'envoie via l'API Dolibarr (email interne) et logue systématiquement l'action dans l'agenda Dolibarr pour traçabilité. WhatsApp non opérationnel — canaux actifs : email Dolibarr + agenda Dolibarr.
---

# Notification interne — In'Pressco

## Rôle
Alerter les bons membres de l'équipe, au bon moment, via le bon canal. Ne pas sur-notifier — chaque alerte doit déclencher une action précise. Toujours logger dans l'agenda Dolibarr pour traçabilité.

---

## Configuration API

```
BASE_URL : https://in-pressco.crm.freshprocess.eu/api/index.php
AUTH     : Header "DOLAPIKEY: {DOLIBARR_API_KEY}"
FORMAT   : JSON
```

---

## Équipe et routing

| Prénom | Rôle | Email | Reçoit |
|--------|------|-------|--------|
| Paola | ADV / Assistante commerciale | marketing@in-pressco.com | Briefs entrants, devis signés, relances, impayés, erreurs workflow |
| Chloé | ADV / Service client | service-client@in-pressco.com | Suivi commandes, questions clients, livraisons confirmées |
| Mikaël | Chef de production / Fabricant | fab@in-pressco.com | BAT validés/refusés, fichiers de production reçus, urgences fab |
| Valérie | Prepress / Studio | studio@in-pressco.com | Fichiers à préparer, corrections BAT, problèmes techniques fichiers |
| Jean-Paul | Responsable projet | jean-paul@in-pressco.com | Coordination projets, livrables, suivi client complexe |
| Nicolas | Direction commerce | nicolas@in-pressco.com | Devis stratégiques, prospects importants, bilan commercial |
| Alys | Direction commerce | alys@in-pressco.com | Devis stratégiques, prospects importants, bilan commercial |

---

## Routing automatique par type d'événement

### Alertes commerciales
| Événement | Destinataires | Urgence |
|-----------|--------------|---------|
| Nouveau brief / demande de devis entrant | Paola | Normale |
| Devis signé par client | Paola + Mikaël + Jean-Paul | Haute |
| Relance client sans réponse > 30j | Paola | Normale |
| Prospect inactif > 6 mois | Nicolas + Alys | Basse |
| Devis stratégique > 5 000 € HT | Nicolas + Alys + Paola | Haute |

### Alertes production
| Événement | Destinataires | Urgence |
|-----------|--------------|---------|
| BAT validé par client | Mikaël | Haute |
| BAT refusé — corrections demandées | Mikaël + Valérie + Paola | Haute |
| Fichier de production reçu | Valérie | Normale |
| Problème technique fichier (mauvaise résolution, PDF non conforme) | Valérie + Paola | Haute |
| Livraison confirmée (expédié) | Chloé + Paola | Normale |
| Retard de livraison détecté | Jean-Paul + Paola | Haute |

### Alertes financières
| Événement | Destinataires | Urgence |
|-----------|--------------|---------|
| Facture impayée > échéance | Paola | Normale |
| Impayé > 30j après échéance | Paola + Nicolas | Haute |
| Facture fournisseur à valider | Paola | Normale |

### Alertes système / workflow
| Événement | Destinataires | Urgence |
|-----------|--------------|---------|
| Erreur workflow (skill en échec) | Paola | Normale |
| Dolibarr inaccessible | Paola + Nicolas | Haute |
| Skill en échec répété (3×) | Paola | Normale |

---

## Étapes d'exécution

### Étape 1 — Identifier l'événement et les destinataires
Analyser le contexte (type d'événement, urgence, objet Dolibarr concerné) et sélectionner les destinataires dans la table de routing ci-dessus. En cas de doute, inclure Paola par défaut.

### Étape 2 — Rédiger le message email

Format strict :

```
Objet : [INPRESSCO] [TYPE] — [Résumé court en < 60 caractères]

[Contexte en 1-2 phrases claires]

Objet concerné : [REF Dolibarr si applicable — ex: DEV-2026-045]
Tiers : [Nom client ou fournisseur]
Action requise : [Ce qu'il faut faire concrètement, en 1 phrase]

Lien Dolibarr : https://in-pressco.crm.freshprocess.eu/[module]/[id]
```

Types valides : `COMMERCIAL` · `PRODUCTION` · `FINANCIER` · `SYSTÈME`

### Étape 3 — Envoyer l'email via Dolibarr

```
POST {BASE_URL}/emails
Headers: DOLAPIKEY: {DOLIBARR_API_KEY}
Content-Type: application/json

Body:
{
  "from": "noreply@in-pressco.com",
  "to": "[email destinataire]",
  "subject": "[Objet rédigé à l'étape 2]",
  "body": "[Corps du message rédigé à l'étape 2]",
  "ishtml": 0
}
```

Si plusieurs destinataires → un appel API par destinataire (ne pas grouper dans `to`).

**Gestion d'erreur email :**
- `200` → succès, passer à l'étape 4
- `401` / `403` → stopper, signaler l'erreur à l'utilisateur
- `500` → retry 1× après 3s, puis signaler

### Étape 4 — Logger dans l'agenda Dolibarr (systématique)

Toujours créer un événement agenda, même si l'email échoue :

```
POST {BASE_URL}/agendaevents
Headers: DOLAPIKEY: {DOLIBARR_API_KEY}
Content-Type: application/json

Body:
{
  "type_code": "AC_OTH_AUTO",
  "label": "Notification interne — [TYPE] : [Résumé court]",
  "note": "[Contenu complet : contexte, destinataires, action requise]",
  "datep": [timestamp Unix maintenant],
  "datep2": [timestamp Unix maintenant + 3600],
  "fulldayevent": 0,
  "done": 0,
  "socid": [socid du tiers si connu, sinon 0],
  "elementtype": "[propal | commande | facture | vide selon objet]",
  "fk_element": [id Dolibarr de l'objet si connu, sinon 0],
  "userownerid": 1
}
```

**Calcul timestamp Unix :** `Math.floor(Date.now() / 1000)`

---

## Sortie affichée à l'utilisateur

Après exécution réussie :

```
✅ Notification envoyée
─────────────────────────
Type      : [TYPE]
Événement : [description courte]
Envoyé à  : [Prénom1 <email>, Prénom2 <email>…]
Référence : [REF Dolibarr si applicable]
Tiers     : [Nom client si applicable]
Log agenda: créé ✅
```

En cas d'échec partiel :

```
⚠️ Notification partiellement envoyée
[Prénom] <email> : ✅ envoyé / ❌ échec
Agenda log : ✅ / ❌
Erreur : [message Dolibarr]
```

---

## Règles impératives

- **Toujours logger** dans l'agenda Dolibarr, même si l'email échoue
- **Jamais notifier un client externe** via ce skill — strictement interne
- **Regrouper** les notifications de même type dans la même session (éviter le spam)
- **Ne jamais inventer** une REF Dolibarr — n'inclure la référence que si elle est connue avec certitude
- **Urgence haute** → tous les destinataires listés dans la table de routing
- **Urgence normale** → destinataire principal uniquement + log agenda
- **WhatsApp non opérationnel** → ne pas mentionner ce canal
- **Données financières** (montants, impayés) → jamais partagées en dehors de l'équipe

---

## Exemples

### BAT validé par un client
Événement : BAT validé sur CMD-2026-045 (Agence Exemple)
- Destinataire : Mikaël (fab@in-pressco.com)
- Objet : `[INPRESSCO] PRODUCTION — BAT validé CMD-2026-045`
- Corps : `Le client Agence Exemple a validé le BAT de la commande CMD-2026-045. Action requise : démarrer la fabrication.`
- Log : `elementtype=commande`, `fk_element=[id]`

### Nouveau brief entrant
Événement : email reçu, prospect non trouvé dans Dolibarr
- Destinataire : Paola (marketing@in-pressco.com)
- Objet : `[INPRESSCO] COMMERCIAL — Nouveau brief entrant : [Nom/email]`
- Corps : `Nouveau brief reçu de [expéditeur]. Aucune fiche tiers dans Dolibarr. Action requise : qualifier et créer la fiche.`
- Log : `socid=0`, `fk_element=0`

### Impayé > 30 jours
Événement : FA-2026-012, Dupont SARL, +35j après échéance
- Destinataires : Paola + Nicolas
- Objet : `[INPRESSCO] FINANCIER — Impayé 35j FA-2026-012`
- Corps : `La facture FA-2026-012 (Dupont SARL) est impayée depuis 35 jours. Action requise : relance téléphonique urgente.`
- Log : `elementtype=facture`, `fk_element=[id]`

### Déclenchement automatique par un autre skill
Ce skill est souvent appelé par archiveur, chat-to-db, gestion-erreurs, suivi-commande.
→ Récupérer le contexte passé (REF, socid, elementtype, fk_element) et exécuter les étapes 1 à 4 sans interaction utilisateur.
→ Afficher le résumé uniquement si une erreur survient.

---

## Notes importantes
- Quand déclenché automatiquement, ne pas afficher de confirmation sauf erreur
- Il signale — l'équipe décide. Ne pas prendre de décisions à la place de l'équipe.
- Appelé en bout de chaîne de la plupart des workflows In'Pressco
