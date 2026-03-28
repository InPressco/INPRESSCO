---
name: archiveur-inpressco
description: >
  Skill de classification, nommage et dépôt de fichiers pour In'Pressco. Déclencher SYSTÉMATIQUEMENT dès qu'un fichier, PJ, visuel ou document doit être rangé : BAT sur commande Dolibarr, facture fournisseur, visuel IA en base images, bon de commande, fichier issu d'email. Déclencher aussi sans mot-clé explicite si un email contient des PJ, si un skill produit un fichier, ou si l'utilisateur dit "j'ai reçu le fichier", "voici le PDF", "le client a envoyé son BC". Triggers directs : "range ça", "dépose ce fichier", "archive cette PJ", "classe ce visuel", "mets ça sur le devis", "enregistre la facture". Analyse chaque pièce, détermine sa nature, applique la convention de nommage InPressco, vérifie les doublons, route vers Dolibarr ou base images. Gère les lots multi-fichiers avec récap consolidé. En cas d'erreur API → déclencher gestion-erreurs-inpressco. Ne jamais déposer un fichier sans ce skill — il garantit la cohérence et la traçabilité documentaire.
---

# Archiveur — In'Pressco

## Rôle
Recevoir tout fichier produit ou reçu dans le système, l'analyser, lui appliquer la convention de nommage InPressco, et le déposer au bon endroit — dossier Dolibarr ou base images — avec les métadonnées associées. Ce skill est la **porte d'entrée unique** pour toute pièce entrant dans les bases de données.

---

## Convention de nommage InPressco

Tous les fichiers archivés suivent ce format :

```
[TYPE]_[TIERS]_[REF]_[DATE]_[VERSION].[EXT]
```

| Segment | Description | Exemples |
|---------|-------------|---------|
| `TYPE` | Nature du document | `BAT` `BC` `FA` `DEV` `VISUEL` `BRIEF` `PJ` `CONTRAT` `PROD` |
| `TIERS` | Nom court du tiers (max 20 chars, sans espaces) | `AgenceExemple` `DupontSARL` `FournisseurX` |
| `REF` | Référence Dolibarr associée | `DEV-2026-089` `CMD-2026-045` |
| `DATE` | Date au format `AAAAMMJJ` | `20260326` |
| `VERSION` | Version si applicable | `v1` `v2` `vFINAL` |
| `EXT` | Extension originale conservée | `pdf` `ai` `jpg` `png` `xlsx` |

**Exemples de noms conformes :**
```
BAT_AgenceExemple_CMD-2026-045_20260326_v2.pdf
FA_FournisseurPapier_FA-2026-112_20260315.pdf
VISUEL_InPressco_CAM-Printemps_20260320_vFINAL.jpg
BC_DupontSARL_CMD-2026-038_20260310.pdf
BRIEF_NouveauClient_DEV-2026-101_20260326.pdf
PROD_AgenceExemple_CMD-2026-045_20260326_v1.ai
```

**Règles de nommage :**
- Pas d'espaces, pas d'accents, pas de caractères spéciaux
- Tirets `-` autorisés uniquement dans la référence Dolibarr
- Underscores `_` comme séparateurs de segments
- Nom court du tiers : supprimer les articles (Le, La, Les), abréger si > 20 chars
- Si pas de référence Dolibarr : utiliser `SANS-REF` temporairement
- Si tiers inconnu : utiliser `INCONNU` et signaler après dépôt

---

## Types de fichiers et destinations

