---
name: veille-prix-inpressco
description: >
  Skill de veille tarifaire concurrentielle pour In'Pressco — imprimeur façonnier. Déclencher SYSTÉMATIQUEMENT dès qu'une comparaison de prix avec des imprimeurs en ligne est demandée ou utile : "combien ça coûterait chez Exaprint", "compare nos prix avec le marché", "le client dit que c'est moins cher ailleurs", "benchmark concurrents", "prix marché pour ce produit", "veille tarifaire", "nos concurrents proposent combien pour ça", "est-ce qu'on est compétitif". Déclencher aussi automatiquement lors de la validation d'un devis InPressco (après calcul-tarif-inpressco) pour valider le positionnement, et lors d'un brief client avec budget flou pour ancrer les fourchettes sur le marché réel. Ce skill scrape et analyse les prix en ligne de Exaprint, Onlineprinters et Pixartprinting, puis produit un tableau comparatif avec le tarif InPressco intégré pour guider la décision commerciale.
---

# Veille Prix — In'Pressco

## Rôle

Rechercher, collecter et comparer les prix pratiqués par les principaux imprimeurs en ligne (Exaprint, Onlineprinters, Pixartprinting) pour un produit donné, puis les mettre en regard du tarif InPressco afin de valider le positionnement concurrentiel et guider la réponse commerciale.

## Déclencheurs typiques

| Signal | Exemple |
|--------|---------|
| Comparaison explicite | "combien chez Exaprint pour 1000 flyers A5 ?" |
| Doute client | "le client dit que c'est moins cher en ligne" |
| Validation devis | après un calcul via calcul-tarif-inpressco |
| Brief budget flou | "son budget est serré, on se situe comment ?" |
| Recherche marché | "veille tarifaire cartes de visite 500ex" |
| Positionnement | "est-ce qu'on est compétitif sur les affiches A2 ?" |

## Produits couverts

| Catégorie | Références standard |
|-----------|-------------------|
| Flyers / Prospectus | A6 r/v, A5 r/v, A4 r/v — couché 135g ou 170g |
| Cartes de visite | 85×55mm r/v — couché mat 350g ± pelliculage |
| Affiches / Posters | A3, A2 — couché brillant 135g |
| Brochures / Catalogues | A5 ou A4, 8–24 pages agrafés — couché mat 170g |

## Sources concurrentes

| Source | URL de référence | Notes |
|--------|-----------------|-------|
| Exaprint | https://www.exaprint.fr | Configurateur en ligne par produit |
| Onlineprinters | https://www.onlineprinters.fr | Tarifs affichés avec options |
| Pixartprinting | https://www.pixartprinting.fr | Grille tarifaire accessible |

## Processus d'exécution

### Étape 1 — Collecter les paramètres du produit

Vérifier que les paramètres suivants sont disponibles. Si manquants, les déduire du contexte ou demander :

- Type de produit (flyer, carte de visite, affiche, brochure)
- Format (A6 / A5 / A4 / A3 / A2 / 85×55)
- Impression (recto / recto-verso / 4 couleurs)
- Support / grammage
- Finition (aucune / pelliculage mat / pelliculage brillant)
- Quantité(s) cible(s)

### Étape 2 — Recherche web des prix concurrents

Pour chaque concurrent (Exaprint, Onlineprinters, Pixartprinting), effectuer une recherche ciblée :

**Requêtes web_search recommandées :**
- `"[produit] [format] [quantité] prix exaprint 2025"`
- `"[produit] [format] [quantité] tarif onlineprinters"`
- `"[produit] [format] [quantité] pixartprinting prix HT"`

Si web_search ne retourne pas de prix précis → utiliser web_fetch sur l'URL du configurateur du site concerné pour extraire le tarif.

**Stratégie de fallback :** si un site bloque le fetch, utiliser les données de la base de référence (references/prix-marche.md) et le signaler clairement dans la sortie.

### Étape 3 — Récupérer le tarif InPressco

Appeler le skill `calcul-tarif-inpressco` avec les mêmes paramètres pour obtenir l'estimation InPressco (si elle n'est pas déjà disponible dans le contexte).

### Étape 4 — Construire le tableau comparatif

Assembler les données collectées dans le format de sortie standard (voir ci-dessous).

### Étape 5 — Analyser le positionnement

Calculer les écarts et produire une recommandation commerciale synthétique.

### Étape 6 — Proposer une action

Selon le positionnement, proposer :

- Lancer le devis Dolibarr (`inpressco-devis`) si position favorable
- Adapter l'argumentaire valeur si prix plus élevé
- Alerter l'équipe si écart significatif (> 30%)

## Format de sortie

