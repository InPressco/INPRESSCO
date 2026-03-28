---
name: agent-acheteur-inpressco
description: >
  Agent acheteur pour In'Pressco — génère des demandes de prix adaptées au métier de chaque sous-traitant récurrent.
  Déclencher SYSTÉMATIQUEMENT dès qu'une demande de tarification fournisseur est nécessaire : "demande de prix", "consulte le façonnier", "contacte le papetier", "on a besoin d'un tarif fournisseur", "demande un devis à", "envoie une consultation à", "on doit acheter du papier", "combien ça coûte chez le fournisseur", "lance une consultation", "RFQ", "appel d'offre sous-traitant".
  Déclencher aussi automatiquement quand un devis Dolibarr est en cours et qu'une prestation externe est identifiée (façonnage, papier spécial, impression offset, dorure, sérigraphie).
  Ce skill tire les informations du devis Dolibarr correspondant, identifie le(s) fournisseur(s) concerné(s), adapte le vocabulaire métier à chaque type de sous-traitant, et génère un email de demande de prix prêt à envoyer — avec toujours 2 à 3 variantes de quantité.
---

# Agent Acheteur In'Pressco

Génère des demandes de prix professionnelles et adaptées au vocabulaire métier de chaque sous-traitant récurrent d'In'Pressco.

---

## Workflow général

```
1. IDENTIFIER le contexte (devis Dolibarr ou brief chat)
2. EXTRAIRE les spécifications techniques du projet
3. CLASSIFIER le type de sous-traitant nécessaire
4. CHARGER le template métier correspondant
5. CONSTRUIRE les quantités (2-3 paliers)
6. DÉTECTER l'urgence → ajouter deadline si besoin
7. IDENTIFIER le fournisseur (Dolibarr ou utilisateur)
8. GÉNÉRER l'email de demande de prix
9. PROPOSER à l'envoi via reponse-client ou SMTP
```

---

## Étape 1 — Récupérer les infos du devis Dolibarr

Si un numéro de devis ou de commande est mentionné, utiliser **dolibarr-query-inpressco** pour lire :
- Les lignes du devis (description, quantité, finition, format, support)
- Le nom du client et la référence projet
- La date de livraison souhaitée → détecter urgence (< 5 jours ouvrés = urgent)

Si aucune référence Dolibarr n'est donnée, demander à l'utilisateur les spécifications minimales selon le type de sous-traitant (voir templates ci-dessous).

---

## Étape 2 — Classifier le type de sous-traitant

Analyser les lignes du devis ou la demande pour identifier :

| Mots-clés détectés | Type sous-traitant | Template à utiliser |
|---|---|---|
| reliure, pliage, découpe, perforation, assemblage, agrafage, spirale, dos carré | **Façonnier** | → `references/faconnier.md` |
| papier, feuilles, grammage, rame, bobine, support, couché, offset, mat, brillant | **Papetier** | → `references/papetier.md` |
| impression, tirage, numérique, offset, CMJN, quadri, recto-verso, Indigo | **Imprimeur** | → `references/imprimeur.md` |
| dorure, sérigraphie, gravure, vernis sélectif, embossage, estampage, UV | **Finisseur** | → `references/finisseur.md` |

Si le projet nécessite plusieurs types : générer **une demande par fournisseur**.

---

## Étape 3 — Construire les paliers de quantité

Toujours proposer **2 à 3 paliers de quantité** autour de la quantité cible du devis :

