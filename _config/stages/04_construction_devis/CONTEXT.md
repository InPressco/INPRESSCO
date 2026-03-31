# CONTEXT.md — Stage 4 : Construction et création du devis

## Rôle de ce stage
Construire les lignes de devis à partir de l'analyse d'impression,
puis créer le devis dans Dolibarr (valider + remettre en brouillon).

## Inputs

### Layer 3 (référence — stable)
- `../../_config/dolibarr_config.md` — Endpoints, IDs produits, conditions règlement
- `../../shared/regles_devis.md` — Algorithme de construction des lignes

### Layer 4 (working artifact)
- `../03_analyse_besoin_impression/output/result.json` — Composants + socid + nom_projet

## Process

### Étape 1 — Construction des lignes
Appliquer l'algorithme de `../../shared/regles_devis.md` :

**Ligne 0 : Contexte client**
```json
{"desc": synthese_contexte, "product_type": 9, "qty": 50, "special_code": 104777, "txtva": 20}
```

**Pour chaque groupe (intitule_maitre) :**

Ligne A — Descriptif fusionné (product_type=9, special_code=104778) :
- Si plusieurs composants dans le groupe → sous-titres `<u>produit</u>`
- Specs techniques de chaque composant
- En bas : reliure, conditionnement, franco_port (depuis dernier composant uniquement)
- Pied : mention "Fichiers fournis prêt à imprimer..."

Ligne B — Prix par quantité (product_type=0, fk_product=35700, tva_tx=20) :
- Une ligne par quantité distincte dans le groupe
- `array_options.options_analysen8n` : imposition + score moyen + alertes fusionnées

### Étape 2 — Création devis Dolibarr
Appeler `../../scripts/create_devis.py` :
```json
{
  "socid": "...",
  "date": "epoch_secondes",
  "model_pdf": "azur_fp",
  "note_private": "Devis créé automatiquement, à partir du mail '...' reçu le JJ/MM/AAAA",
  "date_livraison": "epoch_ou_0",
  "cond_reglement_id": 15,
  "mode_reglement_id": 2,
  "array_options": {"options_fhp_project_name": "nom_projet"},
  "lines": [...]
}
```

### Étape 3 — Validation + remise en brouillon
1. `POST /proposals/{id}/validate` → valider pour générer la référence
2. `POST /proposals/{id}/settodraft` → remettre en brouillon pour édition

## Outputs
Écrire dans `output/result.json` :
```json
{
  "devis_id": 12345,
  "devis_ref": "PRO2025-0042",
  "socid": 30128,
  "soc_nom": "Société X",
  "nom_projet": "Catalogue printemps 2025",
  "lines_count": 7,
  "email_id": "...",
  "email_subject": "...",
  "email_received_at": "..."
}
```

## Vérification humaine recommandée ⭐
- [ ] Ouvrir le devis dans Dolibarr et vérifier les lignes
- [ ] Vérifier le nom du projet
- [ ] Vérifier les informations d'imposition dans les champs personnalisés
- [ ] Corriger manuellement dans Dolibarr si besoin
- [ ] Valider que le devis peut partir en stage 5 (archivage)
