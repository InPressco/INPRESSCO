---
name: validation-qc-inpressco
description: >
  Skill de validation et contrôle qualité pour In'Pressco. Déclencher SYSTÉMATIQUEMENT avant tout envoi au client, tout dépôt en base de données, ou toute transmission de document. Déclencher aussi dès qu'un devis est créé ou modifié dans Dolibarr, même sans intention d'envoi immédiat. Cas d'usage : vérifier la cohérence d'un devis à la création, à la modification ou avant envoi ; contrôler qu'un email ne contient pas d'informations confidentielles ; valider qu'un fichier est complet avant archivage ; vérifier la cohérence entre un brief et le devis produit. Utiliser aussi quand l'utilisateur dit "vérifie avant d'envoyer", "contrôle ce devis", "est-ce que c'est bon", "valide avant de déposer", "je viens de créer le devis", "j'ai modifié le devis". Ce skill est le dernier filtre avant toute action irréversible.
---

# Validation / QC — In'Pressco

## Rôle
Agir comme dernier filtre de qualité avant toute action irréversible — envoi d'email, dépôt de document, mise à jour Dolibarr — mais aussi comme contrôle préventif dès la création ou modification d'un devis. Détecter les incohérences, les données manquantes, les informations confidentielles mal placées, et les erreurs avant qu'elles n'atteignent le client ou les bases de données.

---

## Moments de déclenchement sur un devis

| Moment | Contrôles appliqués |
|--------|-------------------|
| **Création** d'un devis | Grille devis complète (structure, tiers, montants, descriptif) |
| **Modification** d'un devis existant | Grille devis complète + vérification que les changements restent cohérents |
| **Avant envoi** au client | Grille devis (envoi) + contrôle email + point lien Dolibarr / PJ |

---

## Périmètre de contrôle

### 1. Contrôle devis (création, modification, envoi)

| Point de contrôle | Vérification | Sévérité |
|-------------------|-------------|----------|
| Tiers | Nom, email et adresse corrects et complets | BLOQUANT |
| Référence | Format DEV-AAAA-NNN valide | BLOQUANT |
| Statut | Devis validé (statut ≥ 1) avant génération PDF | BLOQUANT |
| Montants | Total HT / TVA / TTC cohérents, aucun montant à 0 sur lignes prix | BLOQUANT |
| Descriptif | Lignes descriptives présentes (special_code 104777 et 104778) | BLOQUANT |
| Date livraison | Date renseignée et dans le futur | BLOQUANT |
| Nom projet | Champ `options_fhp_project_name` renseigné | AVERTISSEMENT |
| Conditions | Conditions de paiement et mode de règlement renseignés | AVERTISSEMENT |
| Modèle PDF | `azur_fp` sélectionné | AVERTISSEMENT |
| Signature | Collaborateur assigné identifié | AVERTISSEMENT |
| **Lien / PJ devis** | Lien Dolibarr cliquable dans le corps de l'email OU devis en PJ PDF — au moins l'un des deux doit être présent avant envoi | BLOQUANT (si aucun des deux) |

#### Règle lien Dolibarr / PJ — logique de contrôle
```
Si email contient un lien Dolibarr cliquable → OK
Si email contient une PJ PDF du devis       → OK
Si les deux sont présents                   → OK (redondance acceptable)
Si aucun des deux                           → BLOQUANT : "Aucun accès au devis fourni au client (ni lien ni PJ)"
```
> Ce point ne s'applique qu'au moment de l'envoi — pas lors de la création ou modification.

### 2. Contrôle email avant envoi

| Point de contrôle | Vérification |
|-------------------|-------------|
| Destinataire | Email correct, pas d'erreur de tiers |
| Informations confidentielles | Aucune note_private, aucun tarif fournisseur, aucune marge |
| Dates | Aucune date non vérifiée dans Dolibarr |
| Références | Références Dolibarr correctes si mentionnées |
| Pièce jointe | PJ annoncée dans le texte → vérifier qu'elle est bien attachée |
| Signature | Phrase Paola présente et nom correct |
| Promesses | Aucun engagement ferme non validé par l'équipe |
| Impayés | Aucune mention des impayés dans un email commercial |

### 3. Contrôle fichier avant archivage

