# outlook_config.md — Configuration Outlook (Layer 3)

## Connexion
```
API  : Microsoft Graph v1.0
BASE : https://graph.microsoft.com/v1.0/users/contact@in-pressco.com
AUTH : OAuth2 client credentials (Azure AD — app inpressco-claude)
```

## Arborescence des dossiers Outlook

```
contact@in-pressco.com
│
├── Boîte de réception              ← INBOX (emails bruts, non routés)
│
├── >> FLUX INPRESSCO               ← PENDING — DROP ZONE PIPELINE ⭐
│   │   Règle Outlook : tous les emails entrants → ici
│   │   Glisser-déposer : tout élément à traiter par Claude
│   │   s01 lit depuis ce dossier (filtre [Traité] + [Routé-])
│
├── >> COMMERCE                     ← COMMERCE
│   ├── PRO-2026-0001 — NomClient   (créé automatiquement par s11)
│   ├── PRO-2026-0002 — NomClient
│   └── ...
│
├── >> ETUDE PROJET                 ← ETUDE
│   ├── PRO-XXXX — NomClient        (sous-dossiers Flux B)
│   └── ...
│
├── >> GENERAL                      ← GENERAL
│
└── >> ADMIN                        ← ADMIN
    └── [Traité-FOURNISSEUR] ...    (emails fournisseurs archivés par Flux C)
```

## IDs dossiers (découverts le 28/03/2026)

| Constante config.py              | Nom Outlook           | ID Graph API |
|----------------------------------|-----------------------|--------------|
| `OUTLOOK_FOLDER_INBOX`           | Boîte de réception    | `AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAAAAAEMAAA=` |
| `OUTLOOK_FOLDER_FLUX_INPRESSCO`  | >> FLUX INPRESSCO     | `AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAGUrtifAAA=` |
| `OUTLOOK_FOLDER_COMMERCE`        | >> COMMERCE           | `AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRaAAA=` |
| `OUTLOOK_FOLDER_ETUDE`           | >> ETUDE PROJET       | `AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRZAAA=` |
| `OUTLOOK_FOLDER_GENERAL`         | >> GENERAL            | `AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRYAAA=` |
| `OUTLOOK_FOLDER_ADMIN`           | >> ADMIN              | `AAMkADE4NDcwOGRlLWVlNDItNDQ1Yy1hZmViLTBlOTxxZmYzYTQxZAAuAAAAAACxjFZsKT7nSbdhTw69f086AQA4XSMgZpzwS5Qsw_mqPyuHAAHD9iRXAAA=` |
| `OUTLOOK_FOLDER_PENDING`         | >> FLUX INPRESSCO     | alias de `OUTLOOK_FOLDER_FLUX_INPRESSCO` |
| `OUTLOOK_FOLDER_DEVIS`           | >> COMMERCE           | alias de `OUTLOOK_FOLDER_COMMERCE` |
| `OUTLOOK_FOLDER_DEVIS_FOURNISSEUR`   | >> ADMIN (défaut) | configurable via `.env` |
| `OUTLOOK_FOLDER_FACTURE_FOURNISSEUR` | >> ADMIN (défaut) | configurable via `.env` |

## Règle Outlook recommandée

Pour que le pipeline capte tous les emails automatiquement :
```
Condition  : tout email reçu dans la boîte principale
Action     : déplacer vers >> FLUX INPRESSCO
```
Sans cette règle : glisser-déposer manuel dans >> FLUX INPRESSCO.

## Destination des emails après traitement

| Catégorie routing  | Flux | Destination finale           | Marquage sujet           |
|--------------------|------|------------------------------|--------------------------|
| `NEW_PROJECT`      | A    | COMMERCE / sous-dossier devis | `[Traité] ...`           |
| `PROJECT_UPDATE`   | B    | reste dans ETUDE              | `[Traité] ...`           |
| `SUPPLIER_QUOTE`   | C    | ADMIN (ou DEVIS_FOURNISSEUR)  | `[Traité-FOURNISSEUR] ...` |
| `SUPPLIER_INVOICE` | C    | ADMIN (ou FACTURE_FOURNISSEUR)| `[Traité-FOURNISSEUR] ...` |
| Autres catégories  | —    | reste dans FLUX_INPRESSCO     | `[Routé-{cat}] ...`      |

## Filtres OData utilisés par s01

```
# Emails à traiter (ni traités ni routés)
not(startswith(subject,'[Traité]')) and not(startswith(subject,'[Routé-'))

# Flux B — emails dans les sous-dossiers ETUDE (construit dynamiquement)
not(startswith(subject,'[Traité]')) and (parentFolderId eq '{id1}' or ...)
```

## Conventions d'archivage

- Sous-dossier devis créé par s11 : `{ref_devis} — {soc_nom}` (sous >> COMMERCE)
- Email traité (Flux A) : `[Traité] {sujet original}`
- Email traité (Flux C) : `[Traité-FOURNISSEUR] {sujet original}`
- Email non routé : `[Routé-{CATEGORIE}] {sujet original}` — reste dans FLUX_INPRESSCO

## Champs récupérés sur chaque email (Graph API)

```
id, subject, bodyPreview, body.content, body.contentType
sender, from, toRecipients
receivedDateTime, hasAttachments, parentFolderId
```
