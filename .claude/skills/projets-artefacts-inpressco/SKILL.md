---
name: projets-artefacts-inpressco
description: >
  Mémoire des productions Claude pour In'Pressco. Déclencher SYSTÉMATIQUEMENT dès qu'une production est terminée, mentionnée, cherchée, modifiée ou à sauvegarder : devis, email préparé, brief, analyse, récapitulatif projet, template graphique, planning, visuel IA archivé. Triggers immédiats : "le devis", "l'email", "le brief", "la prod", "le récap", "le plan", "retrouve", "reprends", "où est", "sauvegarde", "garde ça", "on avait préparé", "itère sur", "mets à jour", "est-ce qu'il existe encore", "on l'a fait", "repars de". Ne jamais recréer une production sans d'abord chercher ici. Déclencher aussi dès qu'une production longue vient d'être créée — proposer la sauvegarde.
---

# Projets / Artefacts — In'Pressco

## Rôle
Donner à Claude une mémoire persistante de ses propres productions. Retrouver, réutiliser, itérer ou sauvegarder tout document, devis, email, analyse, PDF, planning ou visuel — en session ou entre sessions. Ne jamais recréer ce qui existe déjà.

---

## Types de productions gérées

| Type | Exemples | Stockage principal |
|------|---------|-------------------|
| Devis rédigé | Structure devis avant création Dolibarr | Stockage + session |
| Email rédigé | Réponse client, relance, courrier | Session + stockage |
| Brief structuré | Données extraites brief oral ou email | Session + chat-to-db |
| Analyse tarifaire | Estimation prix, cohérence devis | Session + stockage |
| Récapitulatif projet | Synthèse projet ou historique client multi-sessions | Stockage persisté |
| PDF généré | Devis ou courrier produit en PDF | Dolibarr ou outputs |
| Planning / agenda | Liste tâches, workflow planifié, échéancier | Stockage + agenda |
| Visuel IA archivé | Image générée en session, archivée | Base images (archiveur) |

---

## Sources de recherche — ordre strict

### 1. Session en cours (priorité absolue)
Tout ce qui est dans la conversation active est accessible immédiatement.
Chercher dans le contexte actuel avant toute autre action.

Signal : "tout à l'heure", "qu'on vient de faire", "dans cette session"
→ Si présent : réafficher ou utiliser directement.
→ Ne pas chercher ailleurs si trouvé ici.

### 2. Storage persisté (cross-sessions)

```javascript
// Lister tous les artefacts sauvegardés
const index = await window.storage.get('artefacts:index');

// Accès direct par clé
await window.storage.get('artefacts:{type}:{ref}');

// Lister par type
await window.storage.list('artefacts:devis:');
await window.storage.list('artefacts:email:');
await window.storage.list('artefacts:recap:');
await window.storage.list('artefacts:planning:');
```

Structure de l'index stocké sous `artefacts:index` :

```json
{
  "artefacts:devis:DEV-2026-089": {
    "type": "devis",
    "ref": "DEV-2026-089",
    "tiers": "Agence Exemple SARL",
    "date_creation": "2026-03-26",
    "statut": "brouillon | envoyé | archivé",
    "resume": "Catalogue A5 24p 1000ex couché mat pelliculage"
  },
  "artefacts:email:relance-DEV-2026-089": {
    "type": "email",
    "ref": "relance-DEV-2026-089",
    "tiers": "Agence Exemple SARL",
    "date_creation": "2026-03-26",
    "statut": "non_envoyé | envoyé",
    "resume": "Relance devis catalogue printemps"
  }
}
```

### 3. Dolibarr (documents officiels formalisés)
Uniquement si le document a déjà été créé dans Dolibarr :
→ Appeler `dolibarr-query-inpressco`

### 4. Base images (visuels archivés)
Pour les visuels générés et archivés :
→ Appeler `bdd-images-query-inpressco`

---

## Processus de recherche — étape par étape

**Étape 1 — Identifier la cible**
```
Type         : devis | email | brief | analyse | récap | PDF | planning | visuel
Client/projet : nom tiers, référence, thème projet
Signal temps  : "tout à l'heure" → session | "hier/semaine dernière" → storage |
                "en mars" → storage + Dolibarr
```

**Étape 2 — Parcourir les sources dans l'ordre**
```
1. Contexte conversation actuelle  → immédiat, aucun appel
2. storage.list('artefacts:')      → index cross-sessions
3. dolibarr-query-inpressco        → si document formalisé
4. bdd-images-query-inpressco      → si visuel IA
```

**Étape 3 — Présenter le résultat**
```
Trouvé     → afficher résumé + proposer actions (voir section "Présentation")
Non trouvé → proposer reconstruire | chercher Dolibarr | annuler
```

