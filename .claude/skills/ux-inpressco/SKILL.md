---
name: ux-inpressco
description: >
  Skill UX Design pour In'Pressco — atelier d'impression haut de gamme (Chanel, Rolex, Dom Pérignon).
  Déclencher SYSTÉMATIQUEMENT dès qu'une demande porte sur un composant React/HTML, une spec
  d'interface, un wireframe, ou un conseil UX pour le site/app In'Pressco. Triggers directs :
  "génère la barre IA", "code le sas d'entrée", "crée l'écran de personnalisation", "fais la
  spec du flow devis", "montre le layout du hub", "design le mode Expert vs Guidé", "compose
  la barre de progression gamifiée", "comment afficher les 3 options Dolibarr". Applique
  SYSTÉMATIQUEMENT la palette (#0A0A0A, #C9A96E, #F5F0E8), la typographie (serif titres,
  sans-serif UI), les micro-interactions (transitions ≥0.4s), et l'architecture en 3 niveaux
  (L'Appel → Le Sas → L'Atelier). Produit du code complet auto-suffisant avec commentaire
  // In'Pressco en tête. Jamais de rendu SaaS générique — toujours "atelier luxe vivant".
---

# Skill — UX Design In'Pressco

## Identité du projet

In'Pressco — Atelier d'impression et de façonnage de beaux papiers.
Positionnement : entre artisan et industriel. Luxe, rareté, précision, émotion.
Clientèle : Chanel, Rolex, Dom Pérignon, chefs étoilés, maisons de luxe.
Adresse : 120 rue Molière, 73000 Chambéry — +33 4 85 01 44 38 — contact@in-pressco.com

**Concept UX central :** "Tu n'entres pas sur un site. Tu entres dans un atelier vivant."
Chaque interaction donne la sensation de progression + maîtrise + découverte.

---

## Identité de marque — Logo & Assets (CRITIQUE)

### Logo officiel — Logotype + Ligne de base
Fichier source : `InPressco-LogotypeBaseline.ai`

