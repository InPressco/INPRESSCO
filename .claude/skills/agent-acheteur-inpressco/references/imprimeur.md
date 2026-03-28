# Référence Imprimeur — Vocabulaire et champs métier

## Terminologie correcte

| À utiliser | À éviter |
|---|---|
| quadrichromie / CMJN | "4 couleurs" (peut être ambigu) |
| bichromie / monochromie | "2 couleurs / noir et blanc" |
| impression recto / recto-verso | "imprimé des deux côtés" |
| repérage | "alignement des couleurs" |
| profil ICC / gestion couleur | "correspondance couleur" |
| épreuves contractuelles (Fogra) | "BAT couleur" (distinction BAT écran / contractuel) |
| marges de fond perdu (bleed 3 mm) | "débords" |
| réserves / surimpression | termes normalisés |
| PDF/X-1a ou PDF/X-4 | "fichier PDF" (préciser la norme) |
| tirage numérique (HP Indigo / toner) | "impression numérique" |
| offset feuille / offset rotative | "impression offset" (préciser le type) |
| pantone / ton direct | "couleur spéciale" |

---

## Bloc technique impression

```
Type d'impression :
  [ ] Offset feuille
  [ ] Numérique (HP Indigo)
  [ ] Numérique (toner)
  [ ] Sérigraphie (→ voir finisseur.md)

Produit : [carte / affiche / flyer / brochure / livre / packaging / autre]

Format fini (L × H mm) :
Format de coupe avec fond perdu (L × H mm) :

Impression :
  - Recto uniquement / Recto-verso
  - Chromie : [quadrichromie CMJN / bichromie / monochromie / ton direct Pantone : ]
  - Aplats de couleur : [oui / non] — si oui, % de couverture estimé :

Support (fourni par In'Pressco / fourni par l'imprimeur) :
  - Type :
  - Grammage (g/m²) :
  - Format de feuille :

Finitions demandées (après impression) :
  - Pelliculage : [mat / brillant / soft-touch / aucun]
  - Vernis sélectif UV : [oui / non]
  - Autre :

Fichiers :
  - Format attendu : [PDF/X-1a / PDF/X-4 / autre]
  - Profil couleur : [ISO Coated v2 / autre]
  - Fonds perdus : [3 mm / autre]
  - Épreuve contractuelle demandée : [oui / non]

Quantité :
  - Palier 1 :
  - Palier 2 :
  - Palier 3 :
```

---

## Informations délai

- Date limite de réception des fichiers validés
- Date souhaitée de livraison du produit imprimé (fini ou à façonner)
- Conditionnement de livraison souhaité : [vrac / en boîtes / sur palette]

---

## Notes spécifiques

- Préciser si In'Pressco **fournit le support** ou si l'imprimeur le fournit
- Pour les produits avec tons directs Pantone : fournir la référence exacte (ex: Pantone 485 C)
- Si BAT contractuel demandé : préciser si Fogra39 ou Fogra51
- Pour les petites séries (< 100 ex) : privilégier numérique HP Indigo pour rendu quadri premium
