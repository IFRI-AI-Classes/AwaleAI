// Awalé AI Frontend, JavaScript Module
// Toute la logique de jeu est côté serveur Python (FastAPI).
// Ce fichier gère : UI, appels REST, animations, UX.

// Métadonnées des agents : profondeurs supportées par agent
// (doit correspondre à agents/difficulty.AGENTS côté Python)
const AGENT_DEPTHS = {
    random:    null,               // pas de profondeur
    minimax:   [1,2,3,4,5,6,7,8],
    alphabeta: [1,2,3,4,5,6,7,8,9,10,11,12],
    qlearning: null,
};

// Libellés affichés dans le label du joueur
const AGENT_LABELS = {
    random:    'Aléatoire',
    minimax:   'Minimax',
    alphabeta: 'Alpha-Bêta',
    qlearning: 'Q-Learning',
};

// Profondeur par défaut selon l'agent
const AGENT_DEFAULT_DEPTH = {
    minimax:   5,
    alphabeta: 6,
};

const AGENT_HELP = {
    random: 'Choisit un coup au hasard. Pour découvrir les règles sans forte opposition.',
    minimax: 'Explore les possibilités de jeu sur plusieurs niveaux pour choisir le coup offrant le meilleur résultat.',
    alphabeta: "Utilise l'élagage Alpha-Bêta pour réduire les recherches inutiles et accélérer la prise de décision.",
    qlearning: 'Agent expérimental entraîné par essais. Son niveau de jeu reste variable.',
};

const END_REASONS = {
    score: 'Le seuil de 25 graines capturées a été atteint.',
    blocage: 'Aucun coup légal : les graines restantes reviennent à l’adversaire du joueur qui ne peut plus jouer.',
    repetition: 'La position se répète : la partie est déclarée nulle, même si les scores diffèrent.',
    limite: 'La limite de coups a été atteinte : la partie est déclarée nulle.',
};

// Coordonnées relatives, pour conserver le rangement après redimensionnement.
const SEED_LAYOUTS = new Map();
function seedLayout(count) {
    if (SEED_LAYOUTS.has(count)) return SEED_LAYOUTS.get(count);
    let positions = [];
    if (count === 1) {
        positions = [{x: 50, y: 50, size: 16}];
    } else if (count > 1 && count <= 6) {
        positions = Array.from({length: count}, (_, i) => {
            const angle = -Math.PI / 2 + i * 2 * Math.PI / count;
            return {x: 50 + 26 * Math.cos(angle), y: 50 + 26 * Math.sin(angle), size: 16};
        });
    } else if (count > 6) {
        // Maille hexagonale : distances constantes et paires symétriques.
        const extent = Math.ceil(Math.sqrt(count)) + 1;
        const pairs = [];
        for (let row = 0; row <= extent; row++) {
            for (let column = -extent; column <= extent; column++) {
                const x = column + row / 2;
                const y = row * Math.sqrt(3) / 2;
                if (y === 0 && x <= 0) continue;
                pairs.push({x, y, radius: Math.hypot(x, y)});
            }
        }
        pairs.sort((a, b) => a.radius - b.radius || Math.atan2(a.y, a.x) - Math.atan2(b.y, b.x));
        const points = count % 2 ? [{x: 0, y: 0}] : [];
        for (const {x, y} of pairs.slice(0, Math.floor(count / 2))) {
            points.push({x, y}, {x: -x, y: -y});
        }
        const radius = Math.max(...points.map(p => Math.hypot(p.x, p.y)));
        const spacing = 90 / (2 * radius + 1);
        const size = Math.min(16, spacing * 0.76);
        positions = points.map(p => ({x: 50 + p.x * spacing, y: 50 + p.y * spacing, size}));
    }
    SEED_LAYOUTS.set(count, positions);
    return positions;
}

class AwaleGame {
    constructor() {
        this.apiBaseUrl = ['localhost', '127.0.0.1', ''].includes(window.location.hostname)
            ? 'http://localhost:8000'
            : 'https://awale-ai-backend.onrender.com';
        this.gameState = null;
        this._busy = false;           // verrou global, empêche les actions simultanées
        this._generation = 0;
        this._abortController = new AbortController();
        this._granaryCache = [];      // cache des positions fixes de graines dans granaires
        this._turnCount = 0;          // compteur de tours pour l'historique

        this.players = {
            player1: { name: 'Joueur 1', type: 'human', agent: 'alphabeta', depth: 6 },
            player2: { name: 'Joueur 2', type: 'human', agent: 'alphabeta', depth: 6 }
        };

        this.initializeUI();
        this.attachEventListeners();
    }

    // ─── Initialisation ──────────────────────────────────────────────────────

    initializeUI() {
        this.pits               = document.querySelectorAll('.pit');
        this.scorePlayer1       = document.getElementById('score-player1');
        this.scorePlayer2       = document.getElementById('score-player2');
        this.labelPlayer1       = document.getElementById('label-player1');
        this.labelPlayer2       = document.getElementById('label-player2');
        this.gameStatus         = document.getElementById('game-status');
        this.statusDot          = document.getElementById('status-dot');
        this.moveHistoryContainer = document.getElementById('move-history');
        this.telemetryTime      = document.getElementById('telemetry-time');
        this.telemetryDepth     = document.getElementById('telemetry-depth');
        this.telemetryNodes     = document.getElementById('telemetry-nodes');
        this.telemetryWinrate   = document.getElementById('telemetry-winrate');
        this.atbFill            = document.getElementById('atb-fill');
        this.analysisEmpty      = document.getElementById('analysis-empty');
        this.granarySeedsPlayer1 = document.getElementById('granary-seeds-player1');
        this.granarySeedsPlayer2 = document.getElementById('granary-seeds-player2');
        this.btnNewGame         = document.getElementById('btn-new-game');
        this.btnStop            = document.getElementById('btn-stop');
        this.boardGuide         = document.getElementById('board-guide');
        this.setupNote          = document.getElementById('setup-note');
        this.setupInputs        = document.querySelectorAll('.player-setup input, .player-setup select');

        // Modale
        this.modalEnd           = document.getElementById('modal-end');
        this.modalTitle         = document.getElementById('modal-title');
        this.modalWinner        = document.getElementById('modal-winner');
        this.modalIcon          = document.getElementById('modal-icon');
        this.modalSnameP1       = document.getElementById('modal-sname-p1');
        this.modalSnameP2       = document.getElementById('modal-sname-p2');
        this.modalSnumP1        = document.getElementById('modal-snum-p1');
        this.modalSnumP2        = document.getElementById('modal-snum-p2');
        this.modalScoreP1       = document.getElementById('modal-score-p1');
        this.modalScoreP2       = document.getElementById('modal-score-p2');
        this.toastZone          = document.getElementById('toast-zone');

        // Boutons modale
        document.getElementById('modal-btn-replay').addEventListener('click', () => {
            this._closeModal();
            this.startGame();
        });
        document.getElementById('modal-btn-close').addEventListener('click', () => {
            this._closeModal();
        });
        // Fermer en cliquant sur l'overlay
        this.modalEnd.addEventListener('click', (e) => {
            if (e.target === this.modalEnd) this._closeModal();
        });

        // Raccourci clavier Escape
        document.addEventListener('keydown', (e) => this._handleModalKeydown(e));

        // Dernière décision affichée dans le panneau d'analyse
        this._lastTelemetry = null;

        // Initialise les selects de profondeur
        this._refreshDepthSelect('player1');
        this._refreshDepthSelect('player2');

        this.updatePlayerLabels();
        this.renderInitialBoard();
        this.setStatus('En attente du lancement d’une partie', 'idle');
        this._refreshInteraction();
    }

