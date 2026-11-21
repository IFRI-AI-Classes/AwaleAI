# AwaleAI

Moteur de jeu Awalé en Python avec architecture modulaire.  
Le projet implémente une variante documentée de l'Awalé, quatre agents IA (Aléatoire, Minimax, Alpha-Bêta, Q-Learning) et une interface web interactive connectée à une API REST FastAPI. Le Q-Learning reste expérimental : son apprentissage tactique est démontré, mais sa progression générale n'est pas établie.

> Projet développé dans le cadre du **Club IA & IoT, IFRI**.

---

## Sommaire

- [Architecture](#architecture)
- [Installation](#installation)
- [Lancement](#lancement)
- [Moteur de jeu](#moteur-de-jeu)
- [Agents IA](#agents-ia)
- [API REST](#api-rest)
- [Interface Web](#interface-web)
- [Entraînement Q-Learning](#entraînement-q-learning)
- [Règles implémentées](#règles-implémentées)
- [Tests et benchmarks](#tests-et-benchmarks)
- [Audit technique des agents](#audit-technique-des-agents)
- [Roadmap](#roadmap)

---

## Architecture

```
AwaleAI/
├── engine/
│   ├── board.py          # Modélisation du plateau (12 cases)
│   ├── rules.py          # Règles, distribution des graines, coups valides
│   ├── game.py           # Moteur de jeu : captures, scores, fin de partie
│   ├── env.py            # Wrapper minimal AwaleEnv, non utilisé par le Q-Learning
│   └── random_agent/
│       └── agent.py      # Ancien RandomAgent, hors routeur principal
│
├── agents/
│   ├── difficulty.py           # Routage agent/profondeur (point d'entrée unique)
│   ├── random/
│   │   └── random_agent.py     # Agent aléatoire
│   ├── heuristic/
│   │   └── heuristic.py        # Fonction d'évaluation statique
│   ├── minimax/
│   │   └── minimax.py          # Minimax utilisant les règles du moteur
│   └── alpha_beta/
│       └── elagage.py          # Alpha-Bêta MAX/MIN + évaluation partagée
│
├── awale/
│   └── ai/
│       └── qlearning.py        # Agent Q-Learning persistant + curriculum
│
├── models/
│   ├── q_table_latest.json     # Dernier checkpoint Q-Learning
│   └── q_table_best.json       # Checkpoint choisi par l'évaluation interne
│
├── api/
│   └── server.py               # API REST FastAPI (sessions isolées)
│
├── web/
│   ├── index.html              # Interface HTML, plateau, configuration, modale
│   ├── app.js                  # Client JS, UX complète (toasts, animations, modale)
│   └── styles.css              # Styles, pits, graines, granaires, responsive
│
├── benchmark/                  # Tournoi, rapports et métadonnées de reproduction
├── audit/                      # Audit local uniquement, dossier ignoré par Git
├── tests/                      # Tests moteur, IA, API, benchmarks et interface
├── requirements-dev.txt        # Dépendances pour les tests API
├── main.py                     # Point d'entrée CLI, match IA vs IA en console
├── train_qlearning.py          # Lancement du curriculum d'entraînement
├── Les règles d'Awale.md       # Document de référence ; variantes régionales possibles
├── requirements.txt            # Dépendances Python
├── vercel.json                 # Configuration déploiement Vercel
└── pyproject.toml              # Entrypoint Vercel
```

---

## Installation

**Prérequis : Python 3.10+**

Exécuter les commandes depuis la racine du projet. L'audit a été réalisé avec Python 3.13.0 et Node.js 24.3.0. Node.js est nécessaire uniquement aux tests JavaScript ; l'interface web ne nécessite pas de build.

```bash
python -m pip install -r requirements.txt
```

Dépendances :

| Paquet | Version minimale | Rôle |
| --- | --- | --- |
| `fastapi` | 0.110.0 | Framework API REST |
| `uvicorn[standard]` | 0.29.0 | Serveur ASGI |
| `pydantic` | 2.0.0 | Validation des schémas de requêtes |

---

## Lancement

### Interface web (mode normal)

```bash
# 1. Démarrer le backend
uvicorn api.server:app --reload --port 8000

# 2. Ouvrir l'interface dans un navigateur
# Double-cliquer sur web/index.html
# ou servir web/ avec python -m http.server 8080 --directory web
# puis ouvrir http://localhost:8080
```

### CLI, match IA vs IA en console

```bash
python main.py
```

Le programme propose de choisir un niveau de difficulté pour chaque joueur, puis simule la partie en console avec détection de répétition de position.

### Entraînement Q-Learning

```bash
python train_qlearning.py
```

Reprend le dernier checkpoint disponible et ajoute 4 500 épisodes d'entraînement. Les checkpoints sont mis à jour dans `models/`. Pour démarrer une table neuve et conserver les modèles historiques, utiliser l'exemple de dossier isolé dans [Entraînement Q-Learning](#entraînement-q-learning).

---

## Moteur de jeu

### `engine/board.py`, Plateau

Représente le plateau Awalé : 12 cases, 4 graines chacune à l'initialisation.

```python
board.holes  # list[int] de longueur 12
             # indices 0–5  → Joueur 1 (rangée du bas)
             # indices 6–11 → Joueur 2 (rangée du haut, affichée de droite à gauche)
```

| Méthode | Description |
| --- | --- |
| `copy()` | Retourne une copie indépendante du plateau |
| `display()` | Affiche le plateau en vue miroir (J2 en haut, J1 en bas) |

---

### `engine/rules.py`, Règles

Valide les coups et distribue les graines. Toutes les méthodes sont `@staticmethod`.

| Méthode | Description |
| --- | --- |
| `is_valid_move(board, hole, player=None)` | Vérification de base : indice entier, case non vide et, si précisé, camp du joueur ; le nourrissage est vérifié par `get_valid_moves()` |
| `sow(board, hole)` | Distribue les graines en sens `+1 % 12`, saute la case de départ si tour complet (règle Kroo), retourne le dernier index |
| `get_valid_moves(board, player)` | Retourne les coups légaux, applique la règle de nourrissage par simulation |
| `simulate_move(board, hole, player)` | Sème et capture sur une copie ; retourne `(nouveau_plateau, graines_capturées)` |

**Convention d'index :** le semis incrémente l'index modulo 12 (sens anti-horaire dans la vue plateau : bas de gauche à droite, puis haut de droite à gauche).

---

### `engine/game.py`, Moteur

Orchestre une partie complète.

| Attribut | Type | Description |
| --- | --- | --- |
| `board` | `Board` | Plateau courant |
| `score_p1` | `int` | Graines capturées par le joueur 1 |
| `score_p2` | `int` | Graines capturées par le joueur 2 |
| `current_player` | `int` | Joueur actif (`1` ou `2`) |
| `plies` | `int` | Nombre de demi-coups joués |
| `max_plies` | `int` ou `None` | Limite de demi-coups, 500 par défaut ; `None` désactive cette limite |

| Méthode | Description |
| --- | --- |
| `play_move(hole)` | Retourne `True` après un coup légal ; `False` sans mutation pour un coup invalide ou après la fin |
| `capture(last_hole)` | Remonte depuis `last_hole`, capture tant que la case contient 2 ou 3 graines dans le camp adverse |
| `is_game_over()` | Victoire à ≥ 25 graines, blocage, répétition ou limite de demi-coups (500 par défaut) |
| `end_reason()` | `score`, `blocage`, `repetition`, `limite` ou `None` |
| `final_scores()` | Scores finaux avec graines résiduelles en cas de blocage, sans mutation |
| `copy()` | Copie indépendante conservant les scores et l'historique réel |
| `get_valid_moves()` | Coups légaux de la partie ; liste vide lorsqu'elle est terminée |
| `get_winner()` | Retourne `1`, `2` ou `None` (partie en cours ou nul), **idempotent, ne modifie pas l'état** |
| `get_children()` | Génère tous les états enfants pour les agents de recherche |
| `display()` | Affiche le plateau et les scores en console |

---

### `engine/env.py`, Environnement RL

Wrapper minimal autour de `Game`, avec accès au plateau. Il n'expose pas de méthode `step()` ni de récompense et n'est pas utilisé par l'agent Q-Learning actuel.

| Méthode | Description |
| --- | --- |
| `reset()` | Démarre une nouvelle partie, retourne l'état initial sous forme de liste |
| `state()` | Retourne le plateau courant sous forme de liste |

---

## Agents IA

### `agents/difficulty.py`, Routage

Module centralisé exposant deux points d'entrée :

Contrats de retour (certaines annotations du code ne mentionnent pas encore `None`) :

```text
# Entrée CLI, niveau prédéfini
choose_move(game, level: str) -> int | None

# Entrée Web UI, agent + profondeur libres
choose_move_by_agent(game, agent: str, depth: int | None = None) -> tuple[int | None, int | None]
```

**Niveaux prédéfinis (CLI) :**

| Niveau | Agent | Profondeur |
| --- | --- | --- |
| `"facile"` | Aléatoire | Sans objet |
| `"moyen"` | Minimax | 2 |
| `"difficile"` | Alpha-Bêta | 5 |
| `"expert"` | Alpha-Bêta | 8 |
| `"qlearning"` | Q-Learning | Sans objet |

**Agents disponibles (Web UI) :**

| Agent | Identifiant | Profondeurs valides |
| --- | --- | --- |
| Aléatoire | `random` | Sans objet |
| Minimax | `minimax` | 1 – 8 |
| Alpha-Bêta | `alphabeta` | 1 – 12 |
| Q-Learning | `qlearning` | Sans objet |

Le routeur valide les profondeurs et applique, si elles sont omises, Minimax 2 et Alpha-Bêta 5. Les agents sans recherche ignorent la profondeur. Une partie terminée retourne `(None, None)`.

L'agent Q-Learning est chargé paresseusement (`_get_qlearning_agent()`) : `models/q_table_best.json` est préféré pour jouer, avec repli sur `q_table_latest.json`. « Best » désigne le record d'une évaluation interne bruitée et ne garantit pas une meilleure performance sur d'autres parties. L'entraînement reprend le dernier checkpoint (`QLearningAgent(checkpoint="latest")`).

---

### `agents/random/random_agent.py`

```text
random_move(game) -> int | None
```

Choisit uniformément un coup légal du joueur courant et retourne `None` après toute fin de partie. L'ancien `engine/random_agent/agent.py` expose aussi `RandomAgent(player)` ; il refuse de jouer pour un autre joueur que celui configuré.

---

### `agents/heuristic/heuristic.py`

Fonction d'évaluation partagée par Minimax et Alpha-Bêta. Les fins de partie priment sur les composantes statiques : victoire `+999999`, défaite `-999999`, nul `0`, avec prise en compte des graines résiduelles. Toutes les méthodes sont `@staticmethod`.

```text
heuristic.evaluate(game, player) -> float
```

| Composante | Poids | Description |
| --- | --- | --- |
| Différence de captures | `1.0` | `score_joueur − score_adversaire` |
| Mobilité | `3.0` | Coups valides joueur − coups valides adversaire |
| Graines dans le camp adverse | `0.1` | Nombre de graines adverses, pondéré positivement |

Ces poids ne sont pas calibrés. L'évaluation terminale est prioritaire ; la qualité prédictive des composantes intermédiaires reste à étudier.

---

### `agents/minimax/minimax.py`

Algorithme Minimax pur avec profondeur configurable, mesurée en **demi-coups**. La perspective reste celle du joueur racine : MAX à ses tours, MIN aux tours adverses.

```python
from agents.minimax.minimax import Minimax
from engine.game import Game

game = Game()
move, nodes = Minimax(depth=2).choose_move(
    game.board, game.current_player, game.score_p1, game.score_p2, game=game
)
```

- Utilise les transitions du moteur ; `SearchState` reste disponible comme adaptateur
- Le routeur transmet aussi `game=game` pour préserver l'historique et la limite de coups
- Reçoit les **vrais scores courants** (`score1`, `score2`) pour une évaluation correcte
- Vérifie que `player` correspond au joueur actif de `game`
- Préfère une victoire immédiate à une victoire différée de même valeur ; départage les autres égalités par l'ordre mélangé des coups
- Évaluation terminale via `heuristic.evaluate()`

Retour : `(indice_absolu, nœuds)` ou `(None, 1)` si la partie est terminée. Créer une instance par recherche concurrente pour isoler le compteur.

---

### `agents/alpha_beta/elagage.py`

Alpha-Bêta utilise la formulation MAX/MIN avec le joueur racine comme perspective fixe.

```text
best_move(game, depth=5) -> tuple[int | None, int]
# Retourne : (case jouée, nombre de nœuds explorés)
```

Minimax et Alpha-Bêta partagent les règles, les fins de partie et l'évaluation de `agents/heuristic/heuristic.py`. À profondeur égale, leurs coups ont la même valeur ; Minimax mélange les coups, Alpha-Bêta parcourt les indices croissants. Les victoires immédiates priment en cas d'égalité. Le compteur Alpha-Bêta est propre à chaque recherche. Une partie terminée retourne `(None, 1)`.

L'élagage s'arrête lorsque `alpha >= beta`. Il n'y a pas de tri stratégique des coups, de table de transposition ni de budget de temps. La recherche choisit un coup optimal pour son horizon et son heuristique ; cela ne garantit pas le meilleur coup jusqu'à la fin de la partie.

---

### `awale/ai/qlearning.py`

Agent Q-Learning tabulaire avec encodage symétrique et curriculum d'entraînement progressif.

```text
QLearningAgent().choose_move(game, greedy=True) -> int | None
```

**Encodage de l'état :**

```
"mes_trous|trous_adversaire|score_moi|score_lui"
```

Grâce à cette symétrie, la même Q-Table fonctionne pour les deux joueurs. Les actions sont encodées en indices relatifs (0–5) plutôt qu'absolus (0–11).

La clé omet l'historique des répétitions et le budget de demi-coups restant : elle ne représente pas l'état complet du moteur. La politique sélectionne uniquement des coups légaux et retourne `None` après la fin. En mode greedy, les égalités favorisent la première action légale ; une table vide joue donc le premier coup légal.

**Mise à jour :**

```text
Q(s,a) ← Q(s,a) + alpha × (r + gamma × max_{a' légal} Q(s',a') − Q(s,a))
```

Pour un état terminal, la cible est uniquement `r`, sans bootstrap. `greedy=True` force l'exploitation ; sinon la politique explore avec probabilité epsilon.

**Hyperparamètres :**

| Paramètre | Valeur | Description |
| --- | --- | --- |
| `ALPHA` | 0.15 | Taux d'apprentissage constant |
| `GAMMA` | 0.95 | Actualisation par transition entre décisions du même joueur |
| `EPSILON_START` | 1.00 | Taux d'exploration initial |
| `EPSILON_MIN` | 0.05 | Taux d'exploration plancher |

Les paramètres doivent être finis et respecter `0 < alpha <= 1`, `0 <= gamma <= 1`, `0 <= epsilon_min <= epsilon <= 1`. Epsilon diminue linéairement jusqu'au plancher pendant chaque phase.

**Récompenses :**

| Événement | Récompense |
| --- | --- |
| Victoire | +100 |
| Défaite | −100 |
| Égalité | 0 |
| Capture | +2 par graine |
| Capture adverse | −2 par graine |
| Pénalité temporelle | −0.5 par décision de l'agent |

**Curriculum d'entraînement (`run_curriculum`) :**

| Phase | Adversaire | Parties |
| --- | --- | --- |
| 1 | Agent aléatoire | 1 000 |
| 2.1 – 2.5 | Alpha-Bêta profondeur 1 à 5 | 500 × 5 |
| 3 | Self-play | 1 000 |

Un checkpoint "champion" est sauvegardé après chaque phase si le taux de victoire de l'évaluation interne dépasse le record. Cela ne prouve pas une progression générale.

Une transition relie deux tours du même joueur, après la réponse réelle de l'adversaire. Les récompenses utilisent les captures effectives et le bootstrap prend le maximum des actions légales de cet état suivant. Les erreurs des agents sont signalées. Les Q-tables historiques ont été entraînées avant ces corrections : leur niveau ne valide pas le nouvel apprentissage.

Les nouveaux checkpoints version 2 sauvegardent la table, `alpha`, `gamma`, `epsilon`, `epsilon_min`, le décrément d'epsilon, les compteurs et l'identifiant d'encodage. Les anciens fichiers version 1 restent lisibles ; leurs paramètres absents utilisent les valeurs de construction. Le chargement valide le fichier avant application, et la sauvegarde remplace atomiquement la destination. Le RNG et la phase d'entraînement ne sont pas persistés.

---

## API REST

Backend FastAPI avec parties isolées et coups versionnés.

**Lancement :**

```bash
uvicorn api.server:app --reload --port 8000
```

| Endpoint | Méthode | Description |
| --- | --- | --- |
| `/api/game/start` | `POST` | Démarre une partie, retourne l'état initial et son `game_id` |
| `/api/game/{game_id}` | `GET` | Relit l'état de cette partie |
| `/api/game/move` | `POST` | Applique un coup humain, retourne le nouvel état |
| `/api/game/ai-move` | `POST` | Fait jouer l'IA (agent + profondeur libres), retourne état + télémétrie |
| `/api/agents` | `GET` | Liste les agents disponibles et leurs profondeurs valides |
| `/` | `GET` | Health check |

**État de jeu retourné par `/api/game/start`, `/api/game/{game_id}` et `/api/game/move`, ou sous `game_state` par `/api/game/ai-move` :**

```json
{
  "game_id": "123e4567-e89b-42d3-a456-426614174000",
  "version": 0,
  "end_reason": null,
  "board": [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
  "scores":    { "player1": 0, "player2": 0 },
  "granaries": { "player1": 0, "player2": 0 },
  "current_player": "player1",
  "game_over": false,
  "winner": null,
  "valid_moves": [0, 1, 2, 3, 4, 5]
}
```

**Payload `POST /api/game/start` :**

```json
{
  "player1": { "name": "Alice", "type": "human" },
  "player2": { "name": "IA",    "type": "ai"    }
}
```

**Payload `POST /api/game/move` :**

```json
{
  "game_id": "123e4567-e89b-42d3-a456-426614174000",
  "version": 0,
  "pit_index": 3,
  "player": "player1"
}
```

**Payload `POST /api/game/ai-move` :**

```json
{
  "game_id": "123e4567-e89b-42d3-a456-426614174000",
  "version": 1,
  "player": "player2",
  "agent": "alphabeta",
  "depth": 6
}
```

**Réponse `POST /api/game/ai-move` :**

Exemple après le coup humain `3`, puis le coup Alpha-Bêta `9` ; les temps dépendent de la machine. Remplacer le `game_id` illustratif par celui retourné au démarrage dans les requêtes.

```json
{
  "game_state": {
    "game_id": "123e4567-e89b-42d3-a456-426614174000",
    "version": 2,
    "board": [5, 5, 4, 0, 5, 5, 5, 5, 4, 0, 5, 5],
    "scores": { "player1": 0, "player2": 0 },
    "granaries": { "player1": 0, "player2": 0 },
    "current_player": "player1",
    "game_over": false,
    "end_reason": null,
    "winner": null,
    "valid_moves": [0, 1, 2, 4, 5]
  },
  "telemetry": {
    "computation_time": 146.4,
    "depth": 6,
    "nodes_explored": 4160,
    "win_rate": null,
    "pit_played": 9,
    "agent": "alphabeta"
  }
}
```

Chaque coup exige le `game_id` retourné au démarrage et la dernière `version`. Une version ou un plateau périmé est refusé avec HTTP 409 ; un mauvais joueur, un mauvais type de joueur ou une profondeur hors limites avec HTTP 400. Les champs de type incorrect sont refusés avec HTTP 422. Les appels d'une même partie sont sérialisés.

Les sessions sont conservées en mémoire dans **un seul processus ASGI**, expirent après une heure d'inactivité et sont limitées à 256 parties actives. Elles disparaissent au redémarrage ; lancer plusieurs workers ou utiliser un hébergement serverless nécessite un stockage partagé.

---

## Interface Web

Interface jouable dans un navigateur, **sans build ni installation**.  
Icônes **Font Awesome 6** (CDN). Aucune dépendance JS additionnelle.

L'URL de l'API est sélectionnée selon l'hôte de la page :

- `localhost`, `127.0.0.1` ou ouverture directe du fichier → `http://localhost:8000`
- Tout autre hôte → `https://awale-ai-backend.onrender.com` (adresse configurée dans `web/app.js`, disponibilité non vérifiée)

### Configuration des joueurs

Chaque joueur est configurable indépendamment avant le lancement d'une partie :

| Paramètre | Valeurs |
| --- | --- |
| **Type de joueur** | Humain / Agent IA |
| **Nom du joueur** | Facultatif, 80 caractères maximum |
| **Agent IA** | Aléatoire / Minimax / Alpha-Bêta / Q-Learning |
| **Profondeur de recherche** | Valeur affichée en niveaux, masquée pour les agents sans recherche |

L'interface choisit initialement Minimax 5 et Alpha-Bêta 6 lorsqu'on sélectionne ces agents. Ces valeurs sont envoyées explicitement à l'API ; elles diffèrent des valeurs du routeur lorsqu'aucune profondeur n'est fournie. Un demi-coup correspond au tour d'un joueur. Les options affichent « Niveau 8 » à « Niveau 1 » pour Minimax et « Niveau 12 » à « Niveau 1 » pour Alpha-Bêta, dans l'ordre décroissant. Une reconstruction du sélecteur pour le même agent conserve la sélection. Ces libellés et cet ordre ne changent ni les valeurs transmises ni leur interprétation algorithmique.

Une courte explication accompagne chaque agent ; le Q-Learning est signalé comme expérimental. Les réglages sont verrouillés pendant la partie et réactivés après l'abandon ou la fin.

### Plateau de jeu

- De 1 à 6 graines : disposition régulière ; au-delà : maille hexagonale symétrique, taille adaptée à la densité, positions relatives à la case et mises en cache dans `SEED_LAYOUTS`
- **Cases jouables** : anneau doré (`pit--playable`), cases invalides grisées (`pit--disabled`)
- **Animation du semis** case par case à 110 ms/étape (`animateSow`)
- **Flash rouge** (`pit--captured`) sur les cases capturées après semis
- **Granaires** animés avec graines positionnées aléatoirement en cache
- **Indicateur de joueur actif** : bordure dorée sur la score-box du joueur courant
- **Compte des graines** séparé sous chaque case pour ne masquer aucune graine ; toutes les graines sont rendues, même dans une case contenant les 48 graines
- **Clavier** : Tab pour accéder aux cases légales, flèches gauche/droite dans l'ordre visuel, Entrée ou Espace pour jouer
- **Mobile** : le démarrage ramène au plateau ; les grands blocs conservent leur disposition

### Boutons

| Bouton | Comportement |
| --- | --- |
| **Nouvelle partie / Recommencer** | Appelle `POST /api/game/start`, confirme le remplacement d'une partie en cours et lance automatiquement l'IA si nécessaire |
| **Abandonner la partie** | Annule les requêtes côté client et ignore les réponses, animations ou tours programmés de la partie arrêtée |

### Modale de fin de partie

Apparaît automatiquement 600 ms après la dernière animation :

- **Victoire** : icône trophée doré, nom du vainqueur, confettis CSS
- **Match nul** : icône `handshake`, message adapté, pas de confettis
- **Scores** des deux joueurs avec encadré doré sur le gagnant
- **Cause de fin** : seuil de capture, blocage, répétition ou limite de coups ; un nul peut avoir des scores différents
- Boutons **Rejouer** et **Fermer**, fermable aussi via `Escape` ou clic sur l'overlay
- Focus clavier contenu dans la fenêtre, arrière-plan inactif, focus restauré à la fermeture et contenu défilant sur petit écran

### Notifications (toasts)

Notifications contextuelles en bas à droite, disparition automatique, limitées à deux et effacées à l'ouverture du résultat. Elles n'interceptent pas les clics sur les commandes du jeu :

| Situation | Type |
| --- | --- |
| Partie démarrée | Succès (vert) |
| Serveur inaccessible | Erreur (rouge) |
| Partie abandonnée | Avertissement (orange) |
| Coup refusé par l'API | Avertissement (orange) |
| Erreur IA / réseau | Erreur (rouge) |

### Panneau « Analyse de la décision de l’IA »

- **Barre de temps de calcul** animée avec couleur adaptative :
  - vert < 200 ms
  - or < 800 ms
  - rouge ≥ 800 ms
- **Profondeur de recherche** : valeur affichée en niveaux (ex. `6 niveaux`)
- **Positions évaluées** : nombre formaté avec séparateurs (`12 345`). La donnée `nodes_explored` compte les positions visitées, racine comprise, et non uniquement les appels à l'évaluation heuristique. Une infobulle précise cette différence.
- **Taux de victoire** : champ masqué avec l'API actuelle, qui renvoie `win_rate: null`. Aucun résultat d'entraînement n'est fourni par cette route.
- Message d'aide initial jusqu'au premier coup IA

### Panneau Statut

Pastille colorée avec indicateur d'état :

| État | Couleur | Animation |
| --- | --- | --- |
| En attente | Gris | Aucune |
| Tour joueur | Vert forêt | pulsation |
| Calcul de l'agent IA | Violet | pulsation |
| Victoire | Vert | Aucune |
| Match nul | Ambre | Aucune |
| Erreur | Rouge | Aucune |

Le panneau contient une aide « Règles du jeu » repliable, avec les règles de la variante locale et les commandes clavier.

### Historique des coups

Liste scrollable des coups joués avec : numéro de tour, joueur, rangée et case jouée, graines capturées.

La règle typographique du projet est définie dans [AGENTS.md](AGENTS.md) : aucun tiret cadratin dans les textes, le code commenté ou la documentation.

---

## Entraînement Q-Learning

```bash
python train_qlearning.py
```

Le script lance `run_curriculum(agent)` qui enchaîne les phases suivantes :

```
Phase 1, vs Random        : 1 000 parties
Phase 2.1, vs AB depth=1  :   500 parties
Phase 2.2, vs AB depth=2  :   500 parties
Phase 2.3, vs AB depth=3  :   500 parties
Phase 2.4, vs AB depth=4  :   500 parties
Phase 2.5, vs AB depth=5  :   500 parties
Phase 3, Self-Play        : 1 000 parties
```

À chaque changement de phase, epsilon remonte de `+0.15` (relance l'exploration).  
Après chaque phase, une évaluation "Champion" sur 100 parties décide si `q_table_best.json` est mis à jour.

Cette évaluation alterne les camps et mélange 52 parties contre random, 24 contre Alpha-Bêta profondeur 2 et 24 contre profondeur 3. Le record enregistré n'est ni une probabilité de gagner la partie courante ni une garantie de supériorité sur `latest`.

**Fichiers produits :**

| Fichier | Contenu |
| --- | --- |
| `models/q_table_latest.json` | Dernier état de la Q-Table |
| `models/q_table_best.json` | Table et paramètres du checkpoint ayant dépassé le record interne |

**Entraîner une table neuve dans un dossier distinct, en conservant les fichiers historiques :**

```python
import random
from awale.ai.qlearning import QLearningAgent, run_curriculum

random.seed(7)
agent = QLearningAgent(model_dir="models/experiment_seed_7", load_models=False)
run_curriculum(agent)
```

Ce code lance les 4 500 épisodes et écrit dans `models/experiment_seed_7/`. Le chargement d'un modèle de ce dossier se fait avec `QLearningAgent(model_dir="models/experiment_seed_7", checkpoint="latest")`.

---

## Règles implémentées

- Le premier joueur est toujours J1 dans le moteur
- Distribution circulaire en sens `+1 % 12` (anti-horaire sur le plateau physique)
- La case de départ est sautée si le nombre de graines est > 11 (**règle Kroo**)
- **Capture** : si la dernière case atteinte contient exactement 2 ou 3 graines dans le camp adverse, ces graines sont capturées ; la capture remonte les cases précédentes tant que la condition est remplie
- **Règle de nourrissage** : un coup n'est valide que s'il ne laisse pas l'adversaire sans graines, sauf si aucun tel coup n'existe
- **Fin de partie** : victoire à 25 graines, blocage, premier retour d'une position identique (plateau, scores et joueur actif) ou limite de demi-coups
- Les répétitions et limites sont des nuls, même si un joueur mène au score
- En cas de blocage, les graines restantes sur le plateau sont attribuées à l'adversaire du joueur bloqué
- **Égalité** si les deux joueurs finissent avec exactement 24 graines

Ces règles décrivent la variante locale. Le [document de référence](<Les règles d'Awale.md>) mentionne notamment un premier joueur tiré au sort et une répétition indéfinie ; le moteur applique les conventions explicites ci-dessus. L'abandon n'est pas une transition du moteur. La conformité à un règlement officiel externe n'a pas été certifiée.

---

## Tests et benchmarks

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node --test tests/test_web.cjs
```

Les tests couvrent l'affamement dans les deux camps, le Kroo, la conservation des graines, les victoires immédiates, l'équivalence des recherches, les transitions Q-Learning, les sessions concurrentes et l'arrêt des requêtes web.

Au 21 novembre 2026, la dernière validation Python rapporte **58 tests réussis**, dont huit contrôles du protocole de benchmark. Le frontend dispose de **8 tests JavaScript réussis** : les régressions de requêtes, d'annulation et de captures terminales sont complétées par un contrôle géométrique exhaustif des 0 à 48 graines par case. Les tests unitaires et les expériences de force de jeu sont présentés séparément dans les rapports ; des tests réussis ne prouvent pas la performance des algorithmes.

```bash
python -X utf8 -u benchmark/run_50.py
# Vérifier les résultats existants, sans nouvelles confrontations :
python -X utf8 benchmark/run_50.py --verify-only
# Relancer 50 parties dans un nouveau dossier vide :
python -X utf8 -u benchmark/run_50.py --output benchmark/results/reproduction_50
```

Le [benchmark de présentation](benchmark/README.md) joue exactement **50 parties au total**, réparties en quatre duels de 8 et deux duels de 9. Chaque agent joue 25 parties, avec alternance des camps et ouvertures appariées. Minimax et Alpha-Bêta utilisent la profondeur 3 ; Q-Learning utilise le checkpoint historique `best`, en exploitation sans apprentissage. Le script refuse de remplacer des résultats déjà présents.

Les [résultats mesurés](benchmark/results/presentation_50/summary.md) donnent : Random 1 victoire, 1 nul et 23 défaites ; Minimax 17 victoires, 3 nuls et 5 défaites ; Alpha-Bêta 21 victoires, 3 nuls et 1 défaite ; Q-Learning 7 victoires, 1 nul et 17 défaites. Les taux de victoire utilisent le dénominateur 25, nuls inclus : 4 %, 68 %, 84 % et 28 %.

Un seul [graphique PNG 16:9 en palette bleue](benchmark/results/presentation_50/benchmark_50.png), de 4800 × 2700 pixels à 300 dpi, représente les victoires, nuls et défaites en barres empilées. Le CSV conserve les 50 identifiants, les agents, graines, positions, durées et trajectoires. Les résumés et métadonnées enregistrent les paramètres et les empreintes des sources et Q-tables. Les trajets sont vérifiés avec le moteur sans nouvelles décisions des agents ; les valeurs du PNG sont contrôlées contre le CSV. Les modèles historiques restent inchangés.

Les taux de victoire décrivent ce protocole et ces modèles ; ils ne constituent pas une preuve de supériorité générale d'un algorithme.

La [validation de l'interface dans Edge](audit/results/browser_2026-11-21/REPORT.md) couvre **14 scénarios réussis** : humain/humain, humain/IA, les quatre agents sélectionnés, arrêt pendant un semis ou une requête IA, redémarrage, replay, victoire, nul par répétition et blocage, historique des captures et affichage mobile. Le rapport distingue les parcours standard, les parties accélérées et les positions construites. La validation utilise l'API réelle sur un port local isolé ; les icônes du CDN ne sont pas vérifiées.

La [validation UX et rédactionnelle](audit/results/ux_2026-11-21/REPORT.md) complète ce contrôle avec **23 scénarios navigateur réussis**. Elle vérifie le clavier, la gestion du focus, les réglages verrouillés, les erreurs de connexion, les profondeurs décroissantes sans altération des valeurs API et 196 rendus de cases (0 à 48 graines sur des largeurs de 320, 390, 900 et 1 400 pixels). Les fixtures de densité conservent 48 graines au total. À très forte densité sur mobile, les graines deviennent petites ; le compteur numérique donne la quantité exacte.

```bash
# Validation navigateur locale sous Windows avec Edge installé
node audit/browser_validation.cjs
```

Le script utilise les ports locaux 18000, 18080 et 19222, et arrête les processus qu'il a lancés. Le dossier `audit/` entier est ignoré par Git et conservé uniquement en local, avec ses scripts, rapports et résultats. Les modèles historiques dans `models/` restent disponibles pour le suivi Git.

---

## Audit technique des agents

Les liens vers les rapports et résultats ci-dessous concernent les fichiers de l'environnement local ; le dossier `audit/` n'est pas versionné.

Le [rapport détaillé du 21 novembre 2026](audit/results/agents_2026-11-21/REPORT.md) décrit les défauts reproduits, les corrections locales, les protocoles, les limites et les commandes de reproduction. Les expériences Q utilisent des tables initialement vides dans le dossier d'audit ; les modèles historiques sont restés inchangés.

| Agent | Verdict de l'audit | Portée |
| --- | --- | --- |
| Aléatoire, principal et ancien | Correctement implémenté après corrections | Coups légaux, joueur actif et terminaux respectés |
| Minimax | Correct avec réserves | Recherche correcte pour son horizon et son heuristique ; poids non calibrés |
| Alpha-Bêta | Correct avec réserves | Élagage correct et valeurs cohérentes avec Minimax ; coût dépendant de la position |
| Q-Learning | Incomplet | Bellman et alternance corrects, mais état incomplet et progression générale non démontrée |

- **Cohérence des recherches :** 2 400 comparaisons sur 600 positions aux profondeurs 1 à 4, sans désaccord avec l'oracle indépendant ; 8 000 vérifications supplémentaires sur des arbres synthétiques.
- **Performance Alpha-Bêta :** environ 3× plus rapide et 65,5 % de nœuds en moins sur 100 positions à profondeur 4, avec cinq répétitions. Ce gain est propre au protocole mesuré.
- **Q-Learning :** trois graines après 6 000 épisodes contre random et un curriculum réduit ne montrent pas de progression générale fiable. Un entraînement tactique restreint passe de 0/4 à 4/4 sur les positions répétées et leurs symétries.
- **Curriculum complet :** sur une graine et 4 500 épisodes, `latest` obtient 112 victoires sur 200 contre random sans ouverture, contre 101 pour la table vide ; l'intervalle de variation à 95 % [−4 ; +15 points] contient zéro. Le checkpoint `best` n'en obtient que 77 sur ce même protocole indépendant.

La [synthèse JSON](audit/results/agents_2026-11-21/summary.json) et les [courbes d'apprentissage](audit/results/agents_2026-11-21/learning_curves.png) permettent de consulter les résultats. L'absence de progression démontrée ne signifie pas absence d'apprentissage local. L'état Q omet l'historique et la limite de coups ; l'équivalence entre récompenses actualisées et maximisation des victoires reste à étudier.

---

## Roadmap

| Phase | Objectif | Statut |
| --- | --- | --- |
| **Phase 1** | Moteur de jeu : plateau, règles, captures, scores | Implémenté et vérifié pour la variante locale ; conformité officielle non certifiée |
| **Phase 2** | IA classique + Interface : Aléatoire, Heuristique, Minimax, Alpha-Bêta, API REST, Web UI | Disponibles ; recherches auditées, heuristique et coûts aux grandes profondeurs à étudier |
| **Phase 3** | IA par renforcement : Q-Learning tabulaire + curriculum | Expérimental ; état complet et progression générale à améliorer et valider |
| **Phase 4** | Tests automatisés, benchmark inter-agents et documentation | ✅ Disponibles ; démo à finaliser |
