# Benchmark des agents IA : 50 parties

Résultats mesurés localement, sans entraînement ni modification des agents.

| Agent | Victoires | Matchs nuls | Défaites | Parties | Taux de victoire | Premier / second joueur |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 1 | 1 | 23 | 25 | 4.0 % | 13 / 12 |
| Minimax | 17 | 3 | 5 | 25 | 68.0 % | 13 / 12 |
| Alpha-Bêta | 21 | 3 | 1 | 25 | 84.0 % | 12 / 13 |
| Q-Learning | 7 | 1 | 17 | 25 | 28.0 % | 12 / 13 |

Le dénominateur est le nombre total de parties disputées par l'agent, soit 25, matchs nuls et défaites inclus.

## Protocole

Graine maîtresse : `20261121`. Minimax et Alpha-Bêta : profondeur `3` et `3`, en demi-coups.
Ouvertures : 4 coups légaux choisis avec une graine fixe, depuis le plateau standard de 4 graines par case. Même ouverture et même graine de décisions dans chaque aller-retour, avec échange des joueurs.
Limite moteur : 500 coups, ouverture incluse. Les coups automatiques d'ouverture ne sont pas attribués aux agents.

| Duel | Parties |
| --- | ---: |
| Random / Minimax | 8 |
| Random / Alpha-Bêta | 8 |
| Random / Q-Learning | 9 |
| Minimax / Alpha-Bêta | 9 |
| Minimax / Q-Learning | 8 |
| Alpha-Bêta / Q-Learning | 8 |

Durée cumulée mesurée des parties : 9.625 s. Le chargement du modèle, la vérification des trajectoires et la production du PNG sont exclus.
Motifs de fin : `{"blocage":4,"repetition":4,"score":42}`.

## Q-Learning

Checkpoint chargé exactement : `models/q_table_best.json`. SHA-256 : `570da4fca1bc35e42961a7f3b68ee7d714469085fd14ff01761186619cea4ce8`.
États de la table : 87282. Politique d'exploitation (`greedy=True`), aucune mise à jour ou sauvegarde de la Q-table.

## Vérifications

Les 50 lignes du CSV sont relues et leurs coups rejoués avec le moteur, sans solliciter les agents et sans ajouter de nouvelles confrontations.
Les graines, ouvertures, positions, scores, gagnants, fins et nombres de coups sont vérifiés. Les comptes individuels donnent 100 participations pour 50 parties uniques. Chaque victoire correspond à une défaite ; chaque match nul figure dans le bilan de deux agents.
Les valeurs des rectangles Matplotlib sont contrôlées avant export. Les données intégrées au PNG, le résumé JSON et l'agrégation indépendante du CSV doivent être identiques. Voir `verification.json`.

## Limites

50 parties constituent une première comparaison, pas une preuve définitive de supériorité. Les 24 aller-retours sont appariés : ils ne constituent pas 48 observations indépendantes. Deux parties supplémentaires ne sont pas appariées ; elles permettent 25 parties par agent.
Ces résultats dépendent de la profondeur choisie, du checkpoint Q-Learning, des ouvertures, des adversaires et de la variante du moteur. Minimax et Alpha-Bêta utilisent le même horizon et la même heuristique ; leurs égalités peuvent être départagées différemment.
Le moteur permet l'affamement si tous les coups l'imposent ; ce benchmark suit cette variante locale et ne prétend pas certifier toutes les variantes officielles. Les répétitions et la limite de coups donnent un match nul, même avec des scores différents.
Le taux observé ne démontre pas un progrès d'apprentissage du Q-Learning. Les temps dépendent de la machine et ne sont pas reproductibles à l'identique ; les graines, coups et résultats sont reproductibles avec les mêmes sources, versions et modèle.

## Artefacts

`games.csv`, `summary.json`, `run_metadata.json`, `verification.json` et un seul graphique `benchmark_50.png` (4800 × 2700, 16:9, 300 dpi).
