# Benchmark AwaleAI : 50 parties

Un tournoi local entre Random, Minimax, Alpha-Bêta et Q-Learning, avec **50 parties au total** et **un seul graphique final** pour une diapositive 16:9. Le script n'entraîne aucun agent et ne modifie aucun algorithme ou modèle.

## Protocole fixé

| Duel | Parties |
| --- | ---: |
| Random / Minimax | 8 |
| Random / Alpha-Bêta | 8 |
| Random / Q-Learning | 9 |
| Minimax / Alpha-Bêta | 9 |
| Minimax / Q-Learning | 8 |
| Alpha-Bêta / Q-Learning | 8 |
| Total | **50** |

Chaque agent dispute exactement **25 parties**, avec 12 ou 13 départs comme premier joueur. Les duels alternent les positions des joueurs. Les 48 premières parties forment 24 aller-retours ; deux duels disjoints reçoivent chacun une partie supplémentaire. Cette répartition minimise l'écart entre duels et garde le même nombre de parties par agent.

- Graine maîtresse : `20261121`, graines individuelles enregistrées dans le CSV.
- Plateau standard : 12 cases de 4 graines, scores à zéro, Joueur 1 au départ.
- Ouverture : 4 coups légaux déterminés par une graine dédiée, comptés dans la longueur totale de la partie. Les agents prennent ensuite le relais. Les deux parties d'un aller-retour ont la même ouverture, le même historique et la même graine de décisions ; les agents échangent leurs positions.
- Minimax et Alpha-Bêta : profondeur 3, exprimée en demi-coups. Les paramètres restent identiques pendant les 50 parties.
- Q-Learning : `models/q_table_best.json`, empreinte SHA-256 verrouillée dans la configuration, exploitation avec `greedy=True`, aucun apprentissage. Le script refuse un autre checkpoint ou une table vide issue d'un échec de chargement.
- Limite moteur : 500 coups, ouverture incluse. L'exécution est séquentielle pour éviter le partage aléatoire entre threads ou processus.

Les règles utilisées sont exactement celles de `engine/game.py` et `engine/rules.py`. Le moteur termine par seuil de 25 graines, blocage, répétition ou limite de coups. Les deux derniers motifs donnent un match nul, même lorsque les scores diffèrent. La variante locale autorise l'affamement si tous les coups l'imposent ; ce benchmark ne certifie pas la conformité à toutes les variantes d'un règlement externe.

## Exécution

Depuis la racine du projet, avec Python 3.13 et Matplotlib 3.10.8 :

```powershell
python -m pip install -r benchmark/requirements.txt
python -X utf8 -u benchmark/run_50.py
```

Le script mesure exactement 50 parties et crée les fichiers dans `benchmark/results/presentation_50/`. Il refuse de remplacer des résultats existants. Pour **relancer une nouvelle expérience de 50 parties**, utiliser un dossier vide :

```powershell
python -X utf8 -u benchmark/run_50.py --output benchmark/results/reproduction_50
```

Pour **vérifier les résultats existants sans aucune nouvelle confrontation** :

```powershell
python -X utf8 benchmark/run_50.py --verify-only
```

Pour recréer uniquement le graphique à partir du CSV vérifié :

```powershell
python -X utf8 benchmark/run_50.py --render-only
```

Une autre configuration peut être passée avec `--config`, mais elle doit conserver 50 parties, les quatre agents et une répartition de 25 parties par agent. Le rendu respecte la règle typographique du projet : le titre est **« Benchmark des agents IA : 50 parties »**, avec un deux-points.

## Fichiers

| Fichier | Contenu |
| --- | --- |
| `run_50.py` | Exécution, vérification du CSV et rendu Matplotlib |
| `config_50.json` | Paramètres, graine, modèle et palette bleue |
| `requirements.txt` | Version de Matplotlib utilisée |
| `results/presentation_50/games.csv` | 50 parties mesurées, positions initiales, graines et trajectoires complètes |
| `results/presentation_50/summary.json` | Bilans individuels, taux et nombres de parties par duel |
| `results/presentation_50/summary.md` | Résultats lisibles, protocole et limites |
| `results/presentation_50/run_metadata.json` | Versions, empreintes des sources et des modèles, configuration réellement utilisée |
| `results/presentation_50/verification.json` | Contrôles de cohérence et empreintes du CSV et du PNG |
| `results/presentation_50/benchmark_50.png` | **Graphique unique, 4800 × 2700 pixels, 300 dpi, 16:9** |

Le CSV donne les identifiants et agents des deux sièges, le gagnant ou `draw`, le motif de fin, les coups, la durée, l'ouverture, les graines, la position initiale après ouverture et les scores finaux. La trajectoire inclut les coups d'ouverture, ce qui permet de reconstruire aussi l'historique des répétitions.

La durée est le temps mural entre la création du jeu et son état terminal, ouverture et contrôles pendant le jeu inclus. Elle exclut le chargement de la Q-table, la vérification après tournoi et le rendu du graphique. Les temps de décision séparés excluent les animations, l'API et la validation des coups après sélection.

## Lecture du graphique

Les barres empilées présentent les victoires, matchs nuls et défaites de chaque agent. Leur hauteur est 25 parties. Les valeurs positives apparaissent sur les segments ; une ligne sous chaque barre reprend aussi les quantités nulles. Le taux de victoire est **victoires / 25**, sans retirer les matchs nuls du dénominateur. Les 50 parties uniques correspondent à 100 participations d'agents, et non à 100 parties.

La palette est exclusivement dominée par le bleu : bleu royal pour les victoires, bleu clair pour les nuls et bleu foncé pour les défaites. Aucun graphique secondaire ni dashboard n'est produit.

## Vérification et limites

Le calendrier, les 50 identifiants, les six duels et les positions des joueurs sont contrôlés. Chaque coup est validé, la conservation des 48 graines est vérifiée après chaque transition, et chaque partie doit atteindre un état terminal du moteur. Les trajectoires du CSV sont rejouées sans appeler les agents. Le script compare les résultats au moteur, les agrégats CSV au résumé et les hauteurs des rectangles Matplotlib aux comptes. Les données du PNG sont également vérifiées face au CSV. Les sources et Q-tables doivent garder leur empreinte après l'expérience.

Les tests du protocole utilisent des fixtures synthétiques explicitement séparées des résultats mesurés :

```powershell
python -X utf8 -m unittest tests.test_benchmark -v
```

50 parties donnent une première comparaison. Elles ne démontrent ni une supériorité définitive, ni un niveau général de jeu, ni un progrès d'apprentissage du Q-Learning. Les aller-retours appariés sont liés, les deux parties supplémentaires sont non appariées, et les résultats dépendent des ouvertures, des adversaires, de la profondeur et du checkpoint. Les mêmes sources, versions et graines rendent les coups et résultats reproductibles ; les durées varient avec la machine et sa charge.