| Type détecté | Exemples | Destination | modulepart Dolibarr |
|--------------|---------|-------------|---------------------|
| BAT (bon à tirer) | `.pdf` avec "BAT", "épreuve", "validation" | Dolibarr → commande | `commande` |
| Bon de commande client | `.pdf` signé, tampon client | Dolibarr → commande | `commande` |
| Fichier de production | `.ai` `.indd` `.eps` `.pdf` haute résolution | Dolibarr → commande | `commande` |
| Brief client | `.pdf` `.docx` `.txt` description projet | Dolibarr → devis | `proposal` |
| Facture fournisseur | `.pdf` avec montant, n° facture fournisseur | Dolibarr → facture | `facture` |
| Devis fournisseur | `.pdf` offre de prix reçue | Dolibarr → devis | `proposal` |
| Contrat | `.pdf` signé, mentions légales | Dolibarr → tiers | `societe` |
| Document interne | `.xlsx` `.docx` planning, suivi | Dolibarr → tiers | `societe` |
| Visuel généré IA | `.jpg` `.png` `.webp` produit par Claude | Base images | — |
| Photo produit | `.jpg` `.png` `.tif` photo imprimé livré | Base images | — |
| Asset graphique | `.svg` `.ai` `.eps` logo, charte | Base images | — |

> ⚠️ Les fichiers `.ai` `.indd` `.eps` sont des fichiers de **production** — toujours sur la commande, jamais en base images.

---

## Processus d'archivage

### Étape 1 — Analyser le fichier

Examiner dans l'ordre :
1. **Extension** : `.pdf` `.ai` `.jpg` `.png` `.xlsx` `.docx`...
2. **Nom d'origine** : indices sur le type (BAT, facture, bon de commande, brief...)
3. **Contenu extractable** : texte PDF, métadonnées EXIF, mots-clés présents
4. **Contexte conversation** : ce que l'utilisateur a dit sur ce fichier
5. **Source** : email entrant, généré par Claude, uploadé manuellement, produit par un autre skill

**Cas particuliers :**
- **Fichier sans extension** → inférer depuis le contenu binaire (magic bytes) ; si impossible, demander
- **Archive `.zip`** → décompresser, traiter chaque fichier individuellement, puis récap consolidé
- **Image sans contexte** → demander si BAT, photo produit ou visuel IA avant de classer
- **Lot multi-fichiers** → boucler sur chaque fichier, archiver un par un, récap à la fin

---

### Étape 2 — Identifier le tiers et le document associé

```
1. Chercher une référence Dolibarr dans le nom ou le contenu du fichier
   → DEV-XXXX, CMD-XXXX, FA-XXXX → résoudre via dolibarr-query-inpressco

2. Si pas de référence → chercher un nom de tiers dans le nom/contenu
   → résoudre via dolibarr-query-inpressco (recherche par nom)

3. Si tiers inconnu mais contexte suffisant → proposer création fiche minimale
   → sinon utiliser INCONNU et signaler

4. Si aucun contexte exploitable → demander à l'utilisateur AVANT de continuer
```

---

### Étape 3 — Déterminer la destination

```
Document métier (BAT, BC, FA, BRIEF, CONTRAT, PROD)
  → Dolibarr
  → modulepart : proposal | commande | facture | societe
  → id : ID de l'objet Dolibarr associé

Visuel / image / asset graphique
  → Base images (via bdd-images-query-inpressco)
  → Catégorie : generated_ai | photo_produit | asset_graphique | reference_bat

Ambiguïté (ex: PDF inconnu sans contexte suffisant)
  → Présenter les options à l'utilisateur et attendre confirmation
```

---

### Étape 4 — Appliquer la convention de nommage

```
TYPE    → déterminé à l'étape 1
TIERS   → nom court extrait du tiers Dolibarr ou de la conversation
REF     → référence Dolibarr résolue, ou SANS-REF
DATE    → date du jour au format AAAAMMJJ
VERSION → v1 par défaut ; incrémenter si doublon détecté
EXT     → conserver l'extension d'origine (ne jamais convertir)
```

---

### Étape 5 — Vérifier les doublons

Avant tout dépôt :
```
GET /documents?modulepart={module}&id={id}
→ Chercher un fichier de même TYPE + même TIERS + même REF dans le dossier
→ Si doublon exact (même nom) → incrémenter VERSION (v1 → v2)
→ Si doublon partiel (même type, date différente) → signaler, demander confirmation
→ Si aucun doublon → procéder au dépôt
```

---

### Étape 6 — Déposer

