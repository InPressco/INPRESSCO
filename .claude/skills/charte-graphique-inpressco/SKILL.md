---
name: charte-graphique-inpressco
description: >
  Skill d'extraction et de mémorisation de la charte graphique client pour In'Pressco.
  Déclencher SYSTÉMATIQUEMENT dès qu'un client fournit des éléments visuels ou descriptifs
  de son identité de marque : "voici notre charte", "nos couleurs sont...", "on utilise
  la police X", "je joins notre guide de marque", "notre logo c'est...", "charte graphique",
  "identité visuelle", "brand guidelines", "nos codes couleurs", "notre typographie",
  "voici notre logo". Déclencher aussi dès qu'un fichier joint (PDF, image, Word) semble
  être un guide de marque ou un brief visuel. Déclencher également quand Claude prépare
  un devis ou une réponse commerciale et qu'une charte client est déjà en mémoire —
  vérifier si elle doit être rechargée pour personnaliser la réponse. Ne jamais ignorer
  un élément de charte mentionné dans une conversation — toujours extraire et sauvegarder.
---

# Skill — Analyse de Charte Graphique Client

## Objectif

Extraire, structurer et mémoriser la charte graphique d'un client In'Pressco à partir
de n'importe quelle source : texte libre, PDF, image, ou fichier Word. Produire une fiche
de charte structurée + une fiche visuelle rendue, et persister les données dans Dolibarr
(note client) et en artifact Claude.

---

## Sources acceptées

| Source | Comment la traiter |
|---|---|
| **Texte libre** (email, brief, chat) | Extraire directement les éléments mentionnés |
| **PDF** (brand guidelines, brief) | Lire via skill `pdf-reading`, extraire les sections pertinentes |
| **Image** (logo, mockup, capture écran site) | Analyser visuellement : couleurs dominantes, style, typographie visible — PUIS proposer enrichissement CSS si URL identifiable |
| **Word / docx** | Lire via skill `docx`, extraire les sections pertinentes |
| **URL / site web** | Fetcher le CSS avec `web_fetch` pour extraire les valeurs exactes (voir section Enrichissement CSS) |

Si plusieurs sources sont présentes, croiser les informations et privilégier les codes exacts
(HEX, RGB, CMJN) sur les descriptions approximatives.

---

## Éléments à extraire

### 1. Couleurs
- Couleurs principales (primaires)
- Couleurs secondaires / d'accent
- Codes : HEX en priorité, puis RGB, puis CMJN si disponible
- Si pas de code exact : décrire la couleur et estimer un HEX approximatif (signaler que c'est une estimation)

### 2. Typographies
- Police(s) principale(s) : nom, graisse (bold, regular, light)
- Police(s) secondaire(s) / de corps de texte
- Si non spécifiée : noter "non renseignée"

### 3. Logo
- Description formelle (forme, icône, baseline éventuelle)
- Versions connues (fond blanc, fond coloré, monochrome)
- Règles d'usage mentionnées (zones d'exclusion, interdits)

### 4. Ton éditorial / Voix de marque
- Registre (formel, décontracté, luxe, technique, accessible…)
- Mots-clés caractéristiques
- Ce qu'il faut éviter (si mentionné)

### 5. Éléments graphiques complémentaires
- Motifs, textures, icônes récurrentes
- Style photographique (si mentionné)
- Univers visuel global (minimaliste, coloré, épuré, artisanal…)

---

## Comportement si charte incomplète

**Ne jamais bloquer.** Faire de son mieux avec ce qui est disponible :
- Extraire tout ce qui est présent
- Signaler clairement les champs manquants avec `⚠️ Non renseigné`
- Pour les couleurs sans code exact : estimer et marquer `~HEX (estimation)`
- Proposer en fin de fiche : *"Ces éléments manquants pourraient être complétés lors du prochain échange client."*

---

## Format de sortie — Double rendu

### A) Fiche texte structurée (toujours affichée)

```
── CHARTE GRAPHIQUE — [NOM CLIENT] ──────────────────

COULEURS
  Primaire 1   : [nom]  #XXXXXX  (RGB / CMJN si dispo)
  Primaire 2   : ...
  Secondaire   : ...

TYPOGRAPHIES
  Principale   : [nom police] — [graisses]
  Secondaire   : [nom police] — [graisses]

LOGO
  Description  : [texte]
  Versions     : [fond blanc / dark / mono...]
  Règles       : [zones d'exclusion, interdits...]

TON ÉDITORIAL
  Registre     : [formel / luxe / accessible...]
  Mots-clés    : [liste]
  À éviter     : [liste ou "non renseigné"]

UNIVERS VISUEL
  Style global : [description]
  Motifs/textures : [ou "non renseigné"]

CHAMPS MANQUANTS : [liste ou "Charte complète"]
──────────────────────────────────────────────────────
```

### B) Fiche visuelle (widget HTML inline)

