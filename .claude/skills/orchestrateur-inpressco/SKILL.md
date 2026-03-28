---
name: orchestrateur-inpressco
description: >
  Skill d'orchestration des workflows multi-skills pour In'Pressco. Déclencher dès qu'un
  input complexe nécessite l'activation séquentielle ou parallèle de plusieurs skills dans
  un ordre précis : traitement d'un email entrant complet (routing + sentiment + mémoire +
  devis + réponse), traitement d'une commande (droits + query + suivi + notification), ou
  toute demande qui traverse plusieurs domaines fonctionnels. Utiliser aussi quand Claude
  doit gérer une séquence d'actions interdépendantes sans perdre le contexte entre les
  étapes. Ce skill décompose l'input en plan d'exécution, active les skills dans le bon
  ordre, passe le contexte de l'un à l'autre, et gère les erreurs et reprises dans la chaîne.
---

# Orchestrateur — In'Pressco

## Rôle
Décomposer un input complexe en une séquence ordonnée de skills, les exécuter dans le bon ordre en transmettant le contexte enrichi d'une étape à l'autre, et produire un résultat cohérent même si plusieurs skills sont nécessaires. C'est le chef d'orchestre — le routing engine choisit un skill, l'orchestrateur dirige une symphonie de skills.

---

## Distinction routing engine vs orchestrateur

| | Routing engine (Claude natif) | Orchestrateur (ce skill) |
|--|-------------------------------|--------------------------|
| Rôle | Choisir le bon skill pour un input simple | Enchaîner plusieurs skills pour un input complexe |
| Granularité | 1 input → 1 skill | 1 input → N skills en séquence |
| Contexte | Transmis implicitement | Explicitement passé et enrichi à chaque étape |
| Gestion erreurs | Non | Oui — reprise et contournement |
| Parallélisme | Non | Oui — certaines étapes peuvent tourner en parallèle |

---

## Chaînes de skills standards (patterns récurrents)

### Chaîne A — Traitement email entrant complet
```
Input : email client reçu

1. droits-profils-inpressco       → identifier profil expéditeur
2. mail-routing-inpressco         → catégoriser l'email
3. analyse-sentiment-email        → ton, urgence, personnalité
4. memoire-client-inpressco       → charger contexte tiers
5. [selon catégorie routing] :
   NEW_PROJECT → inpressco-devis + calcul-tarif-inpressco
   PROJECT_UPDATE → dolibarr-query-inpressco + archiveur-inpressco
   SUPPLIER_INVOICE → workflow saisie facture
6. reponse-client-inpressco       → rédiger réponse
7. validation-qc-inpressco        → contrôler avant envoi
8. agenda-inpressco               → logger l'échange
```

### Chaîne B — Création devis complète
```
Input : brief client (email, oral, formulaire)

1. droits-profils-inpressco       → vérifier droits
2. extraction-tiers               → extraire données client
3. dolibarr-query-inpressco       → vérifier existence tiers (anti-doublon)
4. memoire-client-inpressco       → charger historique + préférences
5. calcul-tarif-inpressco         → estimation rapide
6. inpressco-devis                → construire devis structuré
7. generation-pdf-inpressco       → générer PDF azur_fp
8. archiveur-inpressco            → classer le PDF
9. validation-qc-inpressco        → contrôler avant envoi
10. reponse-client-inpressco      → email avec devis en PJ
11. agenda-inpressco              → planifier relance à +7j
```

### Chaîne C — Traitement BAT et validation
```
Input : BAT reçu ou validation client annoncée

1. droits-profils-inpressco       → vérifier profil
2. dolibarr-query-inpressco       → identifier la commande associée
3. archiveur-inpressco            → déposer le BAT sur la commande
4. charte-graphique-inpressco     → contrôle conformité charte client
5. suivi-commande-inpressco       → mettre à jour jalon BAT
6. notification-interne-inpressco → alerter Nicolas (production)
7. agenda-inpressco               → logger validation BAT
8. [si validation] → reponse-client-inpressco → accusé réception
```

### Chaîne D — Reporting journalier automatique
```
Input : déclenchement quotidien (heure programmée ou demande manuelle)

1. droits-profils-inpressco       → vérifier profil ADMIN
2. controleur-gestion-inpressco   → agréger données financières
3. analyseur-data-dolibarr        → détecter anomalies et tendances
4. notification-interne-inpressco → envoyer le reporting à Paola
5. agenda-inpressco               → logger la production du rapport
```

