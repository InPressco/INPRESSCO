---
name: generation-pdf-inpressco
description: >
  Skill de génération de documents PDF pour In'Pressco : devis au format InPressco, bons de commande, factures, confirmations de livraison, récapitulatifs de projet, courriers. Déclencher SYSTÉMATIQUEMENT dès qu'un document formel doit être produit, envoyé ou archivé : "génère le devis en PDF", "crée le bon de commande", "produis un récapitulatif", "je veux le document prêt à envoyer", "PDF du devis", "mettre en PDF". Déclencher aussi automatiquement après création ou validation d'un devis/commande dans Dolibarr si l'utilisateur laisse entendre qu'il veut l'envoyer au client. Ce skill utilise l'API Dolibarr native (modèle azur_fp) pour les documents Dolibarr, ou génère un PDF structuré via reportlab pour les documents hors Dolibarr. Le PDF produit est systématiquement passé au skill archiveur pour classement.
---

# Génération PDF — In'Pressco

## Rôle
Produire des documents PDF finalisés, conformes à la charte graphique InPressco, prêts à être envoyés aux clients ou archivés dans Dolibarr.

---

## Types de documents

| Type | Source | Méthode |
|------|--------|---------|
| Devis client | Dolibarr — `GET /proposals/{id}/builddoc` | API Dolibarr native (modèle azur_fp) |
| Facture | Dolibarr — `GET /invoices/{id}/builddoc` | API Dolibarr native |
| Bon de commande | Dolibarr — `GET /orders/{id}/builddoc` | API Dolibarr native |
| Récapitulatif projet | Données Dolibarr + conversation | Génération structurée (reportlab) |
| Courrier client | Contenu conversation | Génération structurée (reportlab) |
| Confirmation livraison | Données commande Dolibarr | Génération structurée (reportlab) |

---

## Mode 1 — Génération via API Dolibarr (devis, factures, commandes)

Dolibarr génère nativement les PDFs avec le modèle `azur_fp` (modèle InPressco).

**Séquence complète :**
```
1. Vérifier le statut du document (devis validé = statut ≥ 1 avant génération)
2. GET /{type}/{id}/builddoc?model=azur_fp&langcode=fr_FR
   → retourne : { "success": { "code": 200 }, "file": "chemin/du/fichier.pdf" }
3. GET /documents/download?modulepart={type}&original_file={chemin}
   → retourne : fichier PDF encodé en base64
4. Décoder le base64 → fichier PDF local
5. Passer au skill archiveur-inpressco
6. Proposer l'action suivante à l'utilisateur
```

**Mapping modulepart Dolibarr :**
| Type document | Endpoint builddoc | modulepart download |
|---------------|-------------------|---------------------|
| Devis | `/proposals/{id}/builddoc` | `proposal` |
| Facture | `/invoices/{id}/builddoc` | `facture` |
| Commande | `/orders/{id}/builddoc` | `commande` |

---

## Mode 2 — Génération structurée hors Dolibarr (reportlab)

Pour les documents non gérés nativement par Dolibarr : récapitulatifs, courriers, confirmations.

**Outil : `reportlab` (Python)**
```bash
pip install reportlab --break-system-packages
```

**Structure obligatoire du PDF :**
```
┌─────────────────────────────────────────┐
│  [Logo InPressco]    InPressco           │  ← En-tête
│                      adresse, tel, email │
├─────────────────────────────────────────┤
│  À : Nom client / Société               │  ← Destinataire
│      Adresse                            │
│  Date : XX/XX/XXXX   Réf : XXX-XXXX    │
├─────────────────────────────────────────┤
│                                         │
│  [Corps du document]                    │  ← Contenu
│                                         │
├─────────────────────────────────────────┤
│  InPressco — SIRET XXXXXXXXX            │  ← Pied de page
│  www.inpressco.fr                       │
└─────────────────────────────────────────┘
```

