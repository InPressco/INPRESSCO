# CONTEXT.md — Stage 1 : Extraction email

## Rôle de ce stage
Récupérer le dernier email non traité dans le dossier DEVIS Outlook
et en extraire les données client structurées par IA.

## Inputs

### Layer 3 (référence — stable)
- `../../_config/outlook_config.md` — IDs dossiers, paramètres connexion
- `../../_config/openai_config.md` — Modèle et paramètres IA
- `../../shared/regles_extraction.md` — Règles d'extraction données client

### Layer 4 (working artifact — run précédent)
- Aucun (ce stage est le premier du flux)

## Process

### Étape 1 — Récupération email
Appeler le script `../../scripts/get_email.py` qui :
- Se connecte à Outlook via Microsoft Graph API
- Récupère le dernier email du dossier DEVIS sans préfixe `[Traité]`
- Retourne : id, subject, sender, body.content, receivedDateTime, hasAttachments

### Étape 2 — Extraction données client par IA
Utiliser le modèle GPT-4.1-mini avec le prompt défini dans `../../shared/regles_extraction.md`.

Extraire :
- `soc_nom` : Nom de la société (depuis expéditeur ou corps du mail)
- `type` : "client" (constante)
- `contact_nom` / `contact_prenom` : Nom et prénom du contact
- `email` : Email du contact (null si @in-pressco.com)
- `nom_projet` : Proposition de nom de projet (OBLIGATOIRE)
- `phone`, `zip`, `town`, `address`, `siren`, `siret` : Si présents

### Étape 3 — Nettoyage
- Filtrer les données InPressco
- Si email = @in-pressco.com → chercher le nom client dans le corps du mail
- Ajouter flag `creation_si_non_trouve: false`

## Outputs
Écrire dans `output/result.json` :
```json
{
  "email_id": "...",
  "email_subject": "...",
  "email_sender": "...",
  "email_received_at": "...",
  "email_body": "...",
  "has_attachments": true,
  "client_data": {
    "soc_nom": "...",
    "type": "client",
    "contact_nom": "...",
    "contact_prenom": "...",
    "email": "...",
    "nom_projet": "...",
    "phone": null,
    "zip": null,
    "town": null,
    "address": null,
    "siren": null,
    "siret": null,
    "creation_si_non_trouve": false
  }
}
```

## Vérification humaine recommandée
Ouvrir `output/result.json` et vérifier :
- [ ] `soc_nom` correct (pas de données InPressco)
- [ ] `email` correct ou null
- [ ] `nom_projet` pertinent
- [ ] Aucune donnée inventée

Si correction nécessaire : modifier directement `output/result.json` avant de lancer le stage 2.
