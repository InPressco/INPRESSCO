# Mail Routing — In'Pressco

## Rôle
Analyser un email entrant et router vers le bon workflow parmi 8 catégories. Certains flux demandent une confirmation utilisateur, d'autres (ACTION interne) se déclenchent directement.

## Déclencheurs
Déclencher SYSTÉMATIQUEMENT dès qu'un email est collé, transféré, ou mentionné dans la conversation, ou que l'utilisateur demande "que faire de cet email", "vers quel workflow", "route cet email", "analyse cet email", "traite ce mail". Ne jamais traiter un email entrant sans utiliser ce skill.

## Règle prioritaire : détection ACTION interne
Avant toute autre analyse, vérifier le domaine expéditeur :

- Si l'expéditeur est `*@inpressco.fr` → catégorie ACTION en priorité (sauf si le contenu indique clairement une autre intention)
- Les emails internes déclenchent le workflow ACTION **sans confirmation utilisateur**

---

## Catégories de routing

| ID | Label | Workflow cible | Validation requise |
|----|-------|---------------|-------------------|
| NEW_PROJECT | Création projet / devis | Skill inpressco-devis → devis brouillon Dolibarr | ✅ Oui |
| VISUAL_CREATION | Création de visuel | Prompt Nano (génération image/visuel) | ✅ Oui |
| SUPPLIER_INVOICE | Facture fournisseur | Dolibarr — saisie facture fournisseur | ✅ Oui |
| PROJECT_UPDATE | Info / PJ sur doc existant | Dolibarr — note ou pièce sur devis/commande existant | ✅ Oui |
| SUPPLIER_QUOTE | Devis fournisseur reçu | Dolibarr — proposition fournisseur | ✅ Oui |
| PRICE_REQUEST | Demande de prix sous-traitant/fournisseur | Workflow prix externe | ✅ Oui |
| ACTION | Action interne Dolibarr | Workflow direct — voir opérations ci-dessous | ❌ Non (interne @inpressco.fr) |
| UNKNOWN | Non identifié | Traitement manuel requis | ⚠️ Alerte |

## Opérations du flux ACTION (sans validation)

- Dépôt de pièce jointe sur une commande ou un devis Dolibarr
- Création de facture Dolibarr
- Versionnement de devis
- Archivage de documents en base Dolibarr
- Toute autre action interne Dolibarr

---

## Déclencheurs par catégorie

### NEW_PROJECT
- Mots-clés : "je souhaite", "nous aimerions", "pouvez-vous nous faire un devis", "demande de devis", "brief", "nouveau projet", "commande", "je voudrais"
- Contexte : email d'un client externe, aucune référence Dolibarr existante, demande commerciale nouvelle

### VISUAL_CREATION
- Mots-clés : "logo", "visuel", "maquette", "graphisme", "illustration", "créer un fichier", "design", "charte"
- Contexte : demande de création ou modification graphique

### SUPPLIER_INVOICE
- Mots-clés : "facture", "invoice", "règlement", "à régler", "échéance", montant + nom fournisseur
- Contexte : email provenant d'un fournisseur avec document de facturation

### PROJECT_UPDATE
- **Signal fort** : présence d'une référence Dolibarr dans l'email (formats : DEV-XXXX-XXX, CMD-XXXX-XXX, FA-XXXX-XXX, ou tout numéro de devis/commande mentionné explicitement)
- Mots-clés supplémentaires : "suite à notre échange", "concernant le devis", "voici les modifications", "en complément", "je vous envoie", "ci-joint", "bon de commande", "BAT"

### SUPPLIER_QUOTE
- Mots-clés : "vous trouverez notre offre", "notre proposition", "devis ci-joint", "tarif pour"
- Contexte : email reçu d'un fournisseur ou sous-traitant contenant une offre de prix

### PRICE_REQUEST
- Mots-clés : "pourriez-vous nous faire un prix", "demande de tarif", "consultation", "nous souhaitons obtenir un devis de votre part"
- Contexte : email envoyé vers un fournisseur pour obtenir un prix (ou à traiter comme tel)

### ACTION
- **Signal fort** : expéditeur `@inpressco.fr`
- Mots-clés complémentaires : "déposer", "archiver", "créer la facture", "nouvelle version", "versionnement", "mettre à jour Dolibarr"

### UNKNOWN
- Aucun signal clair, email de courtoisie pure, contenu insuffisant, langue non reconnue

---

## Processus d'analyse

### Étape 1 — Vérifier l'expéditeur
- `@inpressco.fr` → ACTION direct, pas de confirmation, exécuter immédiatement
- Autre domaine → continuer l'analyse

