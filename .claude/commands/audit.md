# SAGA1o8 Audit v1

Évaluation structurelle d'un projet code.
Autonome, adaptable, livrable directement au client.

---

## USAGE


/audit              → rapport complet automatique
/audit --light      → conversation guidée (questions → diagnostic)
/audit --export     → génère audit_report.html pour livraison


---

## DÉTECTION DU CONTEXTE

Avant tout, identifie le type de projet :

Lis l'arborescence complète. Cherche :
•⁠  ⁠Présence de LLM : imports ⁠ openai ⁠, ⁠ anthropic ⁠, ⁠ ollama ⁠, ⁠ langchain ⁠, appels API
•⁠  ⁠Présence d'agents : boucles autonomes, tool use, planners, memory systems
•⁠  ⁠Pipeline de données : ETL, transformations chaînées, ingestion/processing/output
•⁠  ⁠Projet code classique : application, API, service, librairie

Classe le projet dans une ou plusieurs catégories :

TYPE DÉTECTÉ : [LLM-assisted / Agentic / Pipeline / Code classique]
STACK        : [langages, frameworks principaux]
TAILLE       : [N fichiers .py/.ts/etc, N lignes estimées]
POINT D'ENTRÉE : [fichier principal identifié]


Adapte la profondeur de l'évaluation au type détecté.
Un projet sans LLM ne reçoit pas d'évaluation agentic — seulement les dimensions pertinentes.

---

## LES 4 DIMENSIONS D'ÉVALUATION

Chaque dimension est scorée de 1 à 5 :

5 — Exemplaire
4 — Solide, quelques améliorations mineures
3 — Fonctionnel mais fragile
2 — Problèmes structurels actifs
1 — Dette critique, risque élevé


---

### DIMENSION 1 — Intégrité Structurelle
Inspiré des contraintes Hamiltoniennes et Eulériennes de SAGA1o8

*Ce qu'on évalue :*

Unicité des responsabilités :
•⁠  ⁠Chaque module a-t-il un rôle unique et non dupliqué ?
•⁠  ⁠Y a-t-il des fonctions utilitaires éparpillées qui devraient être centralisées ?
•⁠  ⁠Des modules font-ils la même chose sous des noms différents ?

Unicité des transformations :
•⁠  ⁠Y a-t-il un point d'entrée clair ou plusieurs chemins d'exécution parallèles ?
•⁠  ⁠Des pipelines sont-ils dupliqués à différents endroits ?
•⁠  ⁠L'orchestration est-elle explicite ou cachée dans des sous-modules ?

Séparation des rôles :
•⁠  ⁠Mutation / Observation / Décision sont-ils mélangés dans les mêmes fichiers ?
•⁠  ⁠Les outputs sont-ils séparés des transformations ?

*Signaux d'alerte :*
•⁠  ⁠Fichier ⁠ utils.py ⁠ de plus de 200 lignes
•⁠  ⁠Même logique dans 3 fichiers différents
•⁠  ⁠⁠ main.py ⁠ qui fait tout
•⁠  ⁠Imports circulaires

---

### DIMENSION 2 — Écologie du Code
Inspiré des principes d'éco-conception logicielle et de la dette technique mesurable

*Ce qu'on évalue :*

Redondance active :
•⁠  ⁠Code copié-collé entre modules
•⁠  ⁠Patterns répétés sans abstraction
•⁠  ⁠Configurations dupliquées

Dette structurelle :
•⁠  ⁠Fonctions > 50 lignes sans justification
•⁠  ⁠Couplage fort entre modules indépendants
•⁠  ⁠Dépendances circulaires
•⁠  ⁠Dead code (fonctions jamais appelées)

Lisibilité systémique :
•⁠  ⁠Peut-on comprendre ce que fait le système en lisant 3 fichiers ?
•⁠  ⁠Les noms reflètent-ils la réalité du code ?
•⁠  ⁠Y a-t-il des commentaires qui expliquent le pourquoi (pas le quoi) ?

