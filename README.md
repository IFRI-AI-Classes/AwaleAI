# AwaleAI

Moteur de jeu Awalé en Python, développé en architecture modulaire.  
Le projet couvre les règles complètes, plusieurs agents IA (Aléatoire, Heuristique, Minimax, Alpha-Beta) et une interface web interactive connectée à une API REST FastAPI.

---

## Architecture

```
AwaleAI/
├── engine/
│   ├── board.py          # Modélisation du plateau (12 cases)
│   ├── rules.py          # Règles, distribution des graines, coups valides
│   ├── game.py           # Moteur de jeu, captures, scores, fin de partie
│   └── env.py            # Environnement RL (AwaleEnv) — base Phase 3
│
├── agents/
│   ├── random/
│   │   └── random_agent.py     # Agent aléatoire
│   ├── heuristic/
│   │   └── heuristic.py        # Fonction d'évaluation (diff, mobilité, graines)
│   ├── minimax/
│   │   └── minimax.py          # Minimax avec heuristique
│   └── alpha_beta/
│       └── elagage.py          # Alpha-Beta avec élagage + évaluation avancée
│
├── api/
│   └── server.py         # API REST FastAPI (3 endpoints)
│
├── web/
│   ├── index.html        # Interface HTML (plateau, config joueurs, télémétrie)
│   ├── app.js            # Client JS — communication REST + animation des semis
│   └── styles.css        # Styles de l'interface
│
├── main.py               # Point d'entrée CLI — match IA vs IA (Alpha-Beta vs Minimax)
├── test_heuristic.py     # Tests manuels de la fonction heuristique
└── requirements.txt      # Dépendances Python (FastAPI, Uvicorn, Pydantic)
```

---

## Modules

### `engine/board.py` — Plateau de jeu

Représente le plateau Awalé : 12 cases, 4 graines chacune à l'initialisation.

```python
board.holes  # list[int] de longueur 12
             # indices 0–5  → Joueur 1
             # indices 6–11 → Joueur 2
```

**Méthode :**
- `display()` — affiche le plateau en vue miroir (J2 en haut, J1 en bas)

---

### `engine/rules.py` — Règles

Valide les coups et distribue les graines.

| Méthode | Description |
|---|---|
| `is_valid_move(board, hole, player)` | Vérifie que la case existe, n'est pas vide et appartient au bon joueur |
| `sow(board, hole)` | Distribue les graines dans le sens horaire, saute la case de départ, retourne le dernier index |
| `get_valid_moves(board, player)` | Retourne la liste de tous les coups valides (gère la règle de nourrissage) |

---

### `engine/game.py` — Moteur de jeu

Orchestre une partie complète.

| Attribut | Type | Description |
|---|---|---|
| `board` | `Board` | Plateau courant |
| `score_p1` | `int` | Graines capturées par le joueur 1 |
| `score_p2` | `int` | Graines capturées par le joueur 2 |
| `current_player` | `int` | Joueur actif (`1` ou `2`) |

**Méthodes principales :**
- `play_move(hole)` — valide, sème, capture, met à jour le score, change de joueur
- `capture(last_hole)` — remonte depuis `last_hole`, capture tant que la case contient `2` ou `3` graines
- `is_game_over()` — détecte la fin de partie (blocage ou score > 24)
- `get_winner()` — retourne `1`, `2` ou `None` (égalité)
- `get_children()` — génère tous les états enfants (utilisé par Alpha-Beta)

---

### `engine/env.py` — Environnement RL

Couche d'abstraction pour les agents d'apprentissage par renforcement (Phase 3).

- `reset()` — démarre une nouvelle partie, retourne l'état initial
- `state()` — retourne le plateau courant sous forme de liste

---

## Agents IA

### `agents/random/random_agent.py`

```python
random_move(game) -> int
```
Choisit un coup valide au hasard parmi les coups légaux du joueur courant.

---

### `agents/heuristic/heuristic.py`

Fonction d'évaluation statique utilisée par Minimax et Alpha-Beta.

```python
heuristic.evaluate(game, player) -> float
```

| Composante | Poids | Description |
|---|---|---|
| Différence de captures | `1.0` | `score_joueur − score_adversaire` |
| Mobilité | `3.0` | Nombre de coups valides du joueur − adversaire |
| Graines dans le camp adverse | `0.1` | Pression offensive |

---

### `agents/minimax/minimax.py`