**Vers Dolibarr :**
```
POST /documents/upload
  modulepart        : "proposal" | "commande" | "facture" | "societe"
  id                : {id_objet_dolibarr}
  ref               : {ref_objet}
  filename          : {nom_conforme_convention}
  filecontent       : {base64_du_fichier}
  overwriteifexists : 0   ← ne jamais écraser sans confirmation explicite
```

**Vers base images (via skill bdd-images-query-inpressco) :**
```
Transmettre au skill bdd-images-query-inpressco avec :
  nom_fichier       : {nom_conforme_convention}
  categorie         : generated_ai | photo_produit | asset_graphique | reference_bat
  tiers_associe     : {socid ou nom du tiers}
  ref_dolibarr      : {ref si applicable, sinon null}
  date_creation     : {AAAAMMJJ}
  tags              : [liste de tags déduits du contexte]
  statut            : brouillon | validé | archivé
```

---

### Étape 7 — Gérer les erreurs API

Si l'upload Dolibarr retourne une erreur :

| Code / symptôme | Action |
|-----------------|--------|
| 401 Unauthorized | Signaler à l'utilisateur — problème d'authentification API |
| 404 Not Found (id objet) | Vérifier l'id via dolibarr-query-inpressco, relancer ou demander confirmation |
| 413 Payload Too Large | Informer l'utilisateur que le fichier dépasse la limite Dolibarr |
| 500 / timeout | Réessayer une fois ; si échec → déclencher gestion-erreurs-inpressco |
| Réponse vide ou malformée | Considérer comme échec → déclencher gestion-erreurs-inpressco |

En cas d'erreur non récupérable → déclencher **gestion-erreurs-inpressco** et logguer l'incident.

---

## Schéma JSON de sortie

```json
{
  "archivage": {
    "fichier_original": "bon_commande_client.pdf",
    "fichier_renomme": "BC_AgenceExemple_CMD-2026-045_20260326_v1.pdf",
    "type_detecte": "bon_de_commande",
    "destination": "dolibarr",
    "modulepart": "commande",
    "id_objet": "89",
    "ref_objet": "CMD-2026-045",
    "socid": "42",
    "tiers": "Agence Exemple SARL",
    "doublon": false,
    "statut": "deposé | en_attente_confirmation | erreur",
    "erreur": null
  },
  "metadata_base_images": null,
  "alerte": null
}
```

**Pour un lot multi-fichiers**, retourner un tableau `archivages: [...]` + un champ `recap` :
```json
{
  "archivages": [ { "..." }, { "..." } ],
  "recap": {
    "total": 3,
    "deposés": 2,
    "en_attente": 1,
    "erreurs": 0
  }
}
```

---

## Règles de sécurité et qualité

- **Jamais écraser** un fichier existant sans confirmation explicite (`overwriteifexists: 0`)
- **Jamais déposer** sans avoir résolu le tiers et le document associé
- **Jamais convertir** un fichier lors de l'archivage — l'extension d'origine est toujours conservée
- **Signaler** si le fichier semble corrompu (taille 0, extension incohérente avec le contenu)
- **Confirmer** avant dépôt si la destination est ambiguë
- **Profil `CLIENT`** → ne peut déposer que sur ses propres documents (vérifier via droits-profils-inpressco)
- **Profil `TEAM` / `ADMIN`** → accès complet

---

## Présentation à l'utilisateur

### ✅ Archivage réussi
```
✓ Fichier déposé avec succès

Nom         : BAT_AgenceExemple_CMD-2026-045_20260326_v2.pdf
Destination : Dolibarr → Commande CMD-2026-045
Tiers       : Agence Exemple SARL
```

### ❓ Confirmation requise (ambiguïté)
```
J'ai analysé ce fichier : "document_final.pdf"

Type probable    : BAT (mentions "épreuve" et "validation" dans le contenu)
Document associé : CMD-2026-045 (Agence Exemple)
Nom proposé      : BAT_AgenceExemple_CMD-2026-045_20260326_v1.pdf
Destination      : Dolibarr → dossier commande

[Confirmer] [Modifier] [Annuler]
```