Testabilité :
•⁠  ⁠Le code est-il testable sans setup complexe ?
•⁠  ⁠Y a-t-il des tests ? Couvrent-ils les chemins critiques ?
•⁠  ⁠Les effets de bord sont-ils isolés ?

---

### DIMENSION 3 — Résilience Évaluative
Inspiré du Controlled Evaluation Architecture de SAGA1o8 et des patterns de systèmes critiques

*Ce qu'on évalue :*

Traçabilité :
•⁠  ⁠Les décisions importantes sont-elles documentées ?
•⁠  ⁠Peut-on reconstituer pourquoi le système fait ce qu'il fait ?
•⁠  ⁠Les outputs sont-ils datés, identifiables, reproductibles ?

Frontières d'évaluation :
•⁠  ⁠Le système peut-il modifier ses propres critères de succès ?
•⁠  ⁠Y a-t-il une séparation entre ce qui produit et ce qui évalue ?
•⁠  ⁠Les erreurs sont-elles catchées et loggées ou silencieuses ?

Gestion des états :
•⁠  ⁠Les états implicites sont-ils nombreux ?
•⁠  ⁠Un cycle peut-il rester ouvert sans détection ?
•⁠  ⁠Y a-t-il des side effects non intentionnels entre modules ?

---

### DIMENSION 4 — Robustesse Agentique
Applicable uniquement si LLM ou agents détectés — sinon marquée N/A
Inspiré des recherches récentes en agentic AI safety et human-in-the-loop systems

*Ce qu'on évalue :*

Frontière humain / autonome :
•⁠  ⁠Où s'arrête l'autonomie du système ? Est-ce explicite dans le code ?
•⁠  ⁠Y a-t-il des points de contrôle humain avant les actions irréversibles ?
•⁠  ⁠Le système peut-il s'auto-modifier sans supervision ?

Fragilité des prompts :
•⁠  ⁠Les prompts sont-ils hardcodés ou paramétrables ?
•⁠  ⁠Une réponse LLM malformée fait-elle crasher le système ?
•⁠  ⁠Y a-t-il validation du output LLM avant usage ?

Évaluation LLM :
•⁠  ⁠Comment sait-on si le LLM a bien fait son travail ?
•⁠  ⁠L'évaluation est-elle indépendante du LLM évalué ?
•⁠  ⁠Y a-t-il un fallback si le LLM est indisponible ?

Dérive temporelle :
•⁠  ⁠Le comportement du système va-t-il diverger avec le temps ?
•⁠  ⁠Y a-t-il des mécanismes pour détecter la dégradation ?

---

## ANALYSE DES CONTRADICTIONS ACTIVES
Inspiré de TRIZ — résoudre des contradictions, pas juste des problèmes

Identifie jusqu'à 3 contradictions structurelles dans le projet :
ce que le système veut faire simultanément mais qui crée une tension réelle.


CONTRADICTION #N
Tension    : le projet veut [A] ET [B] simultanément
Coût actuel : ce que cette tension coûte aujourd'hui
Explosion à : [quand / à quelle échelle ça va craquer]
Résolution  : approche suggérée


Exemples de contradictions fréquentes :
•⁠  ⁠Vitesse de développement ET cohérence structurelle
•⁠  ⁠Flexibilité des prompts ET comportement prévisible
•⁠  ⁠Autonomie de l'agent ET contrôle humain
•⁠  ⁠Monorepo tout-en-un ET séparation des responsabilités

---

## RAPPORT CLIENT

