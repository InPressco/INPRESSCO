---
name: gestion-erreurs-inpressco
description: >
  Skill de détection, gestion et reprise des erreurs de workflow pour In'Pressco — imprimeur-façonnier. Déclencher SYSTÉMATIQUEMENT dès qu'un workflow échoue, qu'une action Dolibarr retourne une erreur, qu'une API est inaccessible, qu'un skill ne produit pas le résultat attendu, ou que des données risquent d'être perdues. Déclencher aussi automatiquement en arrière-plan lorsqu'un autre skill rencontre un obstacle, sans attendre que l'utilisateur le signale. Triggers explicites : "ça n'a pas marché", "le devis n'a pas été créé", "Dolibarr ne répond pas", "l'archivage a échoué", "erreur", "ça plante", "ça bug", "je n'arrive pas à", "ça ne s'est pas enregistré", "le fichier ne s'est pas déposé", "l'email n'est pas parti". Ce skill diagnostique l'erreur, évalue l'impact client, préserve les données en attente, propose une reprise ou un contournement, alerte l'équipe si nécessaire, et logue l'incident pour traçabilité. Ne jamais laisser une erreur silencieuse quand des données client ou une commande en cours sont impliquées.
---

# Gestion erreurs — In'Pressco

## Rôle
Intercepter, diagnostiquer et traiter les erreurs survenant dans les workflows et skills InPressco. Protéger les données client, éviter les pertes de commandes, et garantir la continuité de service même en cas de dysfonctionnement technique. Ce skill est le filet de sécurité de tous les autres.

---

## Priorité d'urgence — évaluer d'abord l'impact client

Avant toute décision technique, classer l'erreur selon son impact :

| Niveau | Situation | Réponse |
|--------|-----------|---------|
| 🔴 CRITIQUE | Commande urgente bloquée, client en attente d'un BAT, livraison compromise | Alerte immédiate équipe + mode dégradé + traitement manuel |
| 🟠 ÉLEVÉ | Devis non créé après échange client, email de réponse non envoyé | Retry + notification équipe si échec |
| 🟡 MODÉRÉ | Archivage échoué, log manquant, doublon détecté | Correction différée, pas d'alerte temps réel |
| 🟢 FAIBLE | Erreur silencieuse résolue automatiquement | Logger, aucune notification |

---

## Catégories d'erreurs

### Erreurs API Dolibarr

| Code | Cause probable | Stratégie |
|------|---------------|-----------|
| 401 | Clé API expirée ou invalide | Bloquer toute écriture → alerter admin → mode dégradé |
| 403 | Droits insuffisants | Vérifier profil via droits-profils-inpressco, escalader si légitime — ne jamais contourner |
| 404 | Référence ou objet introuvable | Rechercher par autre critère (nom, email) avant d'abandonner |
| 409 | Conflit — objet déjà existant | Vérifier doublon → proposer de lier à l'existant |
| 422 | Données invalides envoyées | Identifier le champ manquant → corriger → relancer |
| 500 | Erreur serveur Dolibarr | Retry 1x après 5s → si échec : alerter équipe |
| 503 | Dolibarr hors ligne | Mode dégradé immédiat → file d'attente → notification équipe |
| Timeout | Serveur lent ou inaccessible | Retry 1x après 10s → si échec : mode dégradé |

### Erreurs de workflow métier In'Pressco

| Erreur | Cause probable | Reprise |
|--------|---------------|---------|
| Tiers non résolu | Email/nom non trouvé dans Dolibarr | Proposer création via chat-to-db-inpressco |
| Devis non créé | Payload incomplet, statut invalide | Identifier le champ manquant, compléter et réessayer |
| BAT non déposé sur commande | Format refusé, taille trop grande | Vérifier le fichier, proposer alternative (lien externe) |
| Email client non envoyé | SMTP en erreur, adresse invalide | Préparer le mail pour copier-coller manuel |
| Calcul tarifaire impossible | Données produit manquantes | Demander les infos manquantes à l'utilisateur |
| Archivage échoué | Chemin invalide, PJ refusée | Sauvegarder via projets-artefacts-inpressco en attente |
| Skill en échec | Données d'entrée insuffisantes | Identifier ce qui manque, demander à l'utilisateur |

### Erreurs de données

| Erreur | Cause | Reprise |
|--------|-------|---------|
| Doublon tiers détecté | Client déjà existant sous autre nom | Proposer de lier, fusionner ou ignorer |
| Champ obligatoire manquant | Données incomplètes (ref commande, contact) | Demander le champ avant de continuer |
| Format invalide | Date, référence, email malformé | Corriger automatiquement si possible, sinon signaler |
| Incohérence devis/brief | Montant 0, quantité aberrante, date passée | Bloquer → appeler validation-qc-inpressco |
| Données perdues suspectées | Action non confirmée, réponse API vide | Vérifier via dolibarr-query-inpressco avant toute reprise |

---

## Mode dégradé (Dolibarr inaccessible)

Déclencher automatiquement si Dolibarr répond 503 ou timeout après retry.