    attachEventListeners() {
        this.btnNewGame.addEventListener('click', () => this.startGame());
        this.btnStop.addEventListener('click',    () => this.resetGame());

        // Clic sur une case
        this.pits.forEach(pit => {
            pit.setAttribute('role', 'button');
            pit.setAttribute('aria-describedby', 'board-guide');
            pit.addEventListener('click', () => {
                const pitIndex = parseInt(pit.dataset.index);
                this.sendMove(pitIndex);
            });
            pit.addEventListener('keydown', (event) => {
                if (pit.getAttribute('aria-disabled') === 'true' || this._busy) return;
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    if (!event.repeat) this.sendMove(Number(pit.dataset.index));
                } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                    event.preventDefault();
                    const playable = [...this.pits].filter(p => p.getAttribute('aria-disabled') === 'false');
                    const step = event.key === 'ArrowRight' ? 1 : -1;
                    const next = (playable.indexOf(pit) + step + playable.length) % playable.length;
                    playable[next]?.focus();
                }
            });
        });

        // Changement de type de joueur
        document.getElementById('player1-type').addEventListener('change', (e) => {
            this.handlePlayerTypeChange('player1', e.target.value);
        });
        document.getElementById('player2-type').addEventListener('change', (e) => {
            this.handlePlayerTypeChange('player2', e.target.value);
        });

        // Changement de nom
        document.getElementById('player1-name').addEventListener('input', (e) => {
            this.players.player1.name = e.target.value || 'Joueur 1';
            this.updatePlayerLabels();
        });
        document.getElementById('player2-name').addEventListener('input', (e) => {
            this.players.player2.name = e.target.value || 'Joueur 2';
            this.updatePlayerLabels();
        });

        // Changement de modèle IA
        document.getElementById('player1-agent').addEventListener('change', (e) => {
            this.players.player1.agent = e.target.value;
            this._refreshDepthSelect('player1');
            this.updatePlayerLabels();
        });
        document.getElementById('player2-agent').addEventListener('change', (e) => {
            this.players.player2.agent = e.target.value;
            this._refreshDepthSelect('player2');
            this.updatePlayerLabels();
        });

        // Changement de profondeur
        document.getElementById('player1-depth').addEventListener('change', (e) => {
            this.players.player1.depth = e.target.value ? parseInt(e.target.value) : null;
            this.updatePlayerLabels();
        });
        document.getElementById('player2-depth').addEventListener('change', (e) => {
            this.players.player2.depth = e.target.value ? parseInt(e.target.value) : null;
            this.updatePlayerLabels();
        });
    }

    // ─── Gestion des joueurs ─────────────────────────────────────────────────

    handlePlayerTypeChange(playerKey, type) {
        const aiConfig = document.getElementById(`${playerKey}-ai-config`);
        this.players[playerKey].type = type;

        if (type === 'ai') {
            aiConfig.style.display = 'flex';
            aiConfig.style.flexDirection = 'column';
        } else {
            aiConfig.style.display = 'none';
        }

        this.updatePlayerLabels();
    }

    updatePlayerLabels() {
        const getDisplayName = (player) => {
            if (player.type === 'ai') {
                const label = AGENT_LABELS[player.agent] || player.agent;
                // N'afficher la profondeur que si l'agent la supporte (depths non null)
                const agentHasDepth = AGENT_DEPTHS[player.agent] != null;
                const depthStr = (agentHasDepth && player.depth != null) ? ` (niveau ${player.depth})` : '';
                return `${label}${depthStr}`;
            }
            return player.name;
        };

        this.labelPlayer1.textContent = getDisplayName(this.players.player1);
        this.labelPlayer2.textContent = getDisplayName(this.players.player2);
    }

    _syncSetup() {
        const locked = this._busy || !!(this.gameState && !this.gameState.game_over);
        this.setupInputs?.forEach(input => { input.disabled = locked; });
        if (this.setupNote) this.setupNote.textContent = locked
            ? 'Réglages fixés pour cette partie. Abandonnez-la pour changer les joueurs ou les agents IA.'
            : 'Le Joueur 1 commence sur la rangée inférieure. Les agents IA jouent automatiquement.';
        if (this.btnNewGame && !this.btnNewGame.disabled) {
            const active = this.gameState && !this.gameState.game_over;
            this.btnNewGame.innerHTML = active
                ? '<i class="fa-solid fa-rotate-right"></i> Recommencer'
                : '<i class="fa-solid fa-play"></i> Nouvelle partie';
        }
    }

    _refreshInteraction() {
        const gs = this.gameState;
        const humanTurn = gs && !gs.game_over && this.players[gs.current_player].type === 'human';
        const valid = humanTurn && !this._busy ? gs.valid_moves : [];
        const focusedPit = [...this.pits].includes(document.activeElement) ? document.activeElement : null;
        this.pits.forEach(pit => {
            const index = Number(pit.dataset.index);
            const playable = valid.includes(index);
            pit.tabIndex = playable ? 0 : -1;
            pit.setAttribute('aria-disabled', String(!playable));
            const count = Number(pit.querySelector('.seeds').dataset.count || 0);
            const location = index < 6 ? `Joueur 1, rangée inférieure, case ${index + 1}` : `Joueur 2, rangée supérieure, case ${index - 5}`;
            const label = `${location} : ${count} graine${count === 1 ? '' : 's'}${playable ? ', jouable' : ', indisponible'}`;
            pit.setAttribute('aria-label', label);
            pit.title = label;
        });
        // Conserve le parcours clavier lorsqu'un coup rend la case focalisée indisponible.
        if (focusedPit && !this._busy && focusedPit.tabIndex < 0 && valid.length) {
            [...this.pits].find(p => p.tabIndex === 0)?.focus();
        }
        if (this.boardGuide) {
            if (!gs) {
                this.boardGuide.textContent = this._busy
                    ? 'Préparation de la partie…'
                    : 'Choisissez vos joueurs, puis lancez une nouvelle partie.';
            } else if (gs.game_over) {
                this.boardGuide.textContent = END_REASONS[gs.end_reason] || 'Partie terminée. Vous pouvez rejouer.';
            } else if (this._statusState === 'error') {
                this.boardGuide.textContent = `${this.gameStatus.textContent}. Vous pouvez abandonner la partie, puis en lancer une nouvelle.`;
            } else if (this._busy) {
                this.boardGuide.textContent = humanTurn ? 'Coup en cours…' : 'L’agent IA calcule son coup et joue automatiquement…';
            } else {
                const row = gs.current_player === 'player1' ? 'inférieure' : 'supérieure';
                const player = this.players[gs.current_player];
                this.boardGuide.textContent = humanTurn
                    ? `${player.name} · rangée ${row} : sélectionnez une case surlignée en doré. Les nombres indiquent les graines.`
                    : `${player.name} · rangée ${row} : l’agent IA joue automatiquement.`;
            }
        }
    }

    /**
     * Reconstruit le <select> de profondeur selon l'agent sélectionné.
     * Masque la ligne si l'agent n'utilise pas de profondeur (random, qlearning).
     */
    _refreshDepthSelect(playerKey) {
        const agentSelect = document.getElementById(`${playerKey}-agent`);
        const depthSelect = document.getElementById(`${playerKey}-depth`);
        const depthRow    = document.getElementById(`${playerKey}-depth-row`);
        const agent       = agentSelect ? agentSelect.value : this.players[playerKey].agent;
        const depths      = AGENT_DEPTHS[agent];
        const help = document.getElementById(`${playerKey}-agent-help`);
        if (help) help.textContent = AGENT_HELP[agent] || '';

        if (!depths) {
            // Pas de profondeur pour cet agent
            depthRow.style.display    = 'none';
            this.players[playerKey].depth = null;
            return;
        }

        depthRow.style.display = '';
        const defaultDepth = AGENT_DEFAULT_DEPTH[agent] ?? depths[Math.floor(depths.length / 2)];
        const previousDepth = Number(depthSelect.value);
        const selectedDepth = depthSelect.dataset.agent === agent && depths.includes(previousDepth)
            ? previousDepth : defaultDepth;
        depthSelect.dataset.agent = agent;

        depthSelect.innerHTML = [...depths].reverse().map(d => {
            const label = this._depthLabel(d, agent);
            const sel = d === selectedDepth ? ' selected' : '';
            return `<option value="${d}"${sel}>${label}</option>`;
        }).join('');

        this.players[playerKey].depth = selectedDepth;
    }

    /**
     * Retourne un libellé humain pour une profondeur donnée.
     * La profondeur compte des demi-coups, pas une difficulté mesurée.
     */
    _depthLabel(depth, agent) {
        return `Niveau ${depth}`;
    }

    // ─── Rendu du plateau ─────────────────────────────────────────────────────

    renderInitialBoard() {
        this.pits.forEach((pit) => {
            this._renderSeeds(pit, 4);
        });
        this._renderGranarySeeds(this.granarySeedsPlayer1, 0);
        this._renderGranarySeeds(this.granarySeedsPlayer2, 0);
    }

    /**
     * Rend les graines d'une case, ne recrée le DOM que si le count change.
     */
    _renderSeeds(pitElement, seedCount) {
        const seedsContainer = pitElement.querySelector('.seeds');
        const prev = parseInt(seedsContainer.dataset.count ?? '-1');
        if (prev === seedCount) return;   // rien à faire

        seedsContainer.innerHTML = '';
        seedsContainer.dataset.count = seedCount;
        let counter = pitElement.querySelector('.pit-count');
        if (!counter) {
            counter = document.createElement('span');
            counter.className = 'pit-count';
            counter.setAttribute('aria-hidden', 'true');
            pitElement.appendChild(counter);
        }
        counter.textContent = seedCount;

        if (seedCount === 0) return;

        for (const position of seedLayout(seedCount)) {
            const seed = document.createElement('div');
            seed.className = 'seed';
            seed.style.left = `${position.x}%`;
            seed.style.top = `${position.y}%`;
            seed.style.width = `${position.size}%`;
            seed.style.height = `${position.size}%`;
            seedsContainer.appendChild(seed);
        }
    }

    /**
     * Rend les graines dans une granaire.
     * Les positions sont mises en cache par (elementId, seedCount) pour éviter
     * de recalculer Math.random() à chaque coup.
     */
    _renderGranarySeeds(granaryElement, seedCount) {
        // La clé de cache inclut l'id de l'élément pour que les deux granaires
        // (player1 et player2) aient des positions de graines indépendantes,
        // même quand leurs scores sont identiques.
        const cacheKey = `${granaryElement.id}_${seedCount}`;

        // Guard anti-redraw : on compare aussi l'id pour éviter que le même
        // cacheKey ne soit utilisé par les deux éléments lors du premier rendu.
        if (granaryElement.dataset.cacheKey === cacheKey) return;

        granaryElement.innerHTML = '';
        granaryElement.dataset.cacheKey = cacheKey;

        if (seedCount === 0) return;

        // Utilise le cache ou calcule et stocke des positions aléatoires fixes
        if (!this._granaryCache[cacheKey]) {
            const displayCount = Math.min(seedCount, 50);
            const positions = [];
            for (let i = 0; i < displayCount; i++) {
                positions.push({
                    x: Math.random() * 80 + 5,   // pourcentage relatif, granaire ~50px wide
                    y: Math.random() * 85 + 5
                });
            }
            this._granaryCache[cacheKey] = positions;
        }

        for (const pos of this._granaryCache[cacheKey]) {
            const seed = document.createElement('div');
            seed.className = 'granary-seed';
            seed.style.left = `${pos.x}%`;
            seed.style.top  = `${pos.y}%`;
            granaryElement.appendChild(seed);
        }
    }

    updateScores(score1, score2) {
        this.scorePlayer1.textContent = score1;
        this.scorePlayer2.textContent = score2;
        this._renderGranarySeeds(this.granarySeedsPlayer1, score1);
        this._renderGranarySeeds(this.granarySeedsPlayer2, score2);
    }

    /**
     * Met à jour le statut avec une couleur d'état.
     * state: 'idle' | 'playing' | 'ai' | 'win' | 'draw' | 'error'
     */
    setStatus(message, state = 'idle') {
        this._statusState = state;
        this.gameStatus.textContent = message;
        const dot = this.statusDot;
        dot.className = 'status-dot ' + state;
        this._refreshInteraction();
    }

    // Compat alias, appelé par plusieurs endroits
    updateStatus(message) {
        this.setStatus(message, 'playing');
    }

    /**
     * Affiche un toast de notification.
     * type: 'error' | 'warning' | 'info' | 'success'
     */
    showToast(message, type = 'info', durationMs = 4000) {
        const icons = {
            error:   'fa-solid fa-circle-exclamation',
            warning: 'fa-solid fa-triangle-exclamation',
            info:    'fa-solid fa-circle-info',
            success: 'fa-solid fa-circle-check',
        };
        const t = document.createElement('div');
        t.className = `toast toast-${type}`;
        t.innerHTML = `<i class="${icons[type] || icons.info}" aria-hidden="true"></i><span></span>`;
        t.querySelector('span').textContent = message;
        // Évite que les notifications empilées masquent le plateau sur mobile.
        while (this.toastZone.children.length >= 2) this.toastZone.firstElementChild.remove();
        this.toastZone.appendChild(t);

        setTimeout(() => {
            t.classList.add('toast-out');
            t.addEventListener('animationend', () => t.remove(), { once: true });
        }, durationMs);
    }

    /**
     * Met à jour le panneau "Analyse de la décision de l’IA".
     * Remplace l'ancienne updateTelemetry().
     */
    updateTelemetry(telemetry) {
        if (!telemetry) return;

        this._lastTelemetry = telemetry;

        const ms = telemetry.computation_time;

        const agent       = telemetry.agent || '';
        const isRandom    = agent === 'random';
        const isQLearning = agent === 'qlearning';

        // Cache le message "aucune IA"
        if (this.analysisEmpty) this.analysisEmpty.style.display = 'none';

        // ── Barre de temps ──────────────────────────────────
        this.telemetryTime.textContent = ms != null ? `${ms} ms` : 'Non disponible';

        if (ms != null) {
            // Plafond visuel à 3000 ms pour que la barre reste lisible
            const pct = Math.min((ms / 3000) * 100, 100);
            // Reset d'abord à 0 pour déclencher la transition
            this.atbFill.style.width = '0%';
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    this.atbFill.style.width = `${pct}%`;
                });
            });

            // Couleur selon la vitesse
            if (ms < 200)       this.atbFill.style.background = 'linear-gradient(90deg, #22c55e, #86efac)';
            else if (ms < 800)  this.atbFill.style.background = 'linear-gradient(90deg, var(--wood-medium), var(--accent-gold))';
            else                this.atbFill.style.background = 'linear-gradient(90deg, #ef4444, #f97316)';
        }

        // ── Niveau d'analyse (profondeur) ───────────────────
        const rowDepth = this.telemetryDepth.closest('.telemetry-item');
        if (isRandom || isQLearning) {
            rowDepth.style.display = 'none';
        } else {
            rowDepth.style.display = '';
            const d = telemetry.depth;
            this.telemetryDepth.textContent = d != null ? this._depthLabel(d, agent) : 'Non disponible';
        }

        // ── Coups évalués (nodes) ────────────────────────────
        const rowNodes = this.telemetryNodes.closest('.telemetry-item');
        if (telemetry.nodes_explored != null) {
            rowNodes.style.display = '';
            this.telemetryNodes.textContent = telemetry.nodes_explored.toLocaleString('fr-FR');
        } else {
            rowNodes.style.display = 'none';
        }

        // ── Taux de victoire (Q-Learning) ────────────────────
        const rowWinrate = this.telemetryWinrate.closest('.telemetry-item');
        if (telemetry.win_rate != null) {
            rowWinrate.style.display = '';
            this.telemetryWinrate.textContent = `${(telemetry.win_rate * 100).toFixed(1)} %`;
        } else {
            rowWinrate.style.display = 'none';
        }
    }

    /**
     * Ajoute un coup dans l'historique.
     * Affiche : joueur | rangée + numéro | captures éventuelles
     */
    addToHistory(playerName, pitIndex, captured, playerKey) {
        this._turnCount++;
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';

        // Label de rangée : J1 cases 0–5 → "Bas C1–C6", J2 cases 6–11 → "Haut C1–C6"
        const row   = pitIndex < 6 ? 'Rangée inférieure' : 'Rangée supérieure';
        const caseN = pitIndex < 6 ? pitIndex + 1 : pitIndex - 5;
        const badgeClass = playerKey === 'player1' ? 'badge-p1' : 'badge-p2';

        historyItem.innerHTML = `
            <span class="history-turn">#${this._turnCount}</span>
            <span class="history-player ${badgeClass}"></span>
            <span class="history-move">${row}, case ${caseN}</span>
            ${captured > 0 ? `<span class="history-capture">+${captured}</span>` : ''}
        `;
        historyItem.querySelector('.history-player').textContent = playerName;

        const emptyMessage = this.moveHistoryContainer.querySelector('.empty-history');
        if (emptyMessage) emptyMessage.remove();

        this.moveHistoryContainer.prepend(historyItem);   // derniers coups en haut
    }

    clearHistory() {
        this.moveHistoryContainer.innerHTML = '<p class="empty-history">Aucun coup pour le moment</p>';
    }

    // ─── Surbrillance des cases valides ──────────────────────────────────────

    /**
     * Applique .pit--playable sur les cases jouables, grise les autres.
     * Efface tout si validMoves est null/vide (fin de partie, tour IA…).
     */
    _highlightValidMoves(validMoves) {
        this.pits.forEach(pit => {
            const idx = parseInt(pit.dataset.index);
            pit.classList.remove('pit--playable', 'pit--disabled');
            // Si la liste est vide ou absente, toutes les cases restent neutres
            if (!validMoves || validMoves.length === 0) return;
            if (validMoves.includes(idx)) {
                pit.classList.add('pit--playable');
                // Assure que les cases jouables répondent bien au clic
                pit.style.pointerEvents = '';
            } else {
                pit.classList.add('pit--disabled');
                // Bloque les événements JS sur les cases non jouables
                pit.style.pointerEvents = 'none';
            }
        });
        this._refreshInteraction();
    }

    /** Efface toute surbrillance et réactive tous les événements de clic */
    _clearHighlights() {
        this.pits.forEach(pit => {
            pit.classList.remove('pit--playable', 'pit--disabled', 'pit--active', 'pit--captured');
            pit.style.pointerEvents = '';
        });
        this._refreshInteraction();
    }

    // ─── Animation de semis ───────────────────────────────────────────────────

    /**
     * Calcule la séquence de cases touchées par un semis depuis `hole`.
     */
    sowSequence(hole, seedCount) {
        const seq = [];
        let current = hole;
        let seeds = seedCount;
        while (seeds > 0) {
            current = (current + 1) % 12;
            if (current === hole) continue;
            seq.push(current);
            seeds--;
        }
        return seq;
    }

    /**
     * Anime le semis case par case, puis flash les cases capturées.
     */
    async animateSow(hole, seedCount, boardSnapshot, capturedCells = [], delayMs = 110) {
        const generation = this._generation;
        const seq = this.sowSequence(hole, seedCount);

        const working = [...boardSnapshot];
        working[hole] = 0;

        // Vide la case de départ immédiatement
        const startPit = document.querySelector(`.pit[data-index="${hole}"]`);
        if (startPit) this._renderSeeds(startPit, 0);

        for (let step = 0; step < seq.length; step++) {
            if (generation !== this._generation) return;
            const idx   = seq[step];
            const pitEl = document.querySelector(`.pit[data-index="${idx}"]`);
            if (!pitEl) continue;

            working[idx]++;
            pitEl.classList.add('pit--active');
            this._renderSeeds(pitEl, working[idx]);

            await new Promise(r => setTimeout(r, delayMs));
            if (generation !== this._generation) return;
            pitEl.classList.remove('pit--active');
        }

        // Flash sur les cases capturées
        if (capturedCells.length > 0) {
            capturedCells.forEach(idx => {
                const el = document.querySelector(`.pit[data-index="${idx}"]`);
                if (el) el.classList.add('pit--captured');
            });
            await new Promise(r => setTimeout(r, 500));
            if (generation !== this._generation) return;
            capturedCells.forEach(idx => {
                const el = document.querySelector(`.pit[data-index="${idx}"]`);
                if (el) el.classList.remove('pit--captured');
            });
        }
    }

    /**
     * Déduit les cases capturées en comparant boardSnapshot et newBoard.
     * Une case est capturée si son count est passé à 0 ET que c'est une case adverse.
     */
    _findCapturedCells(hole, boardSnapshot, newBoard, playerKey) {
        const oppRange = playerKey === 'player1' ? [6, 11] : [0, 5];
        const captured = [];
        for (let i = oppRange[0]; i <= oppRange[1]; i++) {
            if (boardSnapshot[i] > 0 && newBoard[i] === 0) {
                captured.push(i);
            }
        }
        return captured;
    }

    // ─── Rendu de l'état complet ─────────────────────────────────────────────

    renderGameState() {
        if (!this.gameState) return;

        // Utilise data-index (position logique) et non l'ordre DOM
        //, l'ordre DOM (top-row 11→6, bottom-row 0→5) ne correspond pas
        //   à l'ordre du tableau board[] renvoyé par l'API (0→11).
        this.pits.forEach((pit) => {
            const idx = parseInt(pit.dataset.index);
            this._renderSeeds(pit, this.gameState.board[idx]);
        });

        this.updateScores(this.gameState.scores.player1, this.gameState.scores.player2);

        // Indicateur visuel du joueur courant sur les score-boxes
        const scoreP1 = document.querySelector('.score-box.player1');
        const scoreP2 = document.querySelector('.score-box.player2');
        if (scoreP1 && scoreP2 && !this.gameState.game_over) {
            scoreP1.classList.toggle('active-player', this.gameState.current_player === 'player1');
            scoreP2.classList.toggle('active-player', this.gameState.current_player === 'player2');
        } else if (scoreP1 && scoreP2) {
            scoreP1.classList.remove('active-player');
            scoreP2.classList.remove('active-player');
        }

        if (this.gameState.game_over) {
            this._clearHighlights();

            const winner = this.gameState.winner;
            const msg = winner
                ? `${this.players[winner].name} gagne !`
                : 'Match nul !';
            this.setStatus(`Partie terminée, ${msg}`, winner ? 'win' : 'draw');

            // Capturer le snapshot MAINTENANT : this.gameState peut être
            // écrasé pendant les 600ms (ex : clic rapide "Rejouer").
            const frozenState = this.gameState;
            const generation = this._generation;
            setTimeout(() => {
                if (generation === this._generation) this._showVictoryModal(frozenState);
            }, 600);
            return;
        }

        // Surbrillance des cases jouables uniquement si c'est le tour d'un humain
        const currentPlayer = this.players[this.gameState.current_player];
        if (currentPlayer.type === 'human') {
            this._highlightValidMoves(this.gameState.valid_moves);
        } else {
            this._clearHighlights();
        }
    }

    // ─── Modale victoire ─────────────────────────────────────────────────────

    _showVictoryModal(gs = this.gameState) {
        const winner = gs.winner;
        const isDraw = winner == null;
        document.getElementById('modal-reason').textContent = END_REASONS[gs.end_reason] || 'La partie est terminée.';

        const s1 = gs.scores.player1;
        const s2 = gs.scores.player2;

        // ── Titre + icône ───────────────────────────────────────
        const winnerLabel = document.getElementById('modal-winner-label');

        if (isDraw) {
            this.modalTitle.textContent    = 'Match nul !';
            this.modalIcon.innerHTML       = '<i class="fa-solid fa-handshake"></i>';
            this.modalIcon.className       = 'modal-icon draw';
            if (winnerLabel) winnerLabel.textContent = 'Résultat';
            this.modalWinner.textContent   = s1 === s2 ? 'Égalité des scores' : 'Partie nulle';
        } else {
            this.modalTitle.textContent    = 'Victoire !';
            this.modalIcon.innerHTML       = '<i class="fa-solid fa-trophy"></i>';
            this.modalIcon.className       = 'modal-icon win';
            if (winnerLabel) winnerLabel.textContent = 'Vainqueur';
            this.modalWinner.textContent = this.players[winner].name;
        }

        // ── Scores ──────────────────────────────────────────────
        // Noms complets (pas les labels courts J1/J2)
        this.modalSnameP1.textContent = this.players.player1.name;
        this.modalSnameP2.textContent = this.players.player2.name;
        this.modalSnumP1.textContent  = s1;
        this.modalSnumP2.textContent  = s2;
        this.modalScoreP1.classList.toggle('winner', winner === 'player1');
        this.modalScoreP2.classList.toggle('winner', winner === 'player2');

        // Confettis uniquement en cas de victoire
        const confettiEl = this.modalEnd.querySelector('.confetti');
        if (confettiEl) confettiEl.style.display = isDraw ? 'none' : '';

        // Ouverture
        if (!this.modalEnd.classList.contains('visible')) {
            this._focusBeforeModal = document.activeElement;
            this._bodyOverflowBeforeModal = document.body.style.overflow;
        }
        this.toastZone.replaceChildren();
        document.querySelector('.app-container').inert = true;
        document.body.style.overflow = 'hidden';
        this.modalEnd.inert = false;
        this.modalEnd.setAttribute('aria-hidden', 'false');
        void this.modalEnd.offsetWidth;           // force reflow → déclenche transition
        this.modalEnd.classList.add('visible');
        document.getElementById('modal-btn-replay').focus();
    }

    _closeModal() {
        if (!this.modalEnd.classList.contains('visible')) return;
        this.modalEnd.classList.remove('visible');
        this.modalEnd.setAttribute('aria-hidden', 'true');
        this.modalEnd.inert = true;
        document.querySelector('.app-container').inert = false;
        document.body.style.overflow = this._bodyOverflowBeforeModal || '';
        const target = this._focusBeforeModal;
        if (target?.isConnected && !target.disabled && target.getAttribute('aria-disabled') !== 'true') target.focus();
        else this.btnNewGame.focus();
    }

    _handleModalKeydown(event) {
        if (!this.modalEnd.classList.contains('visible')) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            this._closeModal();
        } else if (event.key === 'Tab') {
            const first = document.getElementById('modal-btn-replay');
            const last = document.getElementById('modal-btn-close');
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }
    }

    // ─── Verrou d'état ───────────────────────────────────────────────────────

    _setBusy(busy) {
        this._busy = busy;
        this.pits.forEach(pit => {
            pit.style.pointerEvents = busy ? 'none' : '';
        });
        // "Abandonner la partie" reste TOUJOURS actif pendant la partie,
        // y compris pendant les coups IA, seul gameState null le désactive.
        this.btnStop.disabled = !this.gameState;
        document.querySelector('.board')?.setAttribute('aria-busy', String(busy));
        if (!busy && this.gameState && !this.gameState.game_over) {
            const human = this.players[this.gameState.current_player].type === 'human';
            this._highlightValidMoves(human ? this.gameState.valid_moves : []);
        }
        this._syncSetup();
        this._refreshInteraction();
    }

    /**
     * Arrête la partie en cours, réinitialise le plateau et les scores.
     * Affiche un toast d'avertissement, puis remet tout à zéro côté client.
     * Aucun appel API, la prochaine partie enverra un nouveau /start.
     */
    resetGame() {
        this._cancelPending();
        this.btnNewGame.disabled = false;
        this.btnNewGame.innerHTML = '<i class="fa-solid fa-play"></i> Nouvelle partie';
        // Annule le verrou pour ne pas rester bloqué
        this._busy = false;
        this.pits.forEach(pit => { pit.style.pointerEvents = ''; });

        // Vide l'état de jeu
        this.gameState = null;

        // Remet le plateau à 4 graines par case
        this.renderInitialBoard();
        this.updateScores(0, 0);

        // Remet la barre d'analyse à zéro
        if (this.atbFill)     { this.atbFill.style.width = '0%'; }
        if (this.telemetryTime) { this.telemetryTime.textContent = 'Non disponible'; }
        if (this.analysisEmpty) { this.analysisEmpty.style.display = ''; }

        // Remet les stats / historique
        this._lastTelemetry = null;
        this._turnCount     = 0;
        this._granaryCache  = [];
        this.clearHistory();
        this._clearHighlights();

        // Retire la bordure "joueur actif"
        document.querySelector('.score-box.player1')?.classList.remove('active-player');
        document.querySelector('.score-box.player2')?.classList.remove('active-player');

        // Ferme la modale si ouverte
        this._closeModal();

        // Désactive Stop
        this.btnStop.disabled = true;

        this.setStatus('Partie abandonnée, plateau réinitialisé', 'idle');
        this._setBusy(false);
        this.showToast(
            'Partie abandonnée. Le plateau et les scores ont été réinitialisés.',
            'warning',
            4000
        );
    }

    // ─── Appels API ───────────────────────────────────────────────────────────

    _revealBoard() {
        const board = document.querySelector('.board-container');
        if (!board) return;
        const box = board.getBoundingClientRect();
        if (box.top < 0 || box.bottom > window.innerHeight) {
            document.querySelector('.scores-container')?.scrollIntoView({block: 'start', behavior: 'instant'});
        }
        if (document.activeElement === this.btnNewGame && this.btnNewGame.matches(':focus-visible')) {
            const valid = this.gameState.valid_moves;
            if (this.players[this.gameState.current_player].type === 'human') {
                [...this.pits].find(p => valid.includes(Number(p.dataset.index)))?.focus({preventScroll: true});
            }
        }
    }

    _cancelPending() {
        this._generation += 1;
        this._abortController.abort();
        this._abortController = new AbortController();
    }

    _requestIsCurrent(generation, state) {
        return generation === this._generation
            && this.gameState?.game_id === state.game_id
            && this.gameState?.version === state.version;
    }

    _acceptMoveState(data, state) {
        if (data?.game_id === state.game_id
                && Number.isSafeInteger(data.version) && data.version === state.version + 1) {
            return true;
        }
        this.showToast('La réponse ne correspond pas à ce coup. Relancez une nouvelle partie.', 'error');
        this.setStatus('Réponse de partie incohérente', 'error');
        this._setBusy(false);
        return false;
    }

    async _refreshAfterConflict(generation, state) {
        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/${state.game_id}`, {
                cache: 'no-store',
                signal: this._abortController.signal,
            });
            const data = await response.json();
            if (!this._requestIsCurrent(generation, state)) return;
            if (!response.ok || data?.game_id !== state.game_id
                    || !Number.isSafeInteger(data.version) || data.version < state.version) {
                throw new Error('La partie ne peut pas être actualisée.');
            }

            this.gameState = data;
            this._turnCount = data.version;
            this._lastTelemetry = null;
            this.renderGameState();
            if (data.game_over) return;

            const nextPlayer = this.players[data.current_player];
            this.setStatus(`Tour de ${nextPlayer.name}`, nextPlayer.type === 'ai' ? 'ai' : 'playing');
            if (nextPlayer.type === 'ai') {
                setTimeout(() => {
                    if (this._requestIsCurrent(generation, data)) this.playAI();
                }, 800);
            }
        } catch (error) {
            if (!this._requestIsCurrent(generation, state) || error.name === 'AbortError') return;
            this.showToast('Actualisation impossible. Réessayez ou démarrez une nouvelle partie.', 'error');
            this.setStatus('Actualisation de la partie impossible', 'error');
        } finally {
            if (generation === this._generation) this._setBusy(false);
        }
    }

    async startGame() {
        const previousGameId = this.gameState?.game_id;
        // Confirmation si partie en cours
        if (this.gameState && !this.gameState.game_over) {
            if (!confirm('Une partie est en cours. Voulez-vous vraiment recommencer ?')) return;
        }

        this._cancelPending();
        const generation = this._generation;
        this.gameState = null;
        this._setBusy(true);

        const player1Name = document.getElementById('player1-name').value.trim() || 'Joueur 1';
        const player2Name = document.getElementById('player2-name').value.trim() || 'Joueur 2';
        const player1Type = document.getElementById('player1-type').value;
        const player2Type = document.getElementById('player2-type').value;
        const player1Agent = document.getElementById('player1-agent').value;
        const player2Agent = document.getElementById('player2-agent').value;
        const player1Depth = parseInt(document.getElementById('player1-depth').value) || null;
        const player2Depth = parseInt(document.getElementById('player2-depth').value) || null;

        this.players.player1 = {
            name: player1Name, type: player1Type,
            agent: player1Agent, depth: player1Type === 'ai' ? player1Depth : null
        };
        this.players.player2 = {
            name: player2Name, type: player2Type,
            agent: player2Agent, depth: player2Type === 'ai' ? player2Depth : null
        };

        this.updatePlayerLabels();
        this.updateStatus('Initialisation de la partie…');
        this.clearHistory();
        this._clearHighlights();
        this._granaryCache = [];    // invalide le cache des granaires
        this._lastTelemetry = null; // reset analyse
        this._turnCount = 0;        // reset compteur de tours
        // Reset barre de temps à zéro
        if (this.atbFill) { this.atbFill.style.width = '0%'; }
        if (this.telemetryTime) { this.telemetryTime.textContent = 'Non disponible'; }
        if (this.analysisEmpty) { this.analysisEmpty.style.display = ''; }

        // Désactiver le bouton pendant le fetch pour éviter le double-clic
        this.btnNewGame.disabled = true;
        this.btnNewGame.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Chargement…';

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/start`, {
                method: 'POST',
                cache: 'no-store',
                signal: this._abortController.signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player1: this.players.player1,
                    player2: this.players.player2
                })
            });

            const data = await response.json();

            if (generation !== this._generation) return;

            if (!response.ok) {
                this.showToast(`Impossible de démarrer : ${data.detail}`, 'error');
                this.setStatus('Erreur au démarrage', 'error');
                return;
            }

            if (typeof data.game_id !== 'string'
                    || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(data.game_id)
                    || data.game_id === previousGameId || data.version !== 0) {
                this.showToast('Identifiant ou état initial de partie invalide.', 'error');
                this.setStatus('Erreur au démarrage', 'error');
                return;
            }
            this.gameState = data;
            this._lastTelemetry = null;         // reset analyse
            this.renderGameState();
            this._revealBoard();
            this.btnStop.disabled = false;      // active Stop dès que la partie est lancée
            const currentP = this.players[this.gameState.current_player];
            this.setStatus(`Tour de ${currentP.name}`, currentP.type === 'ai' ? 'ai' : 'playing');
            this.showToast('Partie démarrée, bonne chance !', 'success', 2500);

            if (currentP.type === 'ai') {
                setTimeout(() => {
                    if (generation === this._generation) this.playAI();
                }, 800);
            }

        } catch (error) {
            if (generation !== this._generation || error.name === 'AbortError') return;
            console.error('Error starting game:', error);
            this.showToast('Connexion au jeu impossible. Réessayez avec « Nouvelle partie ».', 'error', 6000);
            this.setStatus('Serveur inaccessible', 'error');
        } finally {
            if (generation === this._generation) {
                this._setBusy(false);
                this.btnNewGame.disabled = false;
                this.btnNewGame.innerHTML = '<i class="fa-solid fa-play"></i> Nouvelle partie';
                this._syncSetup();
            }
        }
    }

    async sendMove(pitIndex) {
        if (!this.gameState || this.gameState.game_over) {
            this.updateStatus('Veuillez démarrer une nouvelle partie');
            return;
        }

        // Verrou anti double-clic
        if (this._busy) return;
        const generation = this._generation;
        const requestState = { ...this.gameState, board: [...this.gameState.board] };

        const currentPlayerKey = this.gameState.current_player;
        const currentPlayer    = this.players[currentPlayerKey];

        if (currentPlayer.type === 'ai') {
            this.showToast(`C’est au tour de l’agent IA (${currentPlayer.name}). Il joue automatiquement.`, 'info', 2500);
            return;
        }

        // Validation client : case dans les coups valides
        if (!this.gameState.valid_moves.includes(pitIndex)) {
            this.showToast('Coup indisponible : sélectionnez une case surlignée en doré.', 'warning', 2500);
            return;
        }

        this._setBusy(true);
        this._clearHighlights();
        this.updateStatus('Envoi du coup…');

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/move`, {
                method: 'POST',
                cache: 'no-store',
                signal: this._abortController.signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    game_id: requestState.game_id,
                    version: requestState.version,
                    pit_index: pitIndex,
                    player: currentPlayerKey
                })
            });

            // BUG FIX : lire le corps UNE seule fois avant de tester response.ok
            const data = await response.json();
            if (generation !== this._generation) return;
            if (!this._requestIsCurrent(generation, requestState)) {
                this._setBusy(false);
                return;
            }

            if (!response.ok) {
                if (response.status === 409) {
                    this.showToast('Le plateau a changé. Actualisation de la partie…', 'warning');
                    await this._refreshAfterConflict(generation, requestState);
                    return;
                }
                this.showToast(`Coup refusé : ${data.detail}`, 'warning');
                this.setStatus('Coup invalide', 'error');
                this._setBusy(false);
                this._highlightValidMoves(this.gameState.valid_moves);
                return;
            }

            if (!this._acceptMoveState(data, requestState)) return;
            const seedCount      = requestState.board[pitIndex];
            const boardSnapshot  = [...requestState.board];
            const capturedCells  = this._findCapturedCells(pitIndex, boardSnapshot, data.board, currentPlayerKey);

            await this.animateSow(pitIndex, seedCount, boardSnapshot, capturedCells);
            if (generation !== this._generation) return;
            if (!this._requestIsCurrent(generation, requestState)) {
                this._setBusy(false);
                return;
            }

            this.gameState = data;

            // Les captures retirent des graines du plateau. Cette différence
            // conserve celles du coup gagnant sans compter les graines résiduelles.
            const captured = boardSnapshot.reduce((sum, count) => sum + count, 0)
                           - this.gameState.board.reduce((sum, count) => sum + count, 0);

            this.renderGameState();
            this.addToHistory(currentPlayer.name, pitIndex, captured, currentPlayerKey);

            if (this.gameState.game_over) {
                this._setBusy(false);
                return;
            }

            const nextPlayer = this.players[this.gameState.current_player];
            this.setStatus(`Tour de ${nextPlayer.name}`, nextPlayer.type === 'ai' ? 'ai' : 'playing');

            if (nextPlayer.type === 'ai') {
                setTimeout(() => {
                    if (generation !== this._generation) return;
                    this._setBusy(false);
                    this.playAI();
                }, 800);
                return;
            }

        } catch (error) {
            if (generation !== this._generation || error.name === 'AbortError') return;
            console.error('Error sending move:', error);
            this.showToast('Erreur réseau lors de l\'envoi du coup.', 'error');
            this.setStatus('Erreur réseau', 'error');
        }

        this._setBusy(false);
    }

    async playAI() {
        if (!this.gameState || this.gameState.game_over) {
            this.showToast('Démarrez une nouvelle partie d\'abord.', 'warning');
            return;
        }

        if (this._busy) return;
        const generation = this._generation;
        const requestState = { ...this.gameState, board: [...this.gameState.board] };

        const currentPlayerKey = this.gameState.current_player;
        const currentPlayer    = this.players[currentPlayerKey];

        if (currentPlayer.type !== 'ai') {
            this.showToast(`${currentPlayer.name} n'est pas une IA.`, 'info');
            return;
        }

        this._setBusy(true);
        this.setStatus(`${currentPlayer.name} calcule son coup…`, 'ai');

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/ai-move`, {
                method: 'POST',
                cache: 'no-store',
                signal: this._abortController.signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    game_id: requestState.game_id,
                    version: requestState.version,
                    player: currentPlayerKey,
                    agent:  currentPlayer.agent,
                    depth:  currentPlayer.depth,
                    board:  requestState.board
                })
            });

            const data = await response.json();
            if (generation !== this._generation) return;
            if (!this._requestIsCurrent(generation, requestState)) {
                this._setBusy(false);
                return;
            }

            if (!response.ok) {
                if (response.status === 409) {
                    this.showToast('Le plateau a changé. Actualisation de la partie…', 'warning');
                    await this._refreshAfterConflict(generation, requestState);
                    return;
                }
                this.showToast(`Erreur IA : ${data.detail}`, 'error');
                this.setStatus('Erreur IA', 'error');
                this._setBusy(false);
                return;
            }

            if (!this._acceptMoveState(data.game_state, requestState)) return;
            const pitIndex      = data.telemetry.pit_played;
            const seedCount     = requestState.board[pitIndex];
            const boardSnapshot = [...requestState.board];
            const capturedCells = this._findCapturedCells(pitIndex, boardSnapshot, data.game_state.board, currentPlayerKey);

            await this.animateSow(pitIndex, seedCount, boardSnapshot, capturedCells);
            if (generation !== this._generation) return;
            if (!this._requestIsCurrent(generation, requestState)) {
                this._setBusy(false);
                return;
            }

            this.gameState = data.game_state;
            this.updateTelemetry(data.telemetry);

            // Les captures retirent des graines du plateau. Cette différence
            // conserve celles du coup gagnant sans compter les graines résiduelles.
            const captured = boardSnapshot.reduce((sum, count) => sum + count, 0)
                           - this.gameState.board.reduce((sum, count) => sum + count, 0);

            this.renderGameState();
            this.addToHistory(currentPlayer.name, pitIndex, captured, currentPlayerKey);

            if (this.gameState.game_over) {
                this._setBusy(false);
                return;
            }

            const nextPlayer = this.players[this.gameState.current_player];
            this.setStatus(`Tour de ${nextPlayer.name}`, nextPlayer.type === 'ai' ? 'ai' : 'playing');

            if (nextPlayer.type === 'ai') {
                setTimeout(() => {
                    if (generation !== this._generation) return;
                    this._setBusy(false);
                    this.playAI();
                }, 800);
                return;
            }

        } catch (error) {
            if (generation !== this._generation || error.name === 'AbortError') return;
            console.error('Error playing AI move:', error);
            this.showToast('Erreur réseau lors du coup IA.', 'error');
            this.setStatus('Erreur réseau', 'error');
        }

        this._setBusy(false);
    }
}

// Initialisation au chargement du DOM
document.addEventListener('DOMContentLoaded', () => {
    window.awaleGame = new AwaleGame();
});
