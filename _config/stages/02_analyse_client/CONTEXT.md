# CONTEXT.md — Stage 2 : Analyse client (Dolibarr)

## Rôle de ce stage
Rechercher le tiers dans Dolibarr ou le créer si nécessaire.
Enrichir le contexte avec le `socid` Dolibarr.

## Inputs

### Layer 3 (référence — stable)
- `../../_config/dolibarr_config.md` — URL API, clé, constantes IDs

### Layer 4 (working artifact)
- `../01_extraction_email/output/result.json` — Données client extraites

## Process

### Décision 1 — Nom et email existent ?
- Si `soc_nom` et `email` présents → tenter la recherche Dolibarr
- Sinon → utiliser le tiers générique `socid = 16` (CLIENT A RENSEIGNER)

### Décision 2 — Recherche Dolibarr
Appeler `../../scripts/dolibarr_find_client.py` :
1. Chercher par email exact
2. Si non trouvé : chercher par nom société
3. Si trouvé → retourner `socid`
4. Si non trouvé ET `creation_si_non_trouve = true` → créer le tiers
   - Payload : `name`, `client=1`, `email`, `zip`, `town`, `phone`
5. Si non trouvé ET `creation_si_non_trouve = false` → `socid = 16`

## Outputs
Écrire dans `output/result.json` :
```json
{
  "socid": 30128,
  "soc_nom": "Société X",
  "nom_projet": "Catalogue printemps 2025",
  "client_created": false,
  "source_data": "← copie du result.json du stage 1"
}
```

## Vérification humaine recommandée
Ouvrir `output/result.json` et vérifier :
- [ ] `socid` correspond au bon client
- [ ] `client_created: true` → vérifier dans Dolibarr que la fiche est correcte
- [ ] `socid = 16` → client inconnu, à renseigner manuellement si besoin