Algorithme Minimax pur avec profondeur configurable.

```python
Minimax(depth=4).choose_move(board, player) -> int
```

- Utilise `SearchState` (structure légère) pour simuler les coups sans modifier le jeu
- Évaluation terminale via `heuristic.evaluate()`
- Gère la règle de nourrissage via `Rules.get_valid_moves()`

---

### `agents/alpha_beta/elagage.py`

Alpha-Beta avec négamax et élagage.

```python
best_move(game, depth=6) -> int
```

**Fonction d'évaluation propre (`evaluate`) :**

| Composante | Poids | Description |
|---|---|---|
| Différence de captures | `100` | Priorité maximale |
| Opportunités de capture | `10` | Cases adverses à 2 ou 3 graines |
| Mobilité | `5` | Coups valides joueur − adversaire |
| Contrôle du plateau | `0.5` | Total des graines dans son camp |

Détecte aussi les fins de partie immédiates (victoire/défaite/égalité par blocage).

---

## API REST — `api/server.py`

Backend FastAPI exposant trois endpoints pour le frontend web.

**Lancement :**
```bash
uvicorn api.server:app --reload --port 8000
```

| Endpoint | Méthode | Description |
|---|---|---|
| `/api/game/start` | `POST` | Démarre une partie, retourne l'état initial |
| `/api/game/move` | `POST` | Applique un coup humain, retourne le nouvel état |
| `/api/game/ai-move` | `POST` | Fait jouer l'IA, retourne état + télémétrie |
| `/` | `GET` | Health check |

**Algorithmes disponibles via l'API :**

| Valeur (`algorithm`) | Agent |
|---|---|
| `"random"` | Agent aléatoire |
| `"minimax"` | Minimax (profondeur 7) |
| `"alphabeta"` | Alpha-Beta (profondeur 7) |
| `"qlearning"` | *(Phase 3 — repli sur aléatoire)* |

**Structure de la réponse `/api/game/ai-move` :**
```json
{
  "game_state": { "board": [...], "scores": {...}, "current_player": "player1", "game_over": false, ... },
  "telemetry":  { "computation_time": 42.1, "depth": 7, "nodes_explored": null, "pit_played": 3, ... }
}
```

---

## Interface Web — `web/`

Interface jouable accessible dans un navigateur, sans build.

**Fonctionnalités :**
- Plateau visuel avec rendu des graines par case
- Granaries (greniers) animés pour chaque joueur
- Configuration indépendante de chaque joueur (Humain ou IA + choix d'algorithme)
- Animation du semis case par case (séquence `+1 graine` par pas)
- Historique des coups avec captures
- Panneau de télémétrie (temps de calcul, profondeur, nœuds)
- Partie IA vs IA automatique

**Lancement :**
Ouvrir `web/index.html` directement dans un navigateur (le backend doit tourner sur `localhost:8000`).

---

## Point d'entrée CLI — `main.py`

Lance un match **Alpha-Beta (J1) vs Minimax (J2)** en console, avec :
- Détection de répétition de position (nulle)
- Limite de 500 tours
- Affichage du vainqueur et des scores finaux

```bash
python main.py
```

---

## Installation

```bash
pip install -r requirements.txt
```

Prérequis : Python 3.10+

---

## Règles implémentées

- Distribution circulaire dans le sens horaire (sens `+1 % 12`)
- La case de départ est sautée si le tour est assez long pour y revenir
- Capture si la dernière case contient exactement `2` ou `3` graines
- La capture remonte les cases précédentes tant que la condition est remplie
- Règle de nourrissage : un coup n'est valide que s'il ne laisse pas l'adversaire sans graines (sauf si impossible)
- Fin de partie par blocage ou lorsqu'un joueur dépasse 24 graines capturées

---

## Roadmap

| Phase | Objectif | Tâches | Statut |
|---|---|---|---|
| **Phase 1** | Moteur de jeu | Étude des règles · Modélisation du plateau · Développement du moteur · Gestion des scores | ✅ Terminé |
| **Phase 2** | IA classique | Agent aléatoire · Heuristique · Minimax · Alpha-Beta · API REST · Interface web | ✅ Terminé |
| **Phase 3** | IA par renforcement | Étude du RL · Implémentation Q-Learning · Entraînement des agents | 🔲 À venir |
| **Phase 4** | Finalisation | Benchmark · Documentation complète · Préparation démonstration | 🔲 À venir |