### Tableau comparatif inline (affichage conversation)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VEILLE PRIX — [Produit] [Format] [Quantité] ex
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Imprimeur         | Prix HT    | Délai   | Finitions incluses         |
|-------------------|-----------|---------|----------------------------|
| Exaprint          | XXX–XXX € | XX j    | [options]                  |
| Onlineprinters    | XXX–XXX € | XX j    | [options]                  |
| Pixartprinting    | XXX–XXX € | XX j    | [options]                  |
| **InPressco** ★   | XXX–XXX € | XX j    | [options + valeur ajoutée] |

Positionnement InPressco : [EN DESSOUS / DANS LA MOYENNE / AU-DESSUS] du marché
Écart moyen : [±X%]

Note : [Explication de la valeur ajoutée InPressco si prix supérieur]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### JSON structuré (pour usage interne / Dolibarr)

```json
{
  "veille_prix": {
    "produit": "[type produit]",
    "parametres": {
      "format": "",
      "impression": "",
      "support": "",
      "finition": "",
      "quantite": 0
    },
    "date_veille": "[date ISO]",
    "concurrents": [
      {
        "nom": "Exaprint",
        "prix_ht_min": 0,
        "prix_ht_max": 0,
        "delai_jours": 0,
        "source_url": "",
        "fiabilite": "HIGH|MEDIUM|LOW",
        "note": ""
      },
      {
        "nom": "Onlineprinters",
        "prix_ht_min": 0,
        "prix_ht_max": 0,
        "delai_jours": 0,
        "source_url": "",
        "fiabilite": "HIGH|MEDIUM|LOW",
        "note": ""
      },
      {
        "nom": "Pixartprinting",
        "prix_ht_min": 0,
        "prix_ht_max": 0,
        "delai_jours": 0,
        "source_url": "",
        "fiabilite": "HIGH|MEDIUM|LOW",
        "note": ""
      }
    ],
    "inpressco": {
      "prix_ht_min": 0,
      "prix_ht_max": 0,
      "delai_jours": 0,
      "confiance": "HIGH|MEDIUM|LOW"
    },
    "analyse": {
      "positionnement": "EN DESSOUS|DANS LA MOYENNE|AU-DESSUS",
      "ecart_moyen_pct": 0,
      "recommandation": ""
    }
  }
}
```

## Fiabilité des données collectées

| Niveau | Condition |
|--------|-----------|
| HIGH | Prix extrait directement du configurateur du site |
| MEDIUM | Prix issu d'une page tarif générale ou d'un résultat de recherche récent |
| LOW | Prix estimé depuis la base de référence locale (site inaccessible) |

Toujours indiquer le niveau de fiabilité dans le JSON et signaler les données LOW dans le tableau inline avec une note "(estimation)".

## Analyse du positionnement

| Écart InPressco vs marché | Positionnement | Recommandation commerciale |
|--------------------------|----------------|---------------------------|
| InPressco < marché de plus de 10% | EN DESSOUS | Mettre en avant le rapport qualité/prix — opportunité commerciale forte |
| Écart ±10% | DANS LA MOYENNE | Valoriser la qualité façonnage, le conseil, les délais et la relation de proximité |
| InPressco > marché de 10 à 25% | AU-DESSUS | Argumenter sur la qualité papier, les finitions, le suivi BAT, le service |
| InPressco > marché de plus de 25% | ÉCART SIGNIFICATIF | Alerter l'équipe — revoir positionnement ou proposer une offre ajustée |

## Règles importantes

- **Ne jamais communiquer ce tableau comparatif tel quel au client** — usage interne uniquement
- Si le profil est **CLIENT** → ne communiquer que les fourchettes InPressco avec l'argumentaire valeur
- Si le profil est **TEAM / ADMIN** → afficher le tableau complet avec l'analyse
- Les prix concurrents sont indicatifs et peuvent varier selon les options — toujours dater la veille
- Toujours proposer de lancer `inpressco-devis` après la veille pour formaliser l'offre
- Si le client mentionne un prix concurrent précis → l'intégrer dans le tableau comme source additionnelle

## Intégration avec les autres skills

| Skill | Quand l'appeler |
|-------|----------------|
| `calcul-tarif-inpressco` | Toujours — pour obtenir le tarif InPressco à comparer |
| `inpressco-devis` | Après la veille — pour formaliser l'offre commerciale |
| `reponse-client-inpressco` | Si un email client mentionne un concurrent — pour rédiger la réponse |
| `notification-interne-inpressco` | Si écart > 25% — pour alerter l'équipe |
| `memoire-client-inpressco` | Pour contextualiser (client prix-sensible, historique commandes) |