ACTIONS SUSPENDUES en mode dégradé :
→ Aucune création / modification Dolibarr
→ Aucun dépôt de document
→ Aucune mise à jour de statut
→ Aucun envoi automatique d'email

ACTIONS MAINTENUES :
→ Rédaction de devis (sauvegardé via projets-artefacts-inpressco)
→ Réponses clients (sans accès à l'historique Dolibarr)
→ Calculs tarifaires
→ Archivage temporaire en file d'attente

FILE D'ATTENTE :
→ Chaque action en attente sauvegardée avec timestamp et contexte complet
→ Reprise automatique proposée dès retour Dolibarr
→ Notification équipe immédiate (WhatsApp si commande urgente)

---

## Processus de gestion d'erreur — 7 étapes

### Étape 1 — Capturer l'erreur
Source possible :
→ Code HTTP + message d'erreur API Dolibarr
→ Description de l'échec d'un skill
→ Signal utilisateur ("ça n'a pas marché", "je n'arrive pas à...")
→ Résultat vide ou inattendu d'une action

### Étape 2 — Évaluer l'impact client
- Y a-t-il un client en attente d'une réponse ou d'un BAT ?
- Une commande en cours est-elle bloquée ?
- Des données risquent-elles d'être perdues définitivement ?
→ Classer selon le tableau de priorité ci-dessus.

### Étape 3 — Diagnostiquer
- Quelle action a échoué ? À quelle étape du workflow ?
- Les données sont-elles préservées ou perdues ?
- L'erreur est-elle transitoire (timeout, 500) ou permanente (401, 403) ?

### Étape 4 — Décider de la stratégie
Erreur transitoire    → Retry automatique (1x) → si échec : alerter
Erreur de données     → Corriger et relancer
Erreur système        → Alerter équipe, mode dégradé si nécessaire
Erreur droits (403)   → Escalader — ne jamais contourner
Données en attente    → Sauvegarder via projets-artefacts-inpressco

### Étape 5 — Exécuter la reprise
Tenter la reprise selon la stratégie. Si échec après retry → escalader immédiatement. Ne jamais faire plus d'1 retry automatique.

### Étape 6 — Logger l'incident
Toujours créer un log, même si l'erreur est résolue :
```json
{
  "incident": {
    "date": "{timestamp}",
    "skill": "nom_du_skill",
    "action": "description_action_échouée",
    "erreur": "code + message",
    "impact_client": "critique | élevé | modéré | faible",
    "statut": "résolu | en_attente | escaladé",
    "reprise": "description de ce qui a été fait",
    "données_préservées": true
  }
}
```

### Étape 7 — Notifier si nécessaire
- Erreur résolue silencieusement → pas de notification
- Erreur nécessitant action équipe → notification-interne-inpressco
- Erreur bloquante critique (commande urgente, client en attente) → alerte WhatsApp immédiate via notification-interne-inpressco

---

## Messages à l'utilisateur

### Erreur résolue automatiquement
⚠ Erreur détectée lors de la création du devis (serveur Dolibarr).
✓ Résolu automatiquement après nouvelle tentative.
Le devis DEV-2026-089 a bien été créé.

### Erreur nécessitant action
🚫 Échec — Impossible de déposer le fichier sur Dolibarr

Cause : Clé API invalide (erreur 401)
Impact : Aucun client en attente — traitement différé possible
Données : Fichier préservé localement, en file d'attente

Action requise : Renouveler la clé API Dolibarr (admin).
L'équipe a été notifiée.

### Erreur critique — commande urgente bloquée
🔴 ALERTE — Workflow bloqué sur une commande en cours

Cause : Dolibarr inaccessible (timeout)
Commande concernée : CMD-2026-042 (livraison J+1)

Mode dégradé activé. Paola a été alertée immédiatement.
Les actions en attente sont préservées et seront reprises dès le retour de Dolibarr.

Je peux encore vous aider à préparer les documents pour dépôt manuel.

### Mode dégradé activé (impact faible)
⚠ Dolibarr est momentanément inaccessible.
Mode dégradé activé — les créations Dolibarr sont suspendues.

Ce que je peux faire maintenant :
→ Rédiger des devis et emails (sauvegarde locale)
→ Calculer des tarifs
→ Préparer des documents pour dépôt ultérieur

Les actions en attente seront reprises dès le retour de Dolibarr.

---

## Règles absolues

- Ce skill ne contourne JAMAIS une erreur 403 — une action refusée pour droits insuffisants ne doit pas être tentée autrement
- Les données en attente lors d'un mode dégradé sont TOUJOURS préservées — sauvegarder via projets-artefacts-inpressco
- Un retry automatique est limité à 1 tentative — au-delà, l'humain doit intervenir
- L'impact client est TOUJOURS évalué en premier — une erreur bloquant une commande urgente prime sur tout
- Ce skill est appelé automatiquement par tous les autres skills en cas d'erreur — ne pas attendre de déclenchement manuel
- Tous les incidents sont LOGGUÉS même si résolus — pour analyse de la fiabilité du système
