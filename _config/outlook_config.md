# outlook_config.md — Configuration Outlook (Layer 3)

## Connexion
```
API : Microsoft Graph v1.0
BASE_URL : https://graph.microsoft.com/v1.0/me
AUTH : OAuth2 MSAL avec refresh token ← depuis .env
```

## IDs dossiers Outlook

| Nom | ID |
|---|---|
| DEVIS (emails entrants) | AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRZAAA= |
| >> ETUDE PROJET (sous-dossiers projets) | AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHwfJB6AAA= |

## Filtres GraphQL

### Email non traité dans DEVIS
```
not(startswith(subject,'[Traité]'))
```

### Emails dans sous-dossiers ETUDE (construit dynamiquement)
```
not(startswith(subject,'[Traité]')) and (false or parentFolderId eq '{id1}' or parentFolderId eq '{id2}' ...)
```

## Conventions d'archivage

- Nom dossier créé : `{ref_devis} - {soc_nom}`
- Préfixe mail traité : `[Traité] {subject original}`
- Dossier parent pour l'archivage : dossier `DEVIS`

## Champs récupérés sur chaque email
```
body, from, hasAttachments, parentFolderId,
receivedDateTime, sender, subject, toRecipients, bodyPreview
```