- Si quantité devis = Q → paliers recommandés : **Q×0.5 / Q / Q×2**
- Adapter aux paliers logiques du métier (ex : 250 / 500 / 1000 pour l'imprimerie)
- Mentionner explicitement les 3 paliers dans la demande

---

## Étape 4 — Détecter l'urgence

Calculer le délai entre aujourd'hui et la date de livraison client :
- **≤ 5 jours ouvrés** → ajouter en en-tête : *"Ce projet est urgent — merci de nous revenir avant le [date J-1 ouvré]."*
- **6–10 jours ouvrés** → ajouter : *"Merci de nous confirmer votre disponibilité sous 48h."*
- **> 10 jours ouvrés** → pas de mention d'urgence

---

## Étape 5 — Identifier le fournisseur

**Si l'utilisateur précise le fournisseur** → utiliser ce nom directement.

**Si non précisé** → interroger Dolibarr via **dolibarr-query-inpressco** :
```
Rechercher les tiers de type "fournisseur" avec tag correspondant au type détecté
(ex: tag "façonnier", "papetier", "imprimeur", "finisseur")
```
Proposer à l'utilisateur le(s) fournisseur(s) trouvés et demander confirmation avant génération.

---

## Étape 6 — Générer l'email

Charger le fichier de référence du type de sous-traitant concerné (voir `references/`).

### Structure email universelle

```
Objet : Demande de prix — [Type produit] — Réf. [Réf devis Dolibarr] — [Nom client ou projet]

Bonjour [Prénom contact fournisseur si connu, sinon "Madame, Monsieur"],

Dans le cadre d'un projet pour l'un de nos clients, nous souhaitons vous consulter
pour la prestation suivante :

[BLOC TECHNIQUE MÉTIER — voir fichier references/ correspondant]

Merci de nous indiquer vos tarifs pour les quantités suivantes :
- [Palier 1] : _____ € HT
- [Palier 2] : _____ € HT
- [Palier 3] : _____ € HT

[BLOC URGENCE si détectée]

Pourriez-vous également nous confirmer votre délai de production ?

Dans l'attente de votre retour, nous restons disponibles pour tout complément d'information.

Cordialement,
[Signature In'Pressco standard]
```

---

## Étape 7 — Validation et envoi

1. Afficher l'email généré à l'utilisateur pour relecture
2. Demander confirmation : *"Voulez-vous que j'envoie cet email à [nom fournisseur] ?"*
3. Si confirmé → utiliser **reponse-client-inpressco** pour l'envoi
4. Logger l'envoi en note interne sur le devis Dolibarr via **dolibarr-query-inpressco** :
   `"Consultation fournisseur [type] envoyée à [nom fournisseur] le [date]"`

---

## Fichiers de référence

Lire le fichier correspondant au type de sous-traitant détecté :

- `references/faconnier.md` — Vocabulaire et champs façonnage
- `references/papetier.md` — Vocabulaire et champs papier/support
- `references/imprimeur.md` — Vocabulaire et champs impression
- `references/finisseur.md` — Vocabulaire et champs finition spéciale

---

## Règles de qualité

- **Jamais de jargon inadapté** : ne pas parler de "feuilles" à un façonnier, ni de "reliure" à un papetier
- **Toujours 2-3 paliers de quantité** sans exception
- **Ton professionnel mais direct** : on s'adresse à des partenaires récurrents qui connaissent le métier
- **Ne jamais inventer des specs** : si une info manque, la demander à l'utilisateur avant de générer
- **Un email par fournisseur** si plusieurs types de sous-traitance nécessaires
- **Validation qualité** : passer par **validation-qc-inpressco** avant tout envoi
- **Erreur API** : activer **gestion-erreurs-inpressco** si Dolibarr est inaccessible

## Intégrations skills

| Skill | Rôle dans ce workflow |
|---|---|
| `dolibarr-query-inpressco` | Lire le devis source + identifier les fournisseurs + logger l'envoi |
| `memoire-client-inpressco` | Charger le contexte tiers fournisseur si connu |
| `reponse-client-inpressco` | Envoyer l'email après confirmation utilisateur |
| `validation-qc-inpressco` | Contrôle qualité avant envoi |
| `gestion-erreurs-inpressco` | Gestion erreurs API Dolibarr |
| `projets-artefacts-inpressco` | Archiver la demande de prix générée |