| Point de contrôle | Vérification |
|-------------------|-------------|
| Nom | Conforme à la convention `TYPE_TIERS_REF_DATE_VERSION.EXT` |
| Extension | Extension cohérente avec le type de document |
| Taille | Fichier non vide (taille > 0) |
| Destination | Dolibarr ou base images — cohérent avec le type |
| Tiers associé | Socid résolu et valide |
| Référence | Référence Dolibarr existante si applicable |
| Doublon | Vérification faite (pas d'écrasement silencieux) |

### 4. Contrôle cohérence brief ↔ devis

| Point de contrôle | Vérification |
|-------------------|-------------|
| Format | Format du devis = format du brief |
| Quantité | Quantité(s) du devis = quantité(s) demandées |
| Support | Support du devis cohérent avec la demande |
| Finitions | Finitions demandées toutes présentes dans le devis |
| Délai | Date de livraison du devis compatible avec la demande |
| Tiers | Devis associé au bon tiers |

---

## Niveaux de sévérité

| Niveau | Description | Comportement |
|--------|-------------|--------------|
| `BLOQUANT` | Erreur qui empêche l'action (email sans destinataire, devis statut 0, info confidentielle, aucun accès au devis fourni) | Stopper l'action, signaler, corriger avant de continuer |
| `AVERTISSEMENT` | Anomalie qui devrait être corrigée mais n'empêche pas l'action | Signaler, demander confirmation pour continuer |
| `INFO` | Observation non critique | Afficher en note, continuer sans bloquer |

---

## Processus de contrôle

### Étape 1 — Identifier l'objet et le moment
```
Devis créé     → contrôle devis (création)
Devis modifié  → contrôle devis (modification)
Devis à envoyer → contrôle devis (envoi) + contrôle email + point lien/PJ
Email sortant  → contrôle email
Fichier à archiver → contrôle fichier
Brief vs devis → contrôle cohérence
```

### Étape 2 — Appliquer la grille de contrôle correspondante
Vérifier chaque point de la liste. Pour chaque anomalie détectée : noter le niveau de sévérité et le détail.

### Étape 3 — Décision
```
0 BLOQUANT  → OK, procéder (avec avertissements affichés si présents)
≥ 1 BLOQUANT → Stopper, afficher les erreurs, corriger avant de continuer
```

### Étape 4 — Rapport de contrôle
Toujours afficher un rapport avant de valider ou bloquer.

---

## Schéma JSON de sortie

```json
{
  "controle": {
    "objet": "devis_creation | devis_modification | devis_envoi | email | fichier | coherence_brief_devis",
    "ref": "DEV-2026-089",
    "resultat": "OK | BLOQUÉ | AVERTISSEMENT",
    "nb_bloquants": 0,
    "nb_avertissements": 1,
    "nb_infos": 2
  },
  "anomalies": [
    {
      "niveau": "AVERTISSEMENT",
      "point": "date_livraison",
      "message": "Date de livraison dans 2 jours — délai très court, confirmer avec la production"
    },
    {
      "niveau": "INFO",
      "point": "note_projet",
      "message": "Champ nom projet renseigné : 'Catalogue printemps 2026'"
    }
  ],
  "action_recommandee": "Confirmer le délai avec Nicolas avant envoi"
}
```

---

## Présentation à l'utilisateur

### Contrôle OK
```
✓ Contrôle qualité — Aucune anomalie bloquante

Devis DEV-2026-089 prêt à envoyer.
⚠ Avertissement : délai livraison très court (2 jours) — confirmer avec production
ℹ Date de création : 26/03/2026 · Modèle PDF : azur_fp · Accès devis : lien Dolibarr présent

[Envoyer quand même] [Vérifier avec production d'abord]
```

### Contrôle BLOQUÉ
```
🚫 Contrôle qualité — 2 erreurs bloquantes détectées

Impossible d'envoyer avant correction :

1. [BLOQUANT] Aucun accès au devis fourni au client — ni lien Dolibarr ni PJ PDF attachée
2. [BLOQUANT] Pièce jointe annoncée dans le texte mais non attachée

⚠ Avertissement : nom de projet non renseigné dans Dolibarr

→ Corriger les erreurs bloquantes avant de continuer.
```

---

## Notes importantes
- Ce skill est **appelé automatiquement** par les skills `reponse-client`, `generation-pdf` et `archiveur` avant toute action finale
- Il est également déclenché **dès la création ou modification** d'un devis dans Dolibarr, sans attendre l'envoi
- Il peut aussi être **appelé manuellement** par l'équipe pour vérifier un document avant de le traiter
- En cas de doute sur une information confidentielle → **toujours bloquer** et demander confirmation
- Les contrôles sont **non modifiables** par le client — profil `CLIENT` ne peut pas passer outre un BLOQUANT
- Ce skill ne corrige pas les erreurs — il les détecte et les signale. La correction revient à l'utilisateur ou au skill approprié
- **Lien vs PJ** : les deux modes de transmission du devis sont acceptés selon le contexte client. L'important est qu'au moins l'un soit présent avant envoi.