### Structure du rapport


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAGA1o8 Audit v1 — [Nom du projet]
[DATE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Synthèse exécutive

Type de projet  : [détecté]
Stack           : [langages / frameworks]
Score global    : [X.X / 5]

[3-4 phrases. Ce qui est solide. Ce qui est fragile.
Ce qui va exploser en premier si rien ne change.]

## Scores par dimension

| Dimension                  | Score | Statut |
|----------------------------|-------|--------|
| Intégrité structurelle     |  X/5  | 🟢/🟡/🟠/🔴 |
| Écologie du code           |  X/5  | 🟢/🟡/🟠/🔴 |
| Résilience évaluative      |  X/5  | 🟢/🟡/🟠/🔴 |
| Robustesse agentique       |  X/5  | 🟢/🟡/🟠/N/A |

Règle de couleur :
🟢 4-5  🟡 3  🟠 2  🔴 1

## Diagnostic détaillé

[Pour chaque dimension scorée < 4 : développement en prose,
2-3 paragraphes max, exemples concrets depuis le code]

## Contradictions actives

[Les contradictions identifiées avec leur coût et leur horizon d'explosion]

## Pistes concrètes

Classées par impact / effort :

### Action immédiate (< 1 session)
- [piste 1 — pourquoi maintenant]
- [piste 2]

### Sprint structurel (1-3 sessions)
- [piste 1 — dépendance éventuelle]
- [piste 2]

### Décision architecturale (à planifier)
- [piste 1 — ce qui doit être décidé avant d'agir]

## Ce qui est bien
[Ce qui fonctionne, ce qui est solide, ce qui mérite d'être préservé.
Toujours présent — un audit sans reconnaissance est incomplet.]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAGA1o8 Audit v1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


---

## MODE --light (conversation guidée)

Lance une séquence de 6 questions au client, une par une.
Chaque réponse affine le diagnostic avant d'aller lire le code.


Q1 — Quel est l'objectif principal du système ?
     (comprendre le intent avant de juger la structure)

Q2 — Quelle est la partie du code dont tu es le moins fier ?
     (les développeurs savent toujours où est la dette)

Q3 — Si le système grossit x10, où est-ce que ça casse en premier ?
     (détecte la contradiction principale)

Q4 — Comment sais-tu que le système fonctionne correctement ?
     (évalue la résilience évaluative)

Q5 — Y a-t-il des parties que tu évites de toucher ?
     (dette cachée, couplage fort non documenté)

Q6 — Qu'est-ce que tu voudrais qu'il fasse dans 6 mois ?
     (aligne l'audit sur la direction réelle)


Après les 6 questions → lance l'audit complet avec ce contexte.
Les réponses client enrichissent le rapport : "Le client mentionne X — confirmé par le code / infirmé."

---

## MODE --export

Génère ⁠ audit_report.html ⁠ dans la racine du projet scanné.

Le HTML doit être :
•⁠  ⁠Lisible sans outil (navigateur suffit)
•⁠  ⁠Imprimable proprement (A4, pas de coupure dans les sections)
•⁠  ⁠Auto-contenu (pas de dépendance externe)
•⁠  ⁠Signé SAGA1o8 Audit v1 en footer

Structure HTML :
•⁠  ⁠Header avec nom du projet, date, score global visuel (gauge ou étoiles)
•⁠  ⁠Sections repliables pour le diagnostic détaillé
•⁠  ⁠Tableau des scores avec couleurs
•⁠  ⁠Section pistes avec badges impact/effort
•⁠  ⁠Footer signature

---

## RÈGLES DE L'AUDIT

*Honnêteté avant diplomatie*
Un score de 2 est un score de 2. Ne pas arrondir pour ménager.
Le client paie pour savoir ce qui ne va pas, pas pour être rassuré.

*Concret avant générique*
Chaque problème identifié cite le fichier, la fonction, ou la pattern spécifique.
"Votre code a des problèmes de couplage" ne sert à rien.
"src/processor.py importe directement db/connection.py et src/formatter.py — ces trois modules sont couplés sans raison" est utile.

*Toujours terminer par ce qui fonctionne*
Chaque rapport contient une section "Ce qui est bien".
Un projet sans qualités n'existe pas — si l'audit ne trouve rien de positif,
cherche plus attentivement.

*Ne pas sur-promettre*
Les pistes sont des pistes, pas des garanties.
"Cela devrait améliorer la maintenabilité" pas "Cela va résoudre vos problèmes".