---
name: dolibarr-query-inpressco
description: >
  Skill de lecture, interrogation ET modification de Dolibarr via API REST pour In'Pressco. Déclencher SYSTÉMATIQUEMENT dès que Claude doit consulter, vérifier, récupérer OU modifier des données depuis Dolibarr : recherche d'un tiers, lecture d'un devis ou d'une commande, consultation du statut, récupération de l'historique, liste des pièces jointes. Déclencher aussi pour toute action d'écriture : modifier un champ (note, date, condition, adresse), enrichir un champ personnalisé (array_options), mettre à jour une ligne de devis ou de commande, gérer le cycle de vie d'une pièce (valider, refuser, annuler, versionner/cloner). Utiliser pour : "mets à jour la note du devis", "enrichis le descriptif technique", "valide cette commande", "clone ce devis en v2", "annule la facture", "change la date de livraison", "ajoute le champ projet", "refuse ce devis", "modifie la ligne 3", ainsi que toutes les lectures habituelles. Ne jamais inventer de données Dolibarr — toujours interroger puis confirmer avant d'écrire.
---

# Dolibarr Query & Write — In'Pressco

## Rôle
Interroger ET modifier l'API REST Dolibarr pour alimenter Claude en données complètes et fiables, et appliquer des changements avec confirmation systématique. Ce skill couvre : lecture de tous les objets (tiers, devis, commandes, factures, lignes, PJ, contacts, agenda), modification de champs natifs et personnalisés, et gestion du cycle de vie des pièces.

---

## Configuration API

```
BASE_URL : https://in-pressco.crm.freshprocess.eu/api/index.php
AUTH     : Header "DOLAPIKEY: {DOLIBARR_API_KEY}"
FORMAT   : JSON
OWNER_ID : 166
```

Credentials en variable d'environnement — ne jamais afficher ni logger.

---

## 🔒 Règle d'or — Validation avant toute écriture

**Toute opération d'écriture (PUT / POST / DELETE) DOIT suivre ce protocole :**

```
1. LIRE l'état actuel (GET) — récupérer les valeurs actuelles de TOUS les champs
   à modifier

2. AFFICHER le détail champ par champ :
   ┌──────────────────────────────────────────────────────────┐
   │ ✏️  MODIFICATION DOLIBARR                                 │
   │ Objet   : [type] [ref] — [nom tiers]                     │
   │ Action  : [description lisible de l'intention]           │
   │                                                          │
   │ Champ 1 — [nom lisible du champ]                         │
   │   AVANT : "[valeur actuelle exacte]"                     │
   │   APRÈS : "[nouvelle valeur proposée]"                   │
   │                                                          │
   │ Champ 2 — [nom lisible du champ]                         │
   │   AVANT : "[valeur actuelle exacte]"                     │
   │   APRÈS : "[nouvelle valeur proposée]"                   │
   │  (répéter pour chaque champ modifié)                     │
   │                                                          │
   │ Champs inchangés : [liste des autres champs — non touchés]│
   └──────────────────────────────────────────────────────────┘

3. DEMANDER confirmation explicite :
   "✅ Confirmer les modifications ? (oui pour valider / non pour annuler /
    modifier [champ] pour ajuster une valeur)"

4. N'exécuter QUE si réponse = oui / ok / confirme / yes
   Si l'utilisateur demande à ajuster un champ → revenir à l'étape 2 avec
   la correction, ne jamais écrire partiellement.

5. Après écriture : re-lire CHAQUE champ modifié et confirmer la valeur
   enregistrée dans Dolibarr
```

> **Règle de clarté :** Si une valeur actuelle est vide/nulle, afficher `(vide)`.
> Si une valeur est un timestamp, toujours la convertir en `JJ/MM/AAAA`.
> Si une valeur est longue (>80 car.), tronquer avec `...` et indiquer la longueur totale.

---

**Profils et droits d'écriture :**

| Profil | Lectures | Modifications autorisées |
|--------|----------|--------------------------|
| `ADMIN` | Tout | Tout — champs natifs, champs perso, lignes, cycle de vie complet |
| `TEAM` | Tout | Champs natifs (notes, dates, conditions), champs perso, lignes descriptives |
| `CLIENT` | Ses propres pièces uniquement, jamais `note_private` | Voir tableau ci-dessous |

**Droits d'écriture CLIENT (limités à ses propres pièces) :**

| Action CLIENT | Endpoint | Condition |
|---------------|----------|-----------|
| Signer / accepter un devis | `POST /proposals/{id}/close` body `{status:2}` | Devis au statut `1` (validé) uniquement |
| Ajouter un commentaire (note_public) | `PUT /proposals/{id}` body `{note_public}` | Ne peut que *ajouter*, jamais effacer |
| Modifier email/tél de sa propre fiche | `PUT /thirdparties/{socid}` | Champs `email`, `phone`, `phone_mobile` uniquement |

> ⚠️ Le `CLIENT` ne peut **jamais** : modifier `note_private`, toucher aux lignes, changer les montants, accéder aux données d'un autre tiers, ni déclencher une action cycle de vie autre que la signature d'un devis qui lui est adressé.

---

## Endpoints — Lecture (GET)

### Tiers

| Besoin | Endpoint | Paramètres |
|--------|----------|------------|
| Par nom | `GET /thirdparties` | `?sqlfilters=(t.nom:like:'%{nom}%')&limit=20` |
| Par email | `GET /thirdparties` | `?sqlfilters=(t.email:=:'{email}')` |
| Par téléphone | `GET /thirdparties` | `?sqlfilters=(t.phone:like:'%{tel}%')` |
| Par code client | `GET /thirdparties` | `?sqlfilters=(t.code_client:=:'{code}')` |
| Par SIREN | `GET /thirdparties` | `?sqlfilters=(t.siren:=:'{siren}')` |
| Fiche complète | `GET /thirdparties/{id}` | — |
| Contacts | `GET /thirdparties/{id}/contacts` | — |
| Catégories | `GET /thirdparties/{id}/categories` | — |

**Champs disponibles :**
```
id, nom, name_alias, code_client, code_fournisseur
email, phone, fax, url
address, zip, town, state, country_code
client, fournisseur, prospect (flags 0/1)
siren, siret, ape, tva_intra
note_public, note_private
date_creation, date_modification, status
commercial_id, array_options (champs personnalisés)
```

---

### Devis (proposals)

| Besoin | Endpoint | Paramètres |
|--------|----------|------------|
| Par référence | `GET /proposals/ref/{ref}` | — |
| Par ID | `GET /proposals/{id}` | — |
| Liste par tiers | `GET /proposals` | `?thirdparty_ids={socid}&limit=50` |
| Par statut | `GET /proposals` | `?status=0\|1\|2\|3` |
| **Lignes complètes** | `GET /proposals/{id}/lines` | — |
| PJ / documents | `GET /documents` | `?modulepart=proposal&id={id}` |
| Télécharger PJ | `GET /documents/download` | `?modulepart=proposal&original_file={chemin}` |

**Statuts devis :** `0`=brouillon · `1`=validé · `2`=signé · `3`=refusé · `4`=archivé

**Champs d'un devis :**
```
id, ref, socid, societe
date, date_livraison (epoch → convertir)
statut, total_ht, total_tva, total_ttc, remise_percent
cond_reglement_id, mode_reglement_id
model_pdf (="azur_fp" pour InPressco)
note_public, note_private
date_creation, date_validation
array_options.options_fhp_project_name  ← nom du projet
array_options.options_analysen8n        ← données IA : imposition, score, alertes
```

**Champs d'une ligne de devis :**
```
id, rankorder
product_id, product_ref, product_label
label            ← titre court de la ligne
description      ← DESCRIPTIF COMPLET MULTI-LIGNES (principal contenu textuel)
qty, subprice, remise_percent
total_ht, total_tva, total_ttc, tva_tx
product_type     : 0=produit/prix · 9=titre ou descriptif
special_code     : 104777=synthèse contexte · 104778=descriptif technique
array_options.options_analysen8n
```