### Étape 2 — Chercher une référence Dolibarr
- Présence d'un numéro de devis/commande → fort signal PROJECT_UPDATE
- Aucune référence → exclure PROJECT_UPDATE sauf signal contextuel fort

### Étape 3 — Analyser mots-clés et contexte
- Identifier la ou les catégories candidates
- Évaluer le niveau de confiance : `high` / `medium` / `low`

### Étape 4 — Décision
- 1 catégorie à confiance `high` → proposer pour confirmation
- 2+ catégories à confiance ≥ `medium` → ambiguïté, proposer toutes les options
- Aucune catégorie claire → UNKNOWN, alerte traitement manuel

---

## Schéma JSON de sortie

```json
{
  "routing": {
    "primary": "ID_CATEGORIE",
    "confidence": "high | medium | low",
    "alternatives": [
      {
        "id": "ID_CATEGORIE_ALT",
        "confidence": "medium | low",
        "reason": "Explication courte"
      }
    ],
    "ambiguous": true,
    "manual_review": false,
    "internal_action": false,
    "summary": "Résumé en 1 phrase de l'email analysé"
  },
  "proposed_actions": [
    {
      "id": "ID_CATEGORIE",
      "label": "Label lisible",
      "workflow": "Nom du workflow cible",
      "user_confirmation": "pending | yes | yes_with_attachment | no | auto"
    }
  ],
  "alert": null
}
```

Règles JSON :
- `internal_action: true` si expéditeur `@inpressco.fr` → `user_confirmation: "auto"` (pas de validation)
- `ambiguous: true` si 2+ catégories avec confiance ≥ medium
- `manual_review: true` uniquement si UNKNOWN
- `alternatives: []` si confiance high et pas d'ambiguïté

---

## Présentation à l'utilisateur

### Cas ACTION interne (pas de confirmation)
```
⚙️ Email interne @inpressco.fr détecté
Action : [opération identifiée]
→ Déclenchement automatique du workflow ACTION Dolibarr.
```

### Cas standard (avec confirmation)
```
📧 Email analysé : [résumé court]

Options de routing détectées :

▶ [1] LABEL_CATEGORIE
   Raison : ...
   → [Oui]   [Non]   [Oui + PJ/texte]

▶ [2] LABEL_CATEGORIE_ALT  ← si ambiguïté
   Raison : ...
   → [Oui]   [Non]   [Oui + PJ/texte]
```

### Cas UNKNOWN
```
⚠️ Email non classifiable — traitement manuel requis.
Motif : [explication courte]
```

L'utilisateur répond avec le numéro et son choix, ex : `"1 oui"`, `"2 oui avec PJ fichier.pdf"`.

---

## Exemples

### → NEW_PROJECT
> "Bonjour, je souhaite commander 500 flyers pour notre événement du 15 avril. Pouvez-vous nous faire un devis ?"
→ NEW_PROJECT (high) — aucune référence Dolibarr, demande commerciale nouvelle, route vers inpressco-devis

### → PROJECT_UPDATE
> "Suite à notre échange, veuillez trouver ci-joint le bon de commande pour le devis DEV-2026-089."
→ PROJECT_UPDATE (high) — référence DEV-2026-089 détectée + PJ annoncée

### → Ambiguïté PROJECT_UPDATE + NEW_PROJECT
> "Suite à notre échange de la semaine dernière, voici les nouvelles spécifications. Pouvez-vous mettre à jour le devis ?"
→ Ambiguïté — référence absente mais "mettre à jour le devis" suggère un doc existant, "nouvelles specs" peut aussi initier un nouveau devis

### → SUPPLIER_INVOICE
> "Veuillez trouver ci-joint notre facture FA-2026-042 d'un montant de 3 480 € HT pour les fournitures de mars."
→ SUPPLIER_INVOICE (high)

### → ACTION interne
> De : production@inpressco.fr — "Archiver le BAT validé sur la CMD-2026-112 svp"
→ ACTION (auto, sans confirmation) — expéditeur @inpressco.fr

### → UNKNOWN
> "Merci pour votre réponse rapide. Cordialement."
→ UNKNOWN — alerte traitement manuel

---

## Notes importantes

- NEW_PROJECT route toujours vers le skill `inpressco-devis`, pas directement vers Dolibarr
- ACTION ne demande jamais de confirmation — déclenchement direct si `@inpressco.fr`
- SUPPLIER_QUOTE = offre reçue d'un fournisseur — PRICE_REQUEST = demande envoyée à un fournisseur
- L'email peut être en français ou anglais — analyser dans les deux langues
- Ne jamais exécuter une action Dolibarr directement — ce skill route et propose uniquement (sauf ACTION interne)