**Étape 4 — Mettre à jour le stockage si besoin**
Si une production trouvée a changé de statut ou a été modifiée → mettre à jour le storage.

---

## Logique de sauvegarde — quand et comment

### Quand sauvegarder automatiquement (proposer sans attendre)
- Devis complet rédigé (structure + montant + délai)
- Email de réclamation ou courrier formel
- Récapitulatif projet ou synthèse client longue
- Planning ou workflow multi-étapes
- Analyse tarifaire détaillée

### Quand ne pas sauvegarder
- Réponse courte ou esquisse rapide (< 5 lignes)
- Production déjà présente dans Dolibarr
- Email simple sans enjeu de suivi

### Comment sauvegarder

**Étape A — Enregistrer l'artefact**
```javascript
await window.storage.set(
  'artefacts:{type}:{ref_ou_id}',
  JSON.stringify({
    type: 'devis',           // devis | email | brief | analyse | recap | planning | visuel
    ref: 'DEV-2026-089',
    tiers: 'Agence Exemple SARL',
    socid: 42,               // ID Dolibarr si connu
    date_creation: '2026-03-26',
    statut: 'brouillon',     // brouillon | envoyé | archivé | non_envoyé
    resume: 'Catalogue A5 24p 1000ex couché mat pelliculage mat',
    contenu: { /* payload complet */ }
  })
);
```

**Étape B — Mettre à jour l'index**
```javascript
// Lire l'index existant
let index = {};
try {
  const raw = await window.storage.get('artefacts:index');
  index = raw ? JSON.parse(raw.value) : {};
} catch { index = {}; }

// Ajouter l'entrée
index['artefacts:devis:DEV-2026-089'] = {
  type: 'devis',
  ref: 'DEV-2026-089',
  tiers: 'Agence Exemple SARL',
  date_creation: '2026-03-26',
  statut: 'brouillon',
  resume: 'Catalogue A5 24p 1000ex couché mat pelliculage mat'
};

// Sauvegarder l'index mis à jour
await window.storage.set('artefacts:index', JSON.stringify(index));
```

---

## Schéma JSON de sortie

```json
{
  "recherche": {
    "type": "devis | email | brief | analyse | recap | PDF | planning | visuel",
    "criteres": "DEV-2026-089 | Agence Exemple | catalogue printemps",
    "source": "session | storage | dolibarr | base_images",
    "statut": "trouvé | non_trouvé"
  },
  "artefact": {
    "type": "devis",
    "ref": "DEV-2026-089",
    "tiers": "Agence Exemple SARL",
    "date_creation": "2026-03-26",
    "statut": "brouillon",
    "resume": "Catalogue A5 24p 1000ex couché mat pelliculage",
    "contenu": {}
  },
  "actions_proposees": ["réutiliser", "modifier", "envoyer", "archiver_dolibarr", "sauvegarder"]
}
```

---

## Présentation à l'utilisateur

### Artefact en session trouvé
```
J'ai retrouvé le devis préparé tout à l'heure :

Devis — Agence Exemple SARL
Catalogue A5 24p · 1 000 ex · Couché mat · Pelliculage mat
Montant estimé : 530–760 € HT · Livraison : 15 avril

[Créer dans Dolibarr] [Modifier] [Envoyer par email] [Sauvegarder]
```

### Artefact en stockage trouvé
```
J'ai retrouvé une production sauvegardée du 26/03 :

Email de relance — DEV-2026-089 — Agence Exemple
Rédigé le 26/03 · Statut : non envoyé

[Afficher] [Envoyer maintenant] [Modifier] [Supprimer]
```

### Proposition de sauvegarde automatique (après création)
```
Ce devis est complet — souhaitez-vous que je le sauvegarde
pour pouvoir le retrouver lors d'une prochaine session ?

[Sauvegarder] [Non merci]
```

### Non trouvé
```
Je n'ai pas trouvé cette production dans la session actuelle
ni dans les artefacts sauvegardés.

Souhaitez-vous que je le reconstruise depuis les données disponibles ?
[Reconstruire] [Chercher dans Dolibarr] [Annuler]
```

---

## Règles importantes

- **Session en cours = priorité absolue** — ne jamais appeler le storage si la production est encore dans le contexte
- **Index obligatoire** — toute sauvegarde doit mettre à jour `artefacts:index` en même temps
- **Proposer la sauvegarde** pour les productions longues ou complexes, sans attendre que l'utilisateur le demande
- **Avant de renvoyer un artefact retrouvé** → passer par `validation-qc-inpressco`
- Ce skill gère les brouillons et productions — les documents officiels vivent dans Dolibarr
- **Récap multi-sessions** : si l'artefact couvre plusieurs sessions, lire le stockage complet (`artefacts:recap:`) avant de construire la synthèse