> **Descriptifs InPressco :** `product_type=9`, `special_code=104778` = descriptif technique complet (format, grammage, finition, type d'impression, reliure, conditionnement, quantités, imposition). `special_code=104777` = synthèse contexte client.

---

### Commandes (orders)

| Besoin | Endpoint | Paramètres |
|--------|----------|------------|
| Par référence | `GET /orders/ref/{ref}` | — |
| Par ID | `GET /orders/{id}` | — |
| Liste par tiers | `GET /orders` | `?thirdparty_ids={socid}&limit=50` |
| Par statut | `GET /orders` | `?status=0\|1\|2\|3\|-1` |
| **Lignes complètes** | `GET /orders/{id}/lines` | — |
| PJ / documents | `GET /documents` | `?modulepart=commande&id={id}` |

**Statuts commande :** `0`=brouillon · `1`=validée · `2`=expédiée · `3`=livrée · `-1`=annulée

**Champs d'une commande :**
```
id, ref, socid, societe
date_commande, date_livraison (epoch)
statut, total_ht, total_tva, total_ttc
note_public, note_private
date_creation, date_modification
linked_objects (devis d'origine lié)
array_options (champs personnalisés)
```

---

### Factures, Contacts, Agenda, Documents, Produits

| Type | Endpoints clés |
|------|----------------|
| Factures | `GET /invoices/ref/{ref}` · `/invoices/{id}/lines` · `/invoices/{id}/payments` |
| Contacts | `GET /contacts` · `/thirdparties/{id}/contacts` |
| Agenda | `GET /agendaevents?elementtype={type}&fk_element={id}` |
| Documents | `GET /documents?modulepart={module}&id={id}` |
| Produits | `GET /products/ref/{ref}` · `/products/{id}` |

**Statuts facture :** `0`=brouillon · `1`=validée · `2`=payée · `3`=abandonnée

**Produit clé InPressco :** ID `35700` = produit impression standard.

---

## ✏️ Endpoints — Écriture (PUT / POST)

### Modifier un objet — champs natifs

#### Devis
```
PUT /proposals/{id}
Body JSON : { "note_public": "...", "date_livraison": {epoch}, ... }
```

**Champs modifiables :**
```
note_public, note_private
date_livraison (epoch Unix)
cond_reglement_id (conditions de paiement)
mode_reglement_id (mode de règlement)
remise_percent (remise globale)
array_options.options_fhp_project_name
array_options.options_analysen8n
```

#### Commande
```
PUT /orders/{id}
Body JSON : { "note_public": "...", "date_livraison": {epoch}, ... }
```

#### Tiers
```
PUT /thirdparties/{id}
Body JSON : { "note_public": "...", "email": "...", "phone": "...", ... }
```

**Champs modifiables tiers :**
```
nom, name_alias
email, phone, fax, url
address, zip, town
note_public, note_private
commercial_id
array_options.* (tous les champs personnalisés)
```

---

### Modifier une ligne de devis ou commande

```
PUT /proposals/{id}/lines/{line_id}
PUT /orders/{id}/lines/{line_id}

Body JSON :
{
  "label": "Titre de la ligne",
  "description": "Descriptif complet multi-lignes...",
  "qty": 500,
  "subprice": 1250.00,
  "remise_percent": 10
}
```

> ⚠️ Toujours lire les lignes complètes avant modification pour récupérer l'exact `line_id`.

---

### Enrichir un champ personnalisé (array_options)

Les champs `array_options` permettent de stocker des données métier InPressco. Mis à jour via le PUT de l'objet parent.

```
PUT /proposals/{id}
Body JSON :
{
  "array_options": {
    "options_fhp_project_name": "Catalogue Printemps 2026",
    "options_analysen8n": "{\"imposition\":\"4pp\",\"score\":92,\"alertes\":[]}"
  }
}
```

**Créer un nouveau champ perso :** tout nouveau champ inclus dans `array_options` sera créé s'il n'existe pas (selon config Dolibarr). Vérifier d'abord via GET que le champ n'existe pas déjà pour éviter les doublons.

---

## 🔄 Cycle de vie des pièces

### Valider un devis (brouillon → validé)
```
POST /proposals/{id}/validate
Body JSON : { "notrigger": 0 }
```
→ Statut `0` → `1`. Génère le PDF Dolibarr (modèle azur_fp).

### Refuser un devis
```
POST /proposals/{id}/refuse
Body JSON : { "comment": "Motif du refus...", "notrigger": 0 }
```
→ Statut → `3`.

### Clore / Signer un devis (accepté client)
```
POST /proposals/{id}/close
Body JSON : { "status": 2, "note_close": "...", "notrigger": 0 }
```
→ Statut → `2`.

### Valider une commande (brouillon → validée)
```
POST /orders/{id}/validate
Body JSON : { "notrigger": 0 }
```

### Annuler une commande
```
PUT /orders/{id}
Body JSON : { "statut": -1 }
```

### Versionner / Cloner un devis en v2

Dolibarr n'a pas d'endpoint natif "clone". Procédure manuelle :

```
1. GET /proposals/{id}           → lire toutes les données du devis original
2. GET /proposals/{id}/lines     → lire toutes les lignes
3. POST /proposals               → créer nouveau devis (ref auto-générée)
   Body : { ...champs copiés, "note_private": "Clone de {ref_original}" }
4. Pour chaque ligne :
   POST /proposals/{new_id}/lines → recréer la ligne avec les mêmes champs
5. Afficher la nouvelle référence créée
```

> La référence est auto-générée par Dolibarr. Toujours mentionner la ref d'origine en `note_private` pour traçabilité.

---

## Séquence de modification complète (workflow type)

```
Demande : "Mets à jour le descriptif technique du DEV-2026-089"

1. GET /proposals/ref/DEV-2026-089
   → récupérer id, statut, vérifier profil (TEAM/ADMIN requis)

2. GET /proposals/{id}/lines
   → trouver ligne special_code=104778 → récupérer line_id + description actuelle

3. AFFICHER résumé avant confirmation :
   ┌────────────────────────────────────────────────┐
   │ ✏️  MODIFICATION — DEV-2026-089                 │
   │ Ligne : Descriptif technique (id: {line_id})    │
   │ AVANT → "Impression offset 4 couleurs, 135g..." │
   │ APRÈS → "[nouveau descriptif proposé]"          │
   └────────────────────────────────────────────────┘
   "✅ Confirmer la modification ? (oui / non)"

4. Si confirmé :
   PUT /proposals/{id}/lines/{line_id}
   Body : { "description": "nouveau descriptif..." }

5. Vérification :
   GET /proposals/{id}/lines → relire et confirmer le changement
   "✅ Descriptif mis à jour sur DEV-2026-089."
```

---

## Séquence de lecture complète d'un devis

```
1. GET /proposals/ref/{ref}
2. GET /proposals/{id}/lines
3. GET /documents?modulepart=proposal&id={id}
4. GET /agendaevents?elementtype=propal&fk_element={id}
```

---

## Stratégie de recherche

```
Référence connue (DEV-/CMD-/FA-XXXX)
  → type détecté depuis préfixe
  → GET /{type}/ref/{ref} puis lignes + documents + agenda

Email connu
  → GET /thirdparties?sqlfilters=(t.email:=:'{email}')
  → si vide : GET /contacts?sqlfilters=(t.email:=:'{email}')

Nom connu
  → GET /thirdparties?sqlfilters=(t.nom:like:'%{nom}%')
  → si plusieurs résultats : présenter les options

Socid connu → requêtes parallèles
  → GET /thirdparties/{id}
  → GET /proposals?thirdparty_ids={id}
  → GET /orders?thirdparty_ids={id}
  → GET /invoices?thirdparty_ids={id}
  → GET /agendaevents?thirdparty_ids={id}

Vérification doublon avant création
  → email EN PREMIER → puis nom → puis téléphone
```

---

## Gestion des erreurs

| Code | Signification | Comportement |
|------|--------------|--------------|
| `200` + données | Succès | Traiter |
| `200` + `[]` | Non trouvé | Signaler, proposer alternatives |
| `400` | Données invalides | Afficher message Dolibarr, corriger |
| `401` | Clé API invalide | Alerter équipe, stop |
| `403` | Droits insuffisants | Alerter, vérifier profil |
| `404` | Référence inexistante | Confirmer non-existence |
| `409` | Conflit (déjà validé...) | Lire statut actuel, informer |
| `500` | Erreur serveur | Retry 1× après 3s, puis alerter |
| Timeout | Serveur hors ligne | Alerter, ne pas bloquer |

---

## Règles de sécurité

- **Toute écriture → protocole de validation obligatoire champ par champ (voir Règle d'or)**
- `CLIENT` → accès à ses pièces uniquement ; écriture restreinte (signature devis, commentaire, coordonnées) ; jamais `note_private` ; jamais données d'autres tiers
- `TEAM` → lecture complète + modifications contenu, champs perso, lignes, dates
- `ADMIN` → tout, y compris cycle de vie complet
- Ne jamais exposer la clé API, l'URL interne, les IDs bruts à un `CLIENT`
- Résultats multiples ambigus → présenter les options, ne pas choisir
- **Après toute écriture → toujours relire CHAQUE champ modifié et confirmer la valeur enregistrée**

---

## Présentation à l'utilisateur

### Résumé modification champ par champ (avant confirmation)
```
✏️  MODIFICATION DOLIBARR
Objet   : Devis DEV-2026-089 — Agence Exemple
Action  : Mise à jour descriptif technique + date de livraison

Champ 1 — Descriptif technique (ligne 3, special_code=104778)
  AVANT : "Impression offset 4 couleurs, 135g couché mat, pelliculage brillant,
           format A4, 8pp, 500 ex." (142 car.)
  APRÈS : "Impression numérique HD, papier recyclé 120g, pelliculage soft touch,
           format A4, 8pp, 300 ex." (140 car.)

Champ 2 — Date de livraison
  AVANT : 15/03/2026
  APRÈS : 28/03/2026

Champs inchangés : note_public, note_private, remise_percent, conditions de paiement

✅ Confirmer les modifications ? (oui / non / modifier [champ] pour ajuster)
```

### Confirmation après écriture (champ par champ)
```
✅ DEV-2026-089 mis à jour — 2 champs modifiés.

Champ 1 — Descriptif technique (ligne 3)
  → Valeur enregistrée : "Impression numérique HD, papier recyclé 120g..." ✓

Champ 2 — Date de livraison
  → Valeur enregistrée : 28/03/2026 ✓
```

### Action cycle de vie
```
🔄 ACTION CYCLE DE VIE
Pièce  : DEV-2026-089 — Agence Exemple
Action : Valider le devis (brouillon → validé)

⚠️  Cette action génèrera le PDF et notifiera Dolibarr.
✅ Confirmer la validation ? (oui / non)
```

### Versionnement
```
📋 CLONE — DEV-2026-089
Nouveau devis créé : DEV-2026-095
Origine mentionnée en note interne. Statut : brouillon.
```

---

## Exemples

### Modifier la note publique d'un devis
> "Ajoute une note sur DEV-2026-089 : 'BAT validé le 25/03'"
→ GET devis → afficher avant/après → confirmer → PUT `/proposals/{id}` body `{note_public: "..."}`

### Enrichir un champ personnalisé
> "Mets le nom de projet 'Catalogue Été 2026' sur DEV-2026-089"
→ GET devis → PUT `array_options.options_fhp_project_name` → confirmer → vérifier

### Modifier le descriptif technique d'une ligne
> "Mets à jour le descriptif technique du DEV-2026-089"
→ GET lignes → trouver `special_code=104778` → afficher avant/après → PUT ligne

### Valider une commande
> "Valide la commande CMD-2026-045"
→ GET commande (vérifier statut=0) → confirmer → POST `/orders/{id}/validate`

### Cloner un devis
> "Crée une v2 du DEV-2026-089"
→ GET devis + lignes → POST nouveau devis → POST lignes → afficher nouvelle ref

### Refuser un devis avec motif
> "Refuse le DEV-2026-012, motif : hors budget client"
→ GET devis → confirmer → POST `/proposals/{id}/refuse` body `{comment: "hors budget client"}`

### Annuler une commande
> "Annule CMD-2026-032"
→ GET commande → confirmer (irréversible) → PUT `{statut: -1}`

### Signature d'un devis par le CLIENT
> "J'accepte le devis DEV-2026-089"
→ Vérifier profil CLIENT + que le devis appartient à son socid → vérifier statut=1
→ Afficher avant/après champ par champ (statut : `1=validé` → `2=signé`)
→ Confirmer → POST `/proposals/{id}/close` body `{status:2}`

### CLIENT modifie ses coordonnées
> "Change mon email pour contact@nouveau.fr"
→ Vérifier profil CLIENT → GET tiers (son socid uniquement)
→ Afficher avant/après : `email` AVANT / APRÈS
→ Confirmer → PUT `/thirdparties/{socid}` body `{email: "contact@nouveau.fr"}`

---

## Notes importantes
- Dates en **timestamp Unix** → toujours convertir en `JJ/MM/AAAA`
- Statuts entiers → toujours traduire en label français
- Descriptifs dans lignes `product_type=9`, champ `description` → texte complet
- `note_private` strictement interne → jamais affiché à un `CLIENT`
- **Toute écriture sans confirmation préalable est INTERDITE**
- Après écriture → toujours relire pour vérification
- Clonage = procédure manuelle (POST devis + POST lignes une par une)
- Préfixes références : `DEV-`=devis · `CMD-`=commande · `FA-`=facture
- Appelé **avant toute création** pour éviter les doublons
- Alimente le skill `mémoire-client` avec les données récupérées