**Logotype :**
- Texte : `iNPRESSCO` — typo géométrique sans-serif, caps mixtes
- Particularité : `i` minuscule + `N` majuscule en tête, `P` miroir/inversé = signature visuelle unique
- Deux variantes : "Font Dynamique Brute" (légèrement plus fine) et "Font Vectorisée" (légèrement plus grasse, préférée pour l'écran)

**Baseline :**
- Texte : `IMPRIMERIE EXPÉRIENTIELLE`
- Style : lettres très espacées, light, en dessous du logotype
- Espacement lettres : ~0.25–0.3em

**Symbole / Icône :**
- Petit cercle noir avec P stylisé à l'intérieur (haut droit du logotype)
- Usage : favicon, app icon, élément standalone, watermark
- Ratio : 1:1 strict

**Esprit logo :** Moderne, typographique géométrique, précis.
→ Pas un cachet artisanal. Une marque de design contemporain haut de gamme.

### Règles d'utilisation dans les composants
- Sur fond sombre (`#0A0A0A`) : logo blanc (`#F5F0E8`) ou or (`#C9A96E`)
- Sur fond clair : logo noir (`#0A0A0A`)
- Ne jamais déformer les proportions — hauteur de baseline = ~30% hauteur logotype
- Zone de protection : équivalent hauteur du `i` tout autour
- Taille minimale logotype : 80px de large en UI

### Typographie dérivée (à utiliser dans l'interface)
- **Titres principaux :** geometric sans-serif fin, caps mixtes (ex: Futura, Aktiv Grotesk, ou DM Sans)
- **Ligne de base / étiquettes :** lettres espacées, majuscules, poids 300–400
- **Corps texte :** Inter Light ou DM Sans Regular
- ⚠️ Ne PAS utiliser de serif pour les titres — le logo est géométrique, l'UI doit l'être aussi

### Autres assets disponibles
- Sticker A5 (fond tramé de points, cachet sceau circulaire séparé)
- Sticker rond 3×3 cm (version sceau circulaire — asset secondaire distinct du logotype)
- Papier en-tête : logotype en filigrane + coordonnées bas de page
- Modèle : emblème circulaire en filigrane gris clair

### Ton graphique global
- Noir dominant : `#0A0A0A` / `#111111`
- Blanc pur pour le logo sur fond sombre (`#FFFFFF`) ou ivoire chaud (`#F5F0E8`) pour les textes
- Or `#C9A96E` : accent ponctuel uniquement — jamais dominant
- Géométrique, épuré, fort contraste
- Ambiance : studio de design haut de gamme — moderne, pas vintage

---

## Architecture de l'interface (référence obligatoire)

### Les 3 niveaux d'entrée

| Niveau | Nom | Contenu |
|--------|-----|---------|
| 0 | L'Appel | Vidéo 5s (geste artisan, son feutré, lumière) + CTA "Entrer dans l'atelier" |
| 1 | Le Sas | Choix d'identité : Cosmétique / Pharma / Hôtellerie / Industrie / Artisan / Institutionnel |
| 2 | L'Atelier | Hub central : plan de travail, objet en cours, barre IA permanente |

### Layout du Hub central (Niveau 2)

```
┌─────────────┬────────────────────────┬─────────────┐
│  GAUCHE     │        CENTRE          │   DROITE    │
│  Progression│    Produit en live     │  Modules    │
│  Historique │    (objet 3D/visuel)   │  Produits   │
│             │                        │  Matériaux  │
│             │                        │  Impression │
│             │                        │  Finitions  │
├─────────────┴────────────────────────┴─────────────┤
│              BARRE IA (toujours visible)            │
└─────────────────────────────────────────────────────┘
```

### Les 4 modules interactifs
1. **Produits** — type, format, quantité
2. **Matériaux** — papier, grammage, texture (avec aperçu en direct)
3. **Impression** — offset, numérique, sérigraphie
4. **Finitions** — dorure, gaufrage, vernis (avec effet lumière temps réel)

### Progression gamifiée (5 étapes)
🟢 Choix produit → 🟡 Personnalisation → 🔵 Finition → 🟣 Optimisation → 🟠 Devis

### Modes d'utilisation
- **Mode Guidé :** boutons + suggestions + parcours safe
- **Mode Expert :** prompt libre + commandes avancées (switch discret)
- **Mode Tapis Rouge :** détection volume/récurrence/secteur premium → IA plus directe, options premium

---

## Identité visuelle & ton UX

### Palette (à respecter dans tout composant)

| Token | Valeur | Usage |
|-------|--------|-------|
| Fond principal | `#0A0A0A` ou `#111111` | Noir profond atelier |
| Accent or | `#C9A96E` ou `#D4AF37` | Dorure — accent ponctuel |
| Texte primaire | `#F5F0E8` | Blanc ivoire chaud |
| Texte secondaire | `#8A7F72` | Gris fumé |
| Accent lumière | `#E8D5A3` | Reflet or doux |
| Surface carte | `rgba(255,255,255,0.04)` | Fond carte subtil |
| Bordure subtile | `rgba(201,169,110,0.2)` | Bordure or transparente |

### Typographie

- **Titres :** serif (Playfair Display, Cormorant Garamond, ou EB Garamond)
- **Corps/UI :** sans-serif fin (Inter, DM Sans, ou Helvetica Neue Light)
- **Monospace IA :** `'JetBrains Mono'` ou `'Fira Code'` (pour la barre IA)

### Principes micro-interactions (CRITIQUE)

- ❌ Aucun scroll brutal — transitions lentes (0.6s–1.2s ease)
- ✅ Hover matière → aperçu texture en temps réel
- ✅ Clic finition → effet lumière/reflet animé
- ✅ Sons subtils (optionnels, jamais intrusifs)
- ✅ Barre de progression discrète style jeu (pas de steps criards)
- ✅ Curseur personnalisé possible sur bureau

---

## Composants clés à connaître

### 1. Barre IA (composant central)
- **Style :** barre horizontale élégante, toujours visible en bas
- **Apparence :** command line premium, fond semi-transparent, bordure or subtile
- **Placeholders rotatifs :**
  - "Je veux créer un menu haut de gamme…"
  - "Optimise mon coût sur 500 exemplaires…"
  - "Propose-moi un papier noble pour un packaging luxe…"
- **Icône micro :** vocal disponible (UX luxe)
- **Suggestions intelligentes :** apparaissent en chips au-dessus de la barre

### 2. Sas d'identité (Niveau 1)
- Écran minimal, centré
- Question : "Quel est votre univers ?"
- 6 boutons : Cosmétique | Pharmaceutique | Hôtellerie & restauration | Industrie | Artisan | Institutionnel
- Impact : changement de ton IA + visuels + suggestions

### 3. Visualisation produit live
- Centre de l'écran
- Objet imprimé en cours de construction
- Réagit en temps réel aux choix de l'utilisateur
- Transitions douces (pas de rechargement)

### 4. Écran Devis final
- Titre : "Voici votre création"
- Contenu : visuel final + détails techniques + prix
- Actions : Télécharger devis | Parler à un expert | Lancer la production
- Ton : pas un PDF froid — une révélation

---

## Workflow selon le type de demande

### CAS A — Demande de composant React/HTML

1. Identifier le composant cible (barre IA, sas, hub, module, devis...)
2. Appliquer l'identité visuelle In'Pressco (couleurs, typo, micro-interactions)
3. Générer le code complet, auto-suffisant
4. Inclure les états (default, hover, focus, active, loading)
5. Ajouter un commentaire en tête : `// In'Pressco — [Nom composant] — [Date]`

### CAS B — Demande de spec / wireframe textuel

Structure obligatoire :
```
## [Nom de l'écran/composant]
### Objectif UX
### Layout (description ou ASCII)
### États & interactions
### Contenu (textes, labels, placeholders)
### Micro-interactions
### Notes d'implémentation
```

### CAS C — Conseil / critique UX

1. Analyser la demande dans le contexte In'Pressco (luxe, atelier, précision)
2. Formuler un arbitrage clair : ✅ Recommandé / ⚠️ À questionner / ❌ À éviter
3. Justifier par rapport aux 3 piliers : Atelier de Sensation / Fluidité luxe / Efficacité IA
4. Proposer une alternative si critique négative

---

## L'IA dans l'interface — Philosophie (à respecter dans tout livrable)

> L'IA est invisible mais omniprésente. Jamais intrusive. Toujours pertinente.

- ✅ Elle fait : guider, simplifier, proposer, sécuriser
- ❌ Elle ne fait PAS : spammer, jargonner, complexifier, monopoliser l'écran

**Règle d'or :** L'IA est l'interface principale — pas un gadget greffé dessus.

---

## Connexion Dolibarr (contexte technique)

Le flux IA → Dolibarr → UX est :
```
User parle → IA interprète → structure données → Dolibarr calcule → IA reformule en UX
```

Exemple : "500 menus luxe avec dorure" → IA propose 3 options (calcul Dolibarr en arrière-plan)

Dans les composants : prévoir les états de chargement (calcul en cours) et résultat (3 options affichées).

---

## Checklist avant livraison

Avant de livrer tout composant ou spécification :

- [ ] Palette In'Pressco respectée (`#0A0A0A`, `#C9A96E`, `#F5F0E8`)
- [ ] Typographie cohérente (serif titres, sans-serif UI)
- [ ] Aucune transition brutale (min 0.4s)
- [ ] Barre IA présente si écran Hub
- [ ] États complets (default, hover, actif, chargement, erreur)
- [ ] Ton visuel : atelier luxe, jamais SaaS générique
- [ ] Commentaire `// In'Pressco` en tête de code

---

## Exemples de triggers

- "Génère la barre IA du hub central"
- "Code le sas d'entrée niveau 1"
- "Crée l'écran de personnalisation en matière avec preview live"
- "Fais la spec du flow devis"
- "Montre-moi le layout du niveau 2"
- "Comment afficher les 3 options Dolibarr ?"
- "Design le mode Expert vs Guidé"
- "Compose la barre de progression gamifiée"
