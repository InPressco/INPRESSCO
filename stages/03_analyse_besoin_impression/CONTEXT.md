# CONTEXT.md — Stage 3 : Analyse besoin impression

## Rôle de ce stage
Analyser le corps du mail client pour en extraire les composants d'impression
sous forme structurée, avec calculs d'imposition et score qualité.

## Inputs

### Layer 3 (référence — stable)
- `../../_config/openai_config.md` — Modèle, paramètres
- `../../shared/regles_impression.md` — Prompt complet + schéma JSON attendu
- `references/grilles_impression.md` — Formats standards, grammages, finitions

### Layer 4 (working artifact)
- `../02_analyse_client/output/result.json` — Contexte client + email body

## Process

### Étape 1 — Extraction composants par IA
Appeler GPT-4.1-mini avec le prompt de `../../shared/regles_impression.md`.
Analyser `source_data.email_body` du stage 2.

Extraire pour chaque composant :
- `intitule_maitre` : Nom du groupe (ex: "Brochure A5 recto-verso")
- `produit` : Type de produit (ex: "Couverture", "Intérieur")
- `nombre_pages`, `format_ferme_mm`, `format_ouvert_mm`
- `type_impression` : Recto / Recto-verso / Quadrichromie / Bichromie...
- `support_grammage` : Ex: "Couché mat 135g"
- `type_finition` : Ex: "Pelliculage mat", "Vernis sélectif"
- `type_reliure`, `conditionnement`, `franco_port`
- `quantite`

### Étape 2 — Calculs d'imposition
Pour chaque composant, calculer via `../../scripts/calcul_imposition.py` :
- `IMPOSITION_BRUTE_700x1000` : poses_total, calcul_feuilles
- `IMPOSITION_BRUTE_330x480` : poses_total, calcul_feuilles

### Étape 3 — Score qualité
Évaluer chaque composant :
- `score_sur_10` : Score de complétude/cohérence des données
- `alertes` : Liste des problèmes détectés (ex: "Format non standard", "Grammage non précisé")

### Étape 4 — Contexte global
Extraire :
- `synthese_contexte` : Résumé de la demande pour la ligne de devis
- `date_livraison_souhaitee` : Date ISO si mentionnée, sinon null

## Outputs
Écrire dans `output/result.json` :
```json
{
  "synthese_contexte": "Brochure commerciale pour salon de printemps...",
  "date_livraison_souhaitee": "2025-03-15",
  "composants_isoles": [
    {
      "intitule_maitre": "Brochure A5",
      "produit": "Couverture",
      "nombre_pages": 4,
      "format_ferme_mm": {"largeur": 148, "hauteur": 210},
      "format_ouvert_mm": {"largeur": 296, "hauteur": 210},
      "type_impression": "Quadrichromie recto-verso",
      "support_grammage": "Couché brillant 300g",
      "type_finition": "Pelliculage brillant",
      "type_reliure": "Agrafage",
      "conditionnement": "Cartons de 250",
      "franco_port": "Franco",
      "quantite": 1000,
      "IMPOSITION_BRUTE_700x1000": {
        "poses_total": 8,
        "calcul_feuilles": {"feuilles": 125}
      },
      "IMPOSITION_BRUTE_330x480": {
        "poses_total": 4,
        "calcul_feuilles": {"feuilles": 250}
      },
      "SCORE_DEVIS": {
        "score_sur_10": 8.5,
        "alertes": ["Finition de dos non précisée"]
      },
      "TRACE": "Extrait depuis : 'brochure A5 4 pages couv 300g pelliculée...'"
    }
  ],
  "socid": 30128,
  "nom_projet": "Catalogue printemps 2025"
}
```

## Vérification humaine recommandée ⭐
**Point de contrôle critique** — vérifier avant de créer le devis :
- [ ] Chaque composant a un `intitule_maitre` logique
- [ ] Les formats sont cohérents (fermé / ouvert)
- [ ] Les quantités correspondent au mail
- [ ] Les alertes ont été traitées ou acceptées
- [ ] `score_sur_10` < 6 → envisager de demander des précisions au client

Si correction : modifier `output/result.json` directement.