**Charte graphique :**
- Police : Helvetica (corps), Helvetica-Bold (titres)
- Format : A4 portrait (210 × 297 mm)
- Marges : 2 cm tous côtés
- Couleurs : noir (#000000) + couleur signature InPressco pour en-têtes de section
- Taille corps : 10pt, titres : 14pt, sous-titres : 11pt

**Template Python de base (reportlab Platypus) :**
```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import date

def generer_pdf_inpressco(output_path, titre, destinataire, ref, contenu_lignes):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    styles = getSampleStyleSheet()
    s_titre = ParagraphStyle('Titre', fontName='Helvetica-Bold', fontSize=14, spaceAfter=6)
    s_normal = ParagraphStyle('Normal', fontName='Helvetica', fontSize=10, spaceAfter=4)

    story = []
    story.append(Paragraph("In'Pressco", s_titre))
    story.append(Paragraph(f"À : {destinataire}", s_normal))
    story.append(Paragraph(f"Réf : {ref} — {date.today().strftime('%d/%m/%Y')}", s_normal))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(titre, s_titre))
    story.append(Spacer(1, 0.3*cm))
    for ligne in contenu_lignes:
        story.append(Paragraph(ligne, s_normal))
    doc.build(story)
```

---

## Gestion des versions

Si un PDF pour la même référence a déjà été généré :
```
→ Vérifier via skill archiveur-inpressco si un fichier existe déjà
→ Si oui : incrémenter _v2, _v3...
→ Nommer : {TYPE}_{NomTiers}_{Ref}_{YYYYMMDD}_v{N}.pdf
   Exemple : DEV_AgenceExemple_DEV-2026-089_20260326_v2.pdf
```

---

## Processus complet

### Étape 1 — Identifier le document à générer
```
Référence Dolibarr connue → Mode 1 (API native)
Pas de référence Dolibarr → Mode 2 (génération structurée reportlab)
```

### Étape 2 — Vérifier les données
- Données complètes ? (nom tiers, adresse, contenu)
- Statut Dolibarr correct ? (devis validé avant PDF)
- Version à incrémenter ? (vérifier via archiveur)

### Étape 3 — Générer
- Mode 1 : appel API Dolibarr + récupération base64
- Mode 2 : script Python reportlab → fichier PDF local

### Étape 4 — Nommer et archiver
→ Passer **systématiquement** au skill `archiveur-inpressco` avec le fichier et ses métadonnées

### Étape 5 — Proposer l'action suivante
```
[Envoyer par email au client] → skill reponse-client-inpressco
[Archiver uniquement]
[Télécharger]
```

---

## Schéma JSON de sortie

```json
{
  "document": {
    "type": "devis | facture | commande | recapitulatif | courrier | confirmation",
    "ref": "DEV-2026-089",
    "tiers": "Agence Exemple SARL",
    "methode": "dolibarr_native | generation_structuree",
    "modele": "azur_fp | reportlab",
    "statut": "généré | erreur",
    "version": 1,
    "fichier": "DEV_AgenceExemple_DEV-2026-089_20260326_v1.pdf"
  },
  "actions_proposees": ["envoyer_email", "archiver", "telecharger"],
  "erreur": null
}
```

---

## Gestion des erreurs

| Erreur | Cause probable | Action |
|--------|---------------|--------|
| API Dolibarr 404 | Document inexistant ou mauvais ID | Vérifier via dolibarr-query-inpressco |
| API Dolibarr 403 | Statut document insuffisant (devis brouillon) | Demander validation avant génération |
| API Dolibarr 500 / timeout | Serveur indisponible | Basculer Mode 2 + alerter via notification-interne-inpressco |
| reportlab ImportError | Librairie non installée | `pip install reportlab --break-system-packages` |
| Données incomplètes | Adresse tiers manquante, ref absente | Interroger dolibarr-query-inpressco ou demander à l'utilisateur |

**Fallback Mode 2 :** si l'API Dolibarr échoue pour un devis/commande, générer un PDF structuré de secours en précisant qu'il s'agit d'une version provisoire, et relancer la génération Dolibarr dès que le serveur répond.

---

## Règles impératives

- ⛔ Ne jamais générer le PDF d'un devis non **validé** dans Dolibarr (statut < 1)
- 📁 Tout PDF généré passe **obligatoirement** par l'archiveur — jamais de PDF sans classement
- 📧 Les PDFs ne sont jamais envoyés directement — toujours via `reponse-client-inpressco`
- 🔄 En cas d'erreur API → basculer en génération structurée + notifier l'équipe
- 🔢 Toujours vérifier la version avant de nommer le fichier — ne jamais écraser un PDF existant
