# AwaleAI

Moteur de jeu Awalé en Python, développé en architecture modulaire.  
Le projet couvre les règles complètes, plusieurs agents IA (Aléatoire, Minimax, Alpha-Beta, Q-Learning) et une interface web interactive connectée à une API REST FastAPI.

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
│   ├── difficulty.py           # Routage agent/profondeur (choose_move + choose_move_by_agent)
│   ├── random/
│   │   └── random_agent.py     # Agent aléatoire
│   ├── heuristic/
│   │   └── heuristic.py        # Fonction d'évaluation statique (@staticmethod)
│   ├── minimax/
│   │   └── minimax.py          # Minimax avec scores réels
│   └── alpha_beta/
│       └── elagage.py          # Alpha-Beta négamax + évaluation avancée
│
├── awale/
│   └── ai/
│       └── qlearning.py        # Agent Q-Learning persistant
│
├── api/
│   └── server.py         # API REST FastAPI (4 endpoints)
│
├── web/
│   ├── index.html        # Interface HTML — Font Awesome, modale, plateau, config
│   ├── app.js            # Client JS — UX complète (toasts, modale, analyse, animations)
│   └── styles.css        # Styles — pits, états visuels, modale, toasts, responsive
│
├── main.py               # Point d'entrée CLI — match IA vs IA en console
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

**Méthodes :**

- `copy()` — retourne une copie indépendante du plateau
- `display()` — affiche le plateau en vue miroir (J2 en haut, J1 en bas)

---

### `engine/rules.py` — Règles

Valide les coups et distribue les graines.

| Méthode | Description |
| --- | --- |
| `is_valid_move(board, hole, player)` | Vérifie que la case existe, n'est pas vide et appartient au bon joueur |
| `sow(board, hole)` | Distribue les graines dans le sens `+1 % 12`, saute la case de départ, retourne le dernier index |
| `get_valid_moves(board, player)` | Retourne les coups légaux (gère la règle de nourrissage par simulation) |

---

### `engine/game.py` — Moteur de jeu

Orchestre une partie complète.

| Attribut | Type | Description |
| --- | --- | --- |
| `board` | `Board` | Plateau courant |
| `score_p1` | `int` | Graines capturées par le joueur 1 |
| `score_p2` | `int` | Graines capturées par le joueur 2 |
| `current_player` | `int` | Joueur actif (`1` ou `2`) |

**Méthodes principales :**

- `play_move(hole)` — valide, sème, capture, met à jour le score, change de joueur
- `capture(last_hole)` — remonte depuis `last_hole`, capture tant que la case contient `2` ou `3` graines
- `is_game_over()` — détecte la fin de partie (blocage ou score > 24)
- `get_winner()` — retourne `1`, `2` ou `None` (égalité) — **idempotent, ne modifie pas l'état**
- `get_children()` — génère tous les états enfants (utilisé par Alpha-Beta)

---

### `engine/env.py` — Environnement RL

Couche d'abstraction pour les agents d'apprentissage par renforcement (Phase 3).

- `reset()` — démarre une nouvelle partie, retourne l'état initial
- `state()` — retourne le plateau courant sous forme de liste

---

## Agents IA

### `agents/difficulty.py` — Routage des agents

Module centralisé exposant deux points d'entrée :

```python
# Entrée CLI — niveau prédéfini
choose_move(game, level: str) -> int

# Entrée Web UI — agent + profondeur libres
choose_move_by_agent(game, agent: str, depth: int | None) -> int
```

**Niveaux prédéfinis (CLI / rétrocompatibilité) :**

| Niveau | Agent | Profondeur |
| --- | --- | --- |
| `"facile"` | Aléatoire | — |
| `"moyen"` | Minimax | 2 |
| `"difficile"` | Alpha-Beta | 5 |
| `"expert"` | Alpha-Beta | 8 |
| `"qlearning"` | Q-Learning | — |

**Agents disponibles (Web UI) :**