### Chaîne E — Nouveau client entrant
```
Input : contact inconnu avec brief

1. droits-profils-inpressco       → profil CLIENT
2. extraction-tiers               → extraire coordonnées
3. dolibarr-query-inpressco       → vérifier doublon
4. chat-to-db-inpressco           → structurer les données
5. [si nouveau] → workflow création tiers Dolibarr
6. memoire-client-inpressco       → initialiser le contexte
7. calcul-tarif-inpressco         → première estimation
8. inpressco-devis                → construire le devis
```

### Chaîne F — Suivi et relance commande
```
Input : vérification proactive ou alerte automatique

1. dolibarr-query-inpressco       → état réel de la commande
2. suivi-commande-inpressco       → analyser le jalon actuel
3. [si retard ou BAT en attente]
   → reponse-client-inpressco     → relance client
   → notification-interne-inpressco → alerter équipe
4. agenda-inpressco               → replanifier suivi prochain
```

---

## Processus d'orchestration

### Étape 1 — Analyser l'input
Identifier :
- Canaux et type d'entrée
- Entités impliquées (tiers, document, visuel)
- Actions requises
- Dépendances entre actions

### Étape 2 — Sélectionner la chaîne
Mapper l'input sur la chaîne standard la plus proche, ou construire une chaîne sur mesure.

### Étape 3 — Construire le plan d'exécution
```json
{
  "chaine": "A | B | C | D | E | F | custom",
  "etapes": [
    {
      "ordre": 1,
      "skill": "droits-profils-inpressco",
      "input": "email entrant",
      "output_attendu": "profil + droits",
      "parallele_avec": null,
      "bloquant": true
    },
    {
      "ordre": 2,
      "skill": "mail-routing-inpressco",
      "input": "email + profil",
      "output_attendu": "catégorie routing",
      "parallele_avec": null,
      "bloquant": true
    },
    {
      "ordre": 3,
      "skill": "analyse-sentiment-email",
      "input": "email",
      "output_attendu": "ton + urgence",
      "parallele_avec": "memoire-client-inpressco",
      "bloquant": false
    }
  ]
}
```

### Étape 4 — Exécuter en transmettant le contexte
Chaque skill reçoit :
- Son input propre
- Le contexte enrichi par les skills précédents
- Les outputs des étapes dont il dépend

### Étape 5 — Gérer les erreurs dans la chaîne
```
Étape bloquante en échec → stopper la chaîne, appeler gestion-erreurs, alerter
Étape non bloquante en échec → continuer avec valeur par défaut, noter l'échec
Étape parallèle en échec → attendre les autres, merger les résultats disponibles
```

### Étape 6 — Produire le résultat consolidé
Fusionner les outputs de toutes les étapes en un résultat cohérent.

---

## Schéma JSON du plan d'exécution

```json
{
  "orchestration": {
    "input_type": "email_entrant | brief_oral | commande_entrante | ...",
    "chaine_selectionnee": "A",
    "nb_etapes": 8,
    "etapes_paralleles": [["analyse-sentiment-email", "memoire-client-inpressco"]],
    "statut": "en_cours | terminé | erreur | partiel"
  },
  "execution": [
    {
      "etape": 1,
      "skill": "droits-profils-inpressco",
      "statut": "ok",
      "duree_ms": 120,
      "output_cle": "profil=CLIENT, confidence=high"
    },
    {
      "etape": 2,
      "skill": "mail-routing-inpressco",
      "statut": "ok",
      "duree_ms": 340,
      "output_cle": "categorie=NEW_PROJECT, confidence=high"
    }
  ],
  "resultat_final": {
    "actions_réalisées": ["profil identifié", "email routé", "devis préparé", "réponse rédigée"],
    "actions_en_attente": ["validation humaine avant envoi"],
    "alertes": []
  }
}
```

---

## Règles importantes

- L'orchestrateur **ne remplace pas** le routing engine — il prend la main quand le routing engine a identifié qu'une séquence est nécessaire
- Les étapes marquées `bloquant: true` **arrêtent la chaîne** en cas d'échec — les étapes `bloquant: false` permettent de continuer avec dégradation
- **Toujours commencer** par `droits-profils-inpressco` dans toute chaîne impliquant des données Dolibarr ou une communication client
- Le contexte est un objet cumulatif — chaque skill l'enrichit sans effacer ce que les précédents ont produit
- En cas de doute sur la chaîne à appliquer → préférer une chaîne plus longue (sur-contrôle) plutôt qu'une chaîne trop courte (sous-contrôle)
- L'orchestrateur est **transparent pour l'utilisateur** — il voit le résultat final, pas les étapes intermédiaires (sauf en mode debug)