Générer une fiche visuelle avec `show_widget` incluant :
- Palette de couleurs affichées avec leurs codes
- Nom(s) de police(s) dans leur style
- Bloc de présentation du logo (description stylisée si pas d'image)
- Ton éditorial affiché en exemple de phrase courte

---

## Persistance des données

### 1. Dolibarr — Note client
Utiliser le MCP `dolibarr-inpressco` pour :
1. Retrouver le tiers client par nom / email via `find_thirdparty`
2. Ajouter une note privée structurée sur la fiche tiers avec le contenu de la fiche texte

Format de la note Dolibarr :
```
[CHARTE GRAPHIQUE — mis à jour le JJ/MM/AAAA]
COULEURS : ...
TYPOS : ...
LOGO : ...
TON : ...
```

### 2. Artifact Claude (mémoire de session)
Sauvegarder la charte comme artifact pour qu'elle soit réutilisable dans la session en cours,
notamment par les skills `inpressco-devis`, `reponse-client-inpressco`, `ux-inpressco`.

---

## Rendu visuel — Widget HTML

Générer un widget HTML avec la structure suivante :

```
┌─────────────────────────────────────────────┐
│  LOGO / NOM CLIENT          [date extraction]│
├─────────────────────────────────────────────┤
│  PALETTE                                     │
│  [■ bloc couleur + code HEX]  x N couleurs  │
├─────────────────────────────────────────────┤
│  TYPOGRAPHIES                                │
│  Exemple de texte en police principale       │
│  Exemple de texte en police secondaire       │
├─────────────────────────────────────────────┤
│  TON ÉDITORIAL                               │
│  "Phrase exemple dans le registre de marque" │
├─────────────────────────────────────────────┤
│  UNIVERS VISUEL                              │
│  [description courte + mots-clés stylisés]  │
└─────────────────────────────────────────────┘
```

Si certains éléments sont manquants, afficher `—` dans le bloc correspondant.
Ne pas afficher de message d'erreur dans la fiche visuelle — garder le rendu propre.

---

## Enrichissement CSS — Extraction depuis un site web

### Quand déclencher
Dès que l'une de ces conditions est vraie :
- L'input est une **capture d'écran d'un site web** (URL visible dans la barre d'adresse)
- L'utilisateur **mentionne une URL** de site client
- Des couleurs ont été **estimées** (`~HEX`) et un site web est identifiable
- L'utilisateur dit "le site est X", "voilà leur site", "c'est sur leur site"

### Comportement
1. **Proposer automatiquement** : *"Je détecte une URL / un site web. Voulez-vous que je récupère les couleurs et polices exactes depuis le CSS ?"*
2. **Si oui** : fetcher le CSS du site avec `web_fetch` et en extraire les valeurs exactes
3. **Si l'URL est In'Pressco** (in-pressco.com) : le faire directement sans demander confirmation

### Procédure d'extraction CSS

```
1. web_fetch(url) sur la page principale
2. Identifier les balises <link rel="stylesheet"> et <style>
3. web_fetch() sur chaque URL de CSS externe
4. Chercher dans le CSS :
   - Variables CSS : --color-*, --primary-*, --brand-*
   - Couleurs sur : body, :root, header, nav, .btn, h1, h2, a
   - font-family sur : body, h1, h2, .heading, .title
5. Croiser avec l'analyse visuelle pour valider la cohérence
```

### Ce qu'on cherche dans le CSS

| Élément | Sélecteurs prioritaires |
|---|---|
| Couleur principale | `:root`, `body`, `header`, `.primary`, `--color-primary` |
| Couleur d'accent | `.btn`, `a`, `.accent`, `--color-accent` |
| Fond | `body { background }`, `--color-bg` |
| Police titre | `h1, h2 { font-family }`, `.heading` |
| Police corps | `body { font-family }`, `p` |

### Résultat
Remplacer les estimations `~HEX` par les valeurs exactes extraites du CSS.
Mentionner la source : `#B8976A (extrait CSS)`.
Si le CSS ne contient pas de valeurs exploitables : conserver les estimations visuelles.

---

## Workflow complet

```
INPUT (texte / PDF / image / URL / docx)
        │
        ▼
[1] Identifier les sources présentes
        │
        ▼
[2] Lire les fichiers si nécessaire
    (pdf-reading / docx / vision image)
        │
        ▼
[2b] URL détectée ou image de site web ?
     → Proposer enrichissement CSS (web_fetch)
     → Si accepté ou site InPressco : fetcher CSS
       et extraire couleurs + polices exactes
        │
        ▼
[3] Extraire les 5 catégories
    (valeurs CSS exactes prioritaires sur estimations)
        │
        ▼
[4] Afficher fiche texte structurée
        │
        ▼
[5] Générer fiche visuelle (widget HTML)
        │
        ▼
[6] Sauvegarder dans Dolibarr (note tiers via MCP)
        │
        ▼
[7] Sauvegarder en artifact Claude
        │
        ▼
[8] Signaler les champs manquants
    + proposer complétion au prochain échange
```

---

## Intégration avec les autres skills

- **`memoire-client-inpressco`** : toujours vérifier si une charte existe déjà avant d'en créer une nouvelle
- **`inpressco-devis`** : injecter la charte pour adapter les suggestions matières au positionnement visuel du client
- **`reponse-client-inpressco`** : adapter le ton de la réponse au registre éditorial extrait
- **`ux-inpressco`** : fournir la palette et les polices pour générer des composants aux couleurs du client
- **`archiveur-inpressco`** : si un fichier PDF/image de charte est fourni, l'archiver sur la fiche Dolibarr

---

## Exemple de déclencheurs

- *"Voici notre guide de marque en PDF"* → lire PDF + extraire
- *"Nos couleurs sont le bordeaux #8B1A2E et le gold #C9A84C"* → extraire direct
- *"On utilise Garamond pour les titres et Helvetica Neue pour le corps"* → extraire typos
- *"Je joins le logo de notre agence"* → analyser image + extraire couleurs / style
- *"Notre ton est haut de gamme, sobre, on évite le tutoiement"* → extraire ton éditorial
- *"Est-ce que tu as notre charte ?"* → vérifier Dolibarr + mémoire session
- *[capture d'écran avec URL visible dans la barre]* → extraire visuellement + proposer fetch CSS
- *"Voici leur site : www.client.fr"* → fetcher CSS + extraire valeurs exactes
- *"Le site c'est in-pressco.com"* → fetcher CSS directement (site InPressco, pas de confirmation requise)
