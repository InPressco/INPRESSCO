# regles_impression.md — Règles d'analyse besoin impression (Layer 3)

## Prompt système IA

```
Tu es un expert en impression et en pré-presse.
Analyse la demande client et extrais les composants d'impression de façon structurée.

RÈGLES :
1. Identifier chaque composant distinct (couverture, intérieur, marque-page, etc.)
2. Regrouper les composants liés sous un même intitule_maitre
3. Calculer les formats ouverts depuis les formats fermés selon le type de reliure
4. Évaluer la complétude et la cohérence de chaque composant (score /10)
5. Lister les alertes production (données manquantes ou incohérentes)
6. Proposer une synthèse contexte courte (3-4 phrases max)
7. Extraire la date de livraison souhaitée si mentionnée

RÉPONDRE UNIQUEMENT EN JSON, sans texte supplémentaire.
```

## Schéma JSON attendu

```json
{
  "synthese_contexte": "string — résumé de la demande en 3-4 phrases",
  "date_livraison_souhaitee": "YYYY-MM-DD|null",
  "composants_isoles": [
    {
      "intitule_maitre": "string — nom du groupe (ex: Brochure A5)",
      "produit": "string — type produit (ex: Couverture, Intérieur, Marque-page)",
      "nombre_pages": "integer|null",
      "format_ferme_mm": {"largeur": "number|null", "hauteur": "number|null"},
      "format_ouvert_mm": {"largeur": "number|null", "hauteur": "number|null"},
      "type_impression": "string|null — ex: Quadrichromie recto-verso, Bichromie recto",
      "support_grammage": "string|null — ex: Couché brillant 135g",
      "type_finition": "string|null — ex: Pelliculage mat, Vernis sélectif",
      "type_reliure": "string|null — ex: Agrafage, Dos carré collé, Spirale",
      "conditionnement": "string|null — ex: Cartons de 500, Sous film",
      "franco_port": "string|null — ex: Franco, Port dû, Livraison Aix-les-Bains",
      "quantite": "integer — défaut: 1",
      "IMPOSITION_BRUTE_700x1000": {
        "poses_total": "integer|null",
        "calcul_feuilles": {"feuilles": "integer|null"}
      },
      "IMPOSITION_BRUTE_330x480": {
        "poses_total": "integer|null",
        "calcul_feuilles": {"feuilles": "integer|null"}
      },
      "SCORE_DEVIS": {
        "score_sur_10": "float|null",
        "alertes": ["string"]
      },
      "TRACE": "string|null — citation exacte depuis le mail ayant permis l'extraction"
    }
  ]
}
```

## Calcul d'imposition (référence)

### Format 700×1000mm
- Calculer combien de fois le format ouvert du composant rentre dans 700×1000
- Considérer les marges de sécurité (5mm par côté)
- `poses_total` = nombre de poses par feuille
- `feuilles` = ceil(quantite / poses_total)

### Format 330×480mm (demi-format)
- Même logique avec 330×480mm

## Alertes courantes à détecter
- Grammage non précisé
- Format non standard (non diviseur de 700×1000)
- Nombre de pages impair sans justification
- Reliure non cohérente avec nombre de pages (ex: spiral > 300 pages)
- Franco de port non précisé
- Quantité non précisée
