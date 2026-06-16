# AwaleAI — Phase 1

Moteur de jeu Awalé en Python, développé en architecture modulaire.
Phase 1 couvre les règles, la modélisation du plateau, le moteur de jeu et la gestion des scores.

---

## Architecture

```
AwaleAI/
├── engine/
│   ├── board.py      # Modélisation du plateau
│   ├── rules.py      # Règles et distribution des graines
│   └── game.py       # Moteur de jeu et gestion des scores
└── main.py           # Point d'entrée — boucle de jeu
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

**Méthodes statiques :**

| Méthode | Description |
|---|---|
| `is_valid_move(board, hole, player=None)` | Vérifie que la case existe, n'est pas vide, et appartient au bon joueur |
| `sow(board, hole)` | Distribue les graines dans le sens horaire, saute la case de départ, retourne l'index de la dernière case |

**Règles de validité :**
- Joueur 1 → cases `0–5` (entrée utilisateur `1–6`)
- Joueur 2 → cases `6–11` (entrée utilisateur `1–6`, converti en `+5`)

---

### `engine/game.py` — Moteur de jeu

Orchestre une partie complète.

**Attributs :**

| Attribut | Type | Description |
|---|---|---|
| `board` | `Board` | Plateau courant |
| `score_p1` | `int` | Score du joueur 1 |
| `score_p2` | `int` | Score du joueur 2 |
| `current_player` | `int` | Joueur actif (`1` ou `2`) |

**Méthodes :**

- `play_move(hole)` — valide, sème, capture, met à jour le score, change de joueur
- `capture(last_hole)` — remonte les cases depuis `last_hole`, capture tant que la case contient `2` ou `3` graines
- `display()` — affiche plateau + scores + tour courant

---

### `main.py` — Boucle de jeu

```
Entrée utilisateur : 1–6 (pour les deux joueurs)

Joueur 1 : entrée x → index  x - 1   (1 → 0, ..., 6 → 5)
Joueur 2 : entrée x → index  x + 5   (1 → 6, ..., 6 → 11)
```

---

## Lancer le jeu

```bash
python main.py
```

Prérequis : Python 3.10+, aucune dépendance externe.

---

## Règles implémentées

- Distribution circulaire dans le sens horaire
- La case de départ est sautée si le tour est assez long pour y revenir
- Capture si la dernière case contient exactement `2` ou `3` graines
- La capture remonte les cases précédentes tant que la condition est remplie
- Chaque joueur ne joue que ses propres cases

---

## Roadmap

| Phase | Objectif | Tâches | Statut |
|---|---|---|---|
| **Phase 1** | Moteur de jeu | Étude des règles · Modélisation du plateau · Développement du moteur · Gestion des scores | ✅ Terminé |
| **Phase 2** | IA classique | Stratégie aléatoire · Heuristique · Minimax · Alpha-Beta | 🔲 À venir |
| **Phase 3** | IA par renforcement | Étude du RL · Implémentation Q-Learning · Entraînement des agents | 🔲 À venir |
| **Phase 4** | Finalisation | Interface graphique · Benchmark · Préparation démonstration | 🔲 À venir |