| Agent | Identifiant | Profondeurs valides |
| --- | --- | --- |
| Aléatoire | `random` | — |
| Minimax | `minimax` | 1 – 8 |
| Alpha-Beta | `alphabeta` | 1 – 12 |
| Q-Learning | `qlearning` | — |

---

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
| --- | --- | --- |
| Différence de captures | `1.0` | `score_joueur − score_adversaire` |
| Mobilité | `3.0` | Coups valides joueur − adversaire |
| Graines dans le camp adverse | `0.1` | Pression offensive |

> Toutes les méthodes sont décorées `@staticmethod`.

---

### `agents/minimax/minimax.py`

Algorithme Minimax pur avec profondeur configurable.

```python
Minimax(depth=2).choose_move(board, player, score1=0, score2=0) -> int
```

- Utilise `SearchState` (structure légère) pour simuler les coups sans modifier le jeu
- Reçoit les **vrais scores courants** de la partie (`score1`, `score2`) pour une évaluation correcte en fin de partie
- Évaluation terminale via `heuristic.evaluate()`

---

### `agents/alpha_beta/elagage.py`

Alpha-Beta avec négamax et élagage.

```python
best_move(game, depth=5) -> int
```

**Fonction d'évaluation propre (`evaluate`) :**

| Composante | Poids | Description |
| --- | --- | --- |
| Différence de captures | `100` | Priorité maximale |
| Opportunités de capture | `10` | Cases adverses à 2 ou 3 graines |
| Mobilité | `5` | Coups valides joueur − adversaire |
| Contrôle du plateau | `0.5` | Total des graines dans son camp |

Détecte aussi les fins de partie immédiates (victoire/défaite/égalité par blocage).

---

## API REST — `api/server.py`

Backend FastAPI exposant quatre endpoints pour le frontend web.

**Lancement :**

```bash
uvicorn api.server:app --reload --port 8000
```

| Endpoint | Méthode | Description |
| --- | --- | --- |
| `/api/game/start` | `POST` | Démarre une partie, retourne l'état initial |
| `/api/game/move` | `POST` | Applique un coup humain, retourne le nouvel état |
| `/api/game/ai-move` | `POST` | Fait jouer l'IA (agent + profondeur libres), retourne état + analyse |
| `/api/agents` | `GET` | Liste les agents disponibles et leurs profondeurs valides |
| `/` | `GET` | Health check |

**Structure de l'état de jeu retourné :**

```json
{
  "board": [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
  "scores": { "player1": 0, "player2": 0 },
  "current_player": "player1",
  "game_over": false,
  "winner": null,
  "valid_moves": [0, 1, 2, 3, 4, 5]
}
```

**Payload `/api/game/ai-move` (requête) :**

```json
{ "player": "player1", "agent": "alphabeta", "depth": 6, "board": [...] }
```

**Réponse `/api/game/ai-move` :**

```json
{
  "game_state": { "board": [...], "scores": {...}, "current_player": "player2", "game_over": false, "valid_moves": [...] },
  "telemetry":  { "computation_time": 42.1, "depth": 6, "nodes_explored": null, "win_rate": null, "pit_played": 3, "agent": "alphabeta" }
}
```

---

## Interface Web — `web/`

Interface jouable accessible dans un navigateur, sans build ni installation.  
Icônes **Font Awesome 6** (CDN). Aucune dépendance JS additionnelle.

### Configuration des joueurs

Chaque joueur est configurable indépendamment :

- **Type** : Humain ou IA
- **Nom** personnalisé
- **Modèle IA** : Aléatoire / Minimax / Alpha-Beta / Q-Learning
- **Profondeur** : select dynamique avec libellés (Facile / Moyen / Difficile / Expert / Maître) — masqué pour les agents sans profondeur

### Plateau de jeu

- Rendu des graines par case (positions calculées en cercle)
- **Cases jouables** : anneau doré, cases invalides grisées
- **Animation du semis** case par case (110 ms/étape)
- **Flash rouge** sur les cases capturées après semis
- Granaires (greniers) animés avec positions de graines en cache