### ⚠️ Doublon détecté
```
Un fichier similaire existe déjà :
→ BAT_AgenceExemple_CMD-2026-045_20260320_v1.pdf (déposé le 20/03)

Souhaitez-vous :
[Déposer en v2] [Remplacer v1] [Annuler]
```

### ❌ Erreur de dépôt
```
Le dépôt du fichier a échoué.

Fichier : BC_DupontSARL_CMD-2026-038_20260326_v1.pdf
Erreur  : Objet CMD-2026-038 introuvable dans Dolibarr
Action  : Veuillez vérifier la référence ou préciser la commande cible.
```

### 📋 Contexte manquant
```
Je n'ai pas pu identifier le document ou le tiers associé à ce fichier.

Pouvez-vous préciser :
→ Sur quelle commande ou quel devis ce fichier doit-il être déposé ?
→ Ou quel est le nom du client / fournisseur concerné ?
```

### 📦 Récap lot multi-fichiers
```
Archivage terminé — 3 fichiers traités

✓ BAT_AgenceExemple_CMD-2026-045_20260326_v1.pdf → Dolibarr / commande
✓ BC_DupontSARL_CMD-2026-038_20260326_v1.pdf     → Dolibarr / commande
⏳ document_inconnu.pdf                           → En attente : tiers non résolu

Action requise : préciser le tiers pour le 3ᵉ fichier.
```

---

## Exemples

### BAT reçu par email
> Email entrant avec PJ "epreuve_catalogue.pdf"
→ Analyser : contenu = "Bon à tirer", référence CMD-2026-045 dans le texte
→ Tiers : Agence Exemple (résolu via dolibarr-query-inpressco)
→ Renommer : `BAT_AgenceExemple_CMD-2026-045_20260326_v1.pdf`
→ Déposer : `POST /documents/upload` modulepart=commande id=89

### Visuel généré par Claude
> Un skill produit `visuel_instagram.jpg` en contexte campagne printemps 2026
→ Analyser : généré par IA, contexte = campagne Instagram InPressco
→ Destination : base images (via bdd-images-query-inpressco)
→ Renommer : `VISUEL_InPressco_CAM-Printemps_20260326_v1.jpg`
→ Métadonnées : categorie=generated_ai, tags=[instagram, printemps, 2026], statut=brouillon

### Facture fournisseur reçue
> Email fournisseur avec PJ "Facture_Mars2026.pdf"
→ Analyser : montant 3 480 €, n° FA-FOURN-2026-042, expéditeur fournisseur papier
→ Référence Dolibarr : FA-2026-112 (résolue via dolibarr-query-inpressco)
→ Renommer : `FA_FournisseurPapier_FA-2026-112_20260326.pdf`
→ Déposer : `POST /documents/upload` modulepart=facture id=112

### Bon de commande uploadé manuellement
> Utilisateur : "Range ce bon de commande sur la CMD-2026-038"
→ Référence explicite : CMD-2026-038
→ Tiers : Dupont SARL (résolu depuis la commande via dolibarr-query-inpressco)
→ Renommer : `BC_DupontSARL_CMD-2026-038_20260326_v1.pdf`
→ Déposer : `POST /documents/upload` modulepart=commande id=78

### Email avec 3 pièces jointes
> Email entrant avec BAT.pdf + BC_signe.pdf + photo_produit.jpg
→ Traiter chaque fichier individuellement (boucle étapes 1 à 6)
→ Présenter un récap consolidé à la fin

---

## Notes importantes
- Ce skill gère les **fichiers** — le skill `chat-to-db-inpressco` gère les **données textuelles** — complémentaires, non substituables
- La convention de nommage est **obligatoire** pour tous les fichiers, y compris ceux uploadés manuellement
- `dolibarr-query-inpressco` est **toujours appelé** pour résoudre les références avant tout dépôt
- En cas d'erreur non récupérable → déclencher `gestion-erreurs-inpressco`
- Les fichiers `.ai` `.indd` `.eps` sont des fichiers de production → toujours sur la commande, jamais en base images
- Pour les dépôts en base images → passer systématiquement par `bdd-images-query-inpressco`
