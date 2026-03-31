# CONTEXT.md — Stage 5 : Archivage et log

## Rôle de ce stage
Uploader les pièces jointes dans Dolibarr, logger l'email dans l'agenda du devis,
renommer et déplacer le mail Outlook dans le bon dossier.

## Inputs

### Layer 3 (référence — stable)
- `../../_config/dolibarr_config.md` — Endpoints documents + agenda
- `../../_config/outlook_config.md` — IDs dossiers pour archivage

### Layer 4 (working artifact)
- `../04_construction_devis/output/result.json` — devis_ref, devis_id, email_id, soc_nom

## Process

### Étape 1 — Upload pièces jointes (si présentes)
Pour chaque pièce jointe non-inline de l'email :
```
POST /documents/upload
{
  "filename": "PJ Mail - {nom_original}",
  "modulepart": "proposal",
  "ref": "{devis_ref}",
  "filecontent": "{base64}",
  "fileencoding": "base64",
  "overwriteifexists": 1
}
```

### Étape 2 — Log email dans agenda Dolibarr
```
POST /agendaevents
{
  "type_code": "AC_OTH_AUTO",
  "userownerid": 166,
  "percentage": -1,
  "socid": {socid},
  "code": "AC_MAILRECEIVED",
  "label": "Mail reçu",
  "email_msgid": "{email_id}",
  "email_from": "{sender}",
  "email_to": "devis@in-pressco.com",
  "email_subject": "{subject}",
  "note": "{bodyPreview}",
  "elementtype": "propal",
  "fk_element": {devis_id}
}
```

### Étape 3 — Archivage Outlook
1. Créer dossier dans DEVIS : `"{devis_ref} - {soc_nom}"`
2. Renommer le message : `[Traité] {subject original}`
3. Déplacer le message dans le nouveau dossier

## Outputs
Écrire dans `output/result.json` :
```json
{
  "status": "completed",
  "devis_ref": "PRO2025-0042",
  "attachments_uploaded": 2,
  "agenda_event_id": 789,
  "outlook_folder_created": "PRO2025-0042 - Société X",
  "email_archived": true
}
```

## Pas de vérification humaine requise
Ce stage est entièrement automatisé.
En cas d'erreur, consulter les logs dans `output/errors.log`.