### Modale de fin de partie

Apparaît automatiquement 600 ms après la dernière animation :

- **Victoire** : icône trophée doré, couronne devant le nom du vainqueur, confettis CSS
- **Match nul** : icône `handshake`, message adapté, pas de confettis
- **Scores** des deux joueurs avec encadré doré sur le gagnant
- **Bloc Performance IA** (si une IA a joué) : modèle, niveau d'analyse, dernier temps de calcul, coups évalués
- Boutons **Rejouer** (relance directement) et **Fermer** — fermable aussi via `Escape` ou clic sur l'overlay

### Notifications (toasts)

Notifications contextuelles en bas à droite, avec disparition automatique :

| Situation | Type |
| --- | --- |
| Partie démarrée | Succès (vert) |
| Serveur inaccessible | Erreur (rouge) |
| Coup refusé par l'API | Avertissement (orange) |
| Erreur IA / réseau | Erreur (rouge) |

### Panneau "Analyse du coup IA"

Remplace l'ancienne "Télémétrie" — termes compréhensibles par tous :

- **Barre de temps de réflexion** animée avec couleur adaptative (vert < 200 ms → or < 800 ms → rouge ≥ 800 ms)
- **Niveau d'analyse** : profondeur + libellé humain (ex. `6  (Difficile)`)
- **Coups évalués** : nombre formaté (`12 345`)
- **Taux de victoire** : affiché uniquement pour Q-Learning
- Message d'aide initial jusqu'au premier coup IA

### Indicateur de statut

Pastille colorée à gauche du message de statut :

| État | Couleur | Animation |
| --- | --- | --- |
| En attente | Gris | — |
| Tour joueur | Bleu | — |
| IA réfléchit | Violet | pulsation |
| Victoire | Vert | — |
| Égalité | Ambre | — |
| Erreur | Rouge | — |

### Lancement

```bash
# 1. Démarrer le backend
uvicorn api.server:app --reload --port 8000

# 2. Ouvrir dans un navigateur
open web/index.html   # ou double-cliquer sur le fichier
```

---

## Point d'entrée CLI — `main.py`

Lance un match IA vs IA en console avec choix interactif des niveaux.

```bash
python main.py
```

Fonctionnalités :
- Sélection du niveau de difficulté pour chaque joueur
- Détection de répétition de position (nulle automatique)
- Limite de 500 tours
- Affichage du vainqueur et des scores finaux

---

## Installation

```bash
pip install -r requirements.txt
```

Prérequis : **Python 3.10+**

---

## Règles implémentées

- Distribution circulaire dans le sens horaire (sens `+1 % 12`)
- La case de départ est sautée si le tour est assez long pour y revenir
- Capture si la **dernière case** atteinte contient exactement `2` ou `3` graines
- La capture remonte les cases précédentes tant que la condition est remplie
- **Règle de nourrissage** : un coup n'est valide que s'il ne laisse pas l'adversaire sans graines (sauf si aucun tel coup n'existe)
- Fin de partie par blocage ou lorsqu'un joueur dépasse 24 graines capturées
- Égalité si les deux joueurs atteignent exactement 24 graines

---

## Roadmap

| Phase | Objectif | Tâches | Statut |
| --- | --- | --- | --- |
| **Phase 1** | Moteur de jeu | Étude des règles · Modélisation du plateau · Développement du moteur · Gestion des scores | ✅ Terminé |
| **Phase 2** | IA classique + Interface | Agent aléatoire · Heuristique · Minimax · Alpha-Beta · API REST · Interface web + UX complète | ✅ Terminé |
| **Phase 3** | IA par renforcement | Étude du RL · Implémentation Q-Learning · Entraînement des agents | 🔲 À venir |
| **Phase 4** | Finalisation | Benchmark · Documentation complète · Préparation démonstration | 🔲 À venir |
