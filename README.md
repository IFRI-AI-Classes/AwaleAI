# AwaleAI

Moteur de jeu Awalé en Python avec architecture modulaire.  
Le projet couvre les règles complètes du jeu, quatre agents IA (Aléatoire, Minimax, Alpha-Beta, Q-Learning) et une interface web interactive connectée à une API REST FastAPI.

> Projet développé dans le cadre du **Club IA & IoT — IFRI**.

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
- [Roadmap](#roadmap)

---

## Architecture

```
AwaleAI/
├── engine/
│   ├── board.py          # Modélisation du plateau (12 cases)
│   ├── rules.py          # Règles, distribution des graines, coups valides
│   ├── game.py           # Moteur de jeu : captures, scores, fin de partie
│   └── env.py            # Environnement RL (AwaleEnv) — base Phase 3
│
├── agents/
│   ├── difficulty.py           # Routage agent/profondeur (point d'entrée unique)
│   ├── random/
│   │   └── random_agent.py     # Agent aléatoire
│   ├── heuristic/
│   │   └── heuristic.py        # Fonction d'évaluation statique
│   ├── minimax/
│   │   └── minimax.py          # Minimax avec SearchState léger
│   └── alpha_beta/
│       └── elagage.py          # Alpha-Beta négamax + évaluation avancée
│
├── awale/
│   └── ai/
│       └── qlearning.py        # Agent Q-Learning persistant + curriculum
│
├── models/
│   ├── q_table_latest.json     # Dernier checkpoint Q-Learning
│   └── q_table_best.json       # Meilleur checkpoint Q-Learning
│
├── api/
│   └── server.py               # API REST FastAPI (5 endpoints)
│
├── web/
│   ├── index.html              # Interface HTML — plateau, configuration, modale
│   ├── app.js                  # Client JS — UX complète (toasts, animations, modale)
│   └── styles.css              # Styles — pits, graines, granaires, responsive
│
├── main.py                     # Point d'entrée CLI — match IA vs IA en console
├── train_qlearning.py          # Lancement du curriculum d'entraînement
├── Les règles d'Awale.md       # Règles officielles du jeu
├── requirements.txt            # Dépendances Python
├── vercel.json                 # Configuration déploiement Vercel
└── pyproject.toml              # Entrypoint Vercel
```

---

## Installation

**Prérequis : Python 3.10+**

```bash
pip install -r requirements.txt
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
# ou ouvrir http://localhost:8000 si servi via Vercel local
```

### CLI — match IA vs IA en console

```bash
python main.py
```

Le programme propose de choisir un niveau de difficulté pour chaque joueur, puis simule la partie en console avec détection de répétition de position.

### Entraînement Q-Learning

```bash
python train_qlearning.py
```

Lance le pipeline curriculum complet (≈ 4 500 parties). Les modèles sont sauvegardés dans `models/`.

---

## Moteur de jeu

### `engine/board.py` — Plateau

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

### `engine/rules.py` — Règles

Valide les coups et distribue les graines. Toutes les méthodes sont `@staticmethod`.

| Méthode | Description |
| --- | --- |
| `is_valid_move(board, hole, player)` | Vérifie que la case existe, n'est pas vide et appartient au bon joueur |
| `sow(board, hole)` | Distribue les graines en sens `+1 % 12`, saute la case de départ si tour complet (règle Kroo), retourne le dernier index |
| `get_valid_moves(board, player)` | Retourne les coups légaux — applique la règle de nourrissage par simulation |

**Convention d'index :** le semis incrémente l'index modulo 12 (sens anti-horaire dans la vue plateau : bas de gauche à droite, puis haut de droite à gauche).

---

### `engine/game.py` — Moteur

Orchestre une partie complète.

| Attribut | Type | Description |
| --- | --- | --- |
| `board` | `Board` | Plateau courant |
| `score_p1` | `int` | Graines capturées par le joueur 1 |
| `score_p2` | `int` | Graines capturées par le joueur 2 |
| `current_player` | `int` | Joueur actif (`1` ou `2`) |

| Méthode | Description |
| --- | --- |
| `play_move(hole)` | Valide, sème, capture, met à jour le score, change de joueur |
| `capture(last_hole)` | Remonte depuis `last_hole`, capture tant que la case contient 2 ou 3 graines dans le camp adverse |
| `is_game_over()` | `True` si un joueur a ≥ 25 graines ou si le joueur courant n'a plus de coup valide |
| `get_winner()` | Retourne `1`, `2` ou `None` (égalité) — **idempotent, ne modifie pas l'état** |
| `get_children()` | Génère tous les états enfants pour les agents de recherche |
| `display()` | Affiche le plateau et les scores en console |

---

### `engine/env.py` — Environnement RL

Couche d'abstraction autour de `Game` pour les agents d'apprentissage par renforcement.

| Méthode | Description |
| --- | --- |
| `reset()` | Démarre une nouvelle partie, retourne l'état initial sous forme de liste |
| `state()` | Retourne le plateau courant sous forme de liste |

---

## Agents IA

### `agents/difficulty.py` — Routage

Module centralisé exposant deux points d'entrée :

```python
# Entrée CLI — niveau prédéfini
choose_move(game, level: str) -> int

# Entrée Web UI — agent + profondeur libres
choose_move_by_agent(game, agent: str, depth: int | None) -> tuple[int, int | None]
```

**Niveaux prédéfinis (CLI) :**

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

L'agent Q-Learning est chargé paresseusement (`_get_qlearning_agent()`) : la Q-Table est lue depuis `models/q_table_latest.json` uniquement à la première utilisation.

---

### `agents/random/random_agent.py`

```python
random_move(game) -> int
```

Choisit uniformément un coup valide parmi les coups légaux du joueur courant.

---

### `agents/heuristic/heuristic.py`

Fonction d'évaluation statique utilisée par Minimax. Toutes les méthodes sont `@staticmethod`.

```python
heuristic.evaluate(game, player) -> float
```

| Composante | Poids | Description |
| --- | --- | --- |
| Différence de captures | `1.0` | `score_joueur − score_adversaire` |
| Mobilité | `3.0` | Coups valides joueur − coups valides adversaire |
| Graines dans le camp adverse | `0.1` | Pression offensive |

---

### `agents/minimax/minimax.py`

Algorithme Minimax pur avec profondeur configurable.

```python
Minimax(depth=2).choose_move(board, player, score1=0, score2=0) -> tuple[int, int]
# Retourne : (case jouée, nombre de nœuds explorés)
```

- Utilise `SearchState` (structure légère) pour simuler les coups sans copier l'objet `Game`
- Reçoit les **vrais scores courants** (`score1`, `score2`) pour une évaluation correcte
- Bris d'égalité aléatoire via `_shuffled_moves()`
- Évaluation terminale via `heuristic.evaluate()`

---

### `agents/alpha_beta/elagage.py`

Alpha-Beta avec négamax et élagage α-β.

```python
best_move(game, depth=5) -> tuple[int, int]
# Retourne : (case jouée, nombre de nœuds explorés)
```

**Fonction d'évaluation propre (`evaluate`) :**

| Composante | Poids | Description |
| --- | --- | --- |
| Différence de captures | `100` | Priorité maximale |
| Opportunités de capture | `10` | Cases adverses contenant 1 ou 2 graines (menaces) |
| Mobilité | `5` | Coups valides joueur − adversaire |
| Contrôle du plateau | `0.5` | Total des graines dans son propre camp |

Détecte les fins de partie immédiates (victoire `+999999` / défaite `-999999` / égalité `0`) et court-circuite la recherche dès qu'une victoire est trouvée.

---

### `awale/ai/qlearning.py`

Agent Q-Learning tabulaire avec encodage symétrique et curriculum d'entraînement progressif.

```python
QLearningAgent().choose_move(game, greedy=True) -> int
```

**Encodage de l'état :**

```
"mes_trous|trous_adversaire|score_moi|score_lui"
```

Grâce à cette symétrie, la même Q-Table fonctionne pour les deux joueurs. Les actions sont encodées en indices relatifs (0–5) plutôt qu'absolus (0–11).

**Hyperparamètres :**

| Paramètre | Valeur | Description |
| --- | --- | --- |
| `ALPHA` | 0.15 | Taux d'apprentissage |
| `GAMMA` | 0.95 | Facteur d'actualisation |
| `EPSILON_START` | 1.00 | Taux d'exploration initial |
| `EPSILON_MIN` | 0.05 | Taux d'exploration plancher |

**Récompenses :**

| Événement | Récompense |
| --- | --- |
| Victoire | +100 |
| Défaite | −100 |
| Égalité | 0 |
| Capture | +2 par graine |
| Capture adverse | −2 par graine |
| Pénalité temporelle | −0.5 par tour |

**Curriculum d'entraînement (`run_curriculum`) :**

| Phase | Adversaire | Parties |
| --- | --- | --- |
| 1 | Agent aléatoire | 1 000 |
| 2.1 – 2.5 | Alpha-Beta profondeur 1 à 5 | 500 × 5 |
| 3 | Self-play | 1 000 |

Un checkpoint "champion" est sauvegardé après chaque phase si le taux de victoire s'améliore.

---

## API REST

Backend FastAPI exposant cinq endpoints.

**Lancement :**

```bash
uvicorn api.server:app --reload --port 8000
```

| Endpoint | Méthode | Description |
| --- | --- | --- |
| `/api/game/start` | `POST` | Démarre une partie, retourne l'état initial |
| `/api/game/move` | `POST` | Applique un coup humain, retourne le nouvel état |
| `/api/game/ai-move` | `POST` | Fait jouer l'IA (agent + profondeur libres), retourne état + télémétrie |
| `/api/agents` | `GET` | Liste les agents disponibles et leurs profondeurs valides |
| `/` | `GET` | Health check |

**État de jeu retourné (tous les endpoints sauf `/api/agents`) :**

```json
{
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
{ "pit_index": 3, "player": "player1" }
```

**Payload `POST /api/game/ai-move` :**

```json
{ "player": "player1", "agent": "alphabeta", "depth": 6, "board": [...] }
```

**Réponse `POST /api/game/ai-move` :**

```json
{
  "game_state": { "board": [...], "scores": {...}, "current_player": "player2", "game_over": false, "valid_moves": [...] },
  "telemetry":  { "computation_time": 42.1, "depth": 6, "nodes_explored": 8312, "win_rate": null, "pit_played": 3, "agent": "alphabeta" }
}
```

> **Note :** La session de jeu est stockée en mémoire côté serveur (`_game`). Un seul jeu actif à la fois par instance du serveur.

---

## Interface Web

Interface jouable dans un navigateur, **sans build ni installation**.  
Icônes **Font Awesome 6** (CDN). Aucune dépendance JS additionnelle.

L'URL de l'API est détectée automatiquement :
- `localhost` → `http://localhost:8000`
- Production → `https://awale-ai-backend.onrender.com`

### Configuration des joueurs

Chaque joueur est configurable indépendamment avant le lancement d'une partie :

| Paramètre | Valeurs |
| --- | --- |
| **Type** | Humain / IA |
| **Nom** | Texte libre |
| **Modèle IA** | Aléatoire / Minimax / Alpha-Beta / Q-Learning |
| **Profondeur** | Select dynamique avec libellés (Facile → Maître) — masqué pour les agents sans profondeur |

Libellés de profondeur :

| Plage (Alpha-Beta) | Libellé |
| --- | --- |
| 1 – 2 | Facile |
| 3 – 4 | Moyen |
| 5 – 6 | Difficile |
| 7 – 9 | Expert |
| 10 – 12 | Maître |

### Plateau de jeu

- Rendu des graines par case (positions calculées en cercle, mises en cache dans `_granaryCache`)
- **Cases jouables** : anneau doré (`pit--playable`), cases invalides grisées (`pit--disabled`)
- **Animation du semis** case par case à 110 ms/étape (`animateSow`)
- **Flash rouge** (`pit--captured`) sur les cases capturées après semis
- **Granaires** animés avec graines positionnées aléatoirement en cache
- **Indicateur de joueur actif** : bordure dorée sur la score-box du joueur courant

### Boutons

| Bouton | Comportement |
| --- | --- |
| **Nouvelle partie** | Appelle `POST /api/game/start`, lance l'IA si les deux joueurs sont IA |
| **Arrêter la partie** | Réinitialise le plateau côté client sans appel API, reste actif même pendant les coups IA |

### Modale de fin de partie

Apparaît automatiquement 600 ms après la dernière animation :

- **Victoire** : icône trophée doré, couronne devant le nom du vainqueur, confettis CSS
- **Match nul** : icône `handshake`, message adapté, pas de confettis
- **Scores** des deux joueurs avec encadré doré sur le gagnant
- **Bloc Performance IA** (si une IA a joué) : modèle, niveau d'analyse, meilleur temps, temps moyen, coup le plus rapide, coups évalués
- Boutons **Rejouer** et **Fermer** — fermable aussi via `Escape` ou clic sur l'overlay

### Notifications (toasts)

Notifications contextuelles en bas à droite, disparition automatique :

| Situation | Type |
| --- | --- |
| Partie démarrée | Succès (vert) |
| Serveur inaccessible | Erreur (rouge) |
| Partie arrêtée | Avertissement (orange) |
| Coup refusé par l'API | Avertissement (orange) |
| Erreur IA / réseau | Erreur (rouge) |

### Panneau « Analyse du coup IA »

- **Barre de temps de réflexion** animée avec couleur adaptative :
  - vert < 200 ms
  - or < 800 ms
  - rouge ≥ 800 ms
- **Niveau d'analyse** : profondeur + libellé humain (ex. `6 — Difficile`)
- **Coups évalués** : nombre formaté avec séparateurs (`12 345`)
- **Taux de victoire** : affiché uniquement pour Q-Learning si disponible
- Message d'aide initial jusqu'au premier coup IA

### Panneau Statut

Pastille colorée avec indicateur d'état :

| État | Couleur | Animation |
| --- | --- | --- |
| En attente | Gris | — |
| Tour joueur | Bleu | — |
| IA réfléchit | Violet | pulsation |
| Victoire | Vert | — |
| Égalité | Ambre | — |
| Erreur | Rouge | — |

### Historique des coups

Liste scrollable des coups joués avec : numéro de tour, joueur (badge J1/J2), case jouée, graines capturées.

---

## Entraînement Q-Learning

```bash
python train_qlearning.py
```

Le script lance `run_curriculum(agent)` qui enchaîne les phases suivantes :

```
Phase 1 — vs Random        : 1 000 parties
Phase 2.1 — vs AB depth=1  :   500 parties
Phase 2.2 — vs AB depth=2  :   500 parties
Phase 2.3 — vs AB depth=3  :   500 parties
Phase 2.4 — vs AB depth=4  :   500 parties
Phase 2.5 — vs AB depth=5  :   500 parties
Phase 3 — Self-Play        : 1 000 parties
```

À chaque changement de phase, epsilon remonte de `+0.15` (relance l'exploration).  
Après chaque phase, une évaluation "Champion" sur 100 parties décide si `q_table_best.json` est mis à jour.

**Fichiers produits :**

| Fichier | Contenu |
| --- | --- |
| `models/q_table_latest.json` | Dernier état de la Q-Table |
| `models/q_table_best.json` | Meilleur taux de victoire obtenu |

---

## Règles implémentées

- Distribution circulaire en sens `+1 % 12` (anti-horaire sur le plateau physique)
- La case de départ est sautée si le nombre de graines est > 11 (**règle Kroo**)
- **Capture** : si la dernière case atteinte contient exactement 2 ou 3 graines dans le camp adverse, ces graines sont capturées ; la capture remonte les cases précédentes tant que la condition est remplie
- **Règle de nourrissage** : un coup n'est valide que s'il ne laisse pas l'adversaire sans graines, sauf si aucun tel coup n'existe
- **Fin de partie** : lorsqu'un joueur dépasse 24 graines capturées, ou lorsque le joueur courant n'a plus de coup valide
- En cas de blocage, les graines restantes sur le plateau sont attribuées à l'adversaire du joueur bloqué
- **Égalité** si les deux joueurs finissent avec exactement 24 graines

---

## Roadmap

| Phase | Objectif | Statut |
| --- | --- | --- |
| **Phase 1** | Moteur de jeu : plateau, règles, captures, scores | ✅ Terminé |
| **Phase 2** | IA classique + Interface : Aléatoire, Heuristique, Minimax, Alpha-Beta, API REST, Web UI | ✅ Terminé |
| **Phase 3** | IA par renforcement : Q-Learning tabulaire + curriculum | ✅ Terminé |
| **Phase 4** | Finalisation : tests automatisés, benchmark inter-agents, documentation complète, démo | 🔲 À venir |
