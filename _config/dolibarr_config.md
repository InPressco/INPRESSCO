# dolibarr_config.md — Configuration Dolibarr (Layer 3)

## Connexion
```
BASE_URL = https://in-pressco.crm.freshprocess.eu/api/index.php
HEADER : DOLAPIKEY: {DOLIBARR_API_KEY}  ← depuis .env
```

## IDs métier fixes

| Constante | Valeur | Signification |
|---|---|---|
| SOCID_INCONNU | 16 | "CLIENT A RENSEIGNER" |
| USER_OWNER_ID | 166 | Utilisateur propriétaire des événements agenda |
| PRODUCT_IMPRESSION | 35700 | Produit Dolibarr pour les lignes de prix |
| COND_REGLEMENT_BAT | 15 | À validation du BAT |
| MODE_REGLEMENT_VIREMENT | 2 | Virement bancaire |
| MODEL_PDF | azur_fp | Template PDF du devis |

## Codes lignes de devis

| product_type | Signification |
|---|---|
| 0 | Produit/service (avec prix) |
| 9 | Ligne texte/titre (sans prix) |

| special_code | Usage |
|---|---|
| 104777 | Ligne contexte client (surlignée) |
| 104778 | Ligne descriptif technique |

## Endpoints utilisés

### Tiers
- `GET /thirdparties?sqlfilters=(t.email:=:'email@domaine.com')`
- `GET /thirdparties?sqlfilters=(t.nom:like:'%NomSociete%')`
- `POST /thirdparties`

### Devis
- `POST /proposals`
- `POST /proposals/{id}/validate`
- `POST /proposals/{id}/settodraft`
- `GET /proposals/ref/{ref}?contact_list=1`

### Documents
- `POST /documents/upload`

### Agenda
- `POST /agendaevents`
