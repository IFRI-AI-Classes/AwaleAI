// Awalé AI Frontend — JavaScript Module
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
    alphabeta: 'Alpha-Beta',
    qlearning: 'Q-Learning',
};

// Profondeur par défaut selon l'agent
const AGENT_DEFAULT_DEPTH = {
    minimax:   5,
    alphabeta: 6,
};

class AwaleGame {
    constructor() {
        this.apiBaseUrl = window.location.hostname === 'localhost'
            ? 'http://localhost:8000'
            : 'https://awale-ai-backend.onrender.com';
        this.gameState = null;
        this._busy = false;           // verrou global — empêche les actions simultanées
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
        this.btnAiPlay          = document.getElementById('btn-ai-play');

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
        this.modalPerf          = document.getElementById('modal-perf');
        this.modalPerfGrid      = document.getElementById('modal-perf-grid');
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
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this._closeModal();
        });

        // Statistiques de performance cumulées sur toute la partie
        this._lastTelemetry = null;
        this._perfStats = {
            bestTime:  null,   // ms — meilleur (plus rapide) temps de réflexion
            worstTime: null,   // ms — pire temps (le plus long)
            bestPit:   null,   // case jouée lors du coup le plus rapide
            totalMoves: 0,
            totalTime:  0,
        };

        // Initialise les selects de profondeur
        this._refreshDepthSelect('player1');
        this._refreshDepthSelect('player2');

        this.updatePlayerLabels();
        this.renderInitialBoard();
        this._updateAiButton();
        this.setStatus('En attente de nouvelle partie', 'idle');
    }

    attachEventListeners() {
        this.btnNewGame.addEventListener('click', () => this.startGame());
        this.btnAiPlay.addEventListener('click',  () => this.playAI());

        // Clic sur une case
        this.pits.forEach(pit => {
            pit.addEventListener('click', () => {
                const pitIndex = parseInt(pit.dataset.index);
                this.sendMove(pitIndex);
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
        });
        document.getElementById('player2-depth').addEventListener('change', (e) => {
            this.players.player2.depth = e.target.value ? parseInt(e.target.value) : null;
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
        this._updateAiButton();
    }

    updatePlayerLabels() {
        const getDisplayName = (player) => {
            if (player.type === 'ai') {
                const label = AGENT_LABELS[player.agent] || player.agent;
                const depthStr = player.depth != null ? ` — prof. ${player.depth}` : '';
                return `${label}${depthStr}`;
            }
            return player.name;
        };

        this.labelPlayer1.textContent = getDisplayName(this.players.player1);
        this.labelPlayer2.textContent = getDisplayName(this.players.player2);
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

        if (!depths) {
            // Pas de profondeur pour cet agent
            depthRow.style.display    = 'none';
            this.players[playerKey].depth = null;
            return;
        }

        depthRow.style.display = '';
        const defaultDepth = AGENT_DEFAULT_DEPTH[agent] ?? depths[Math.floor(depths.length / 2)];

        depthSelect.innerHTML = depths.map(d => {
            const label = this._depthLabel(d, agent);
            const sel = d === defaultDepth ? ' selected' : '';
            return `<option value="${d}"${sel}>${label}</option>`;
        }).join('');

        this.players[playerKey].depth = defaultDepth;
    }

    /**
     * Retourne un libellé humain pour une profondeur donnée.
     * Associe chaque plage à un nom de niveau.
     */
    _depthLabel(depth, agent) {
        if (agent === 'minimax') {
            if (depth <= 2) return `${depth} — Facile`;
            if (depth <= 4) return `${depth} — Moyen`;
            if (depth <= 6) return `${depth} — Difficile`;
            return `${depth} — Expert`;
        }
        // alphabeta
        if (depth <= 2)  return `${depth} — Facile`;
        if (depth <= 4)  return `${depth} — Moyen`;
        if (depth <= 6)  return `${depth} — Difficile`;
        if (depth <= 9)  return `${depth} — Expert`;
        return `${depth} — Maître`;
    }

    /** Met à jour la visibilité du bouton "IA joue" */
    _updateAiButton() {
        const currentKey = this.gameState ? this.gameState.current_player : null;
        const currentIsAi = currentKey
            ? this.players[currentKey].type === 'ai'
            : (this.players.player1.type === 'ai' || this.players.player2.type === 'ai');

        // Visible uniquement si au moins un des joueurs est IA ET partie active
        const hasAi = this.players.player1.type === 'ai' || this.players.player2.type === 'ai';
        this.btnAiPlay.style.display = hasAi ? '' : 'none';
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
     * Rend les graines d'une case — ne recrée le DOM que si le count change.
     */
    _renderSeeds(pitElement, seedCount) {
        const seedsContainer = pitElement.querySelector('.seeds');
        const prev = parseInt(seedsContainer.dataset.count ?? '-1');
        if (prev === seedCount) return;   // rien à faire

        seedsContainer.innerHTML = '';
        seedsContainer.dataset.count = seedCount;

        if (seedCount === 0) return;

        for (let i = 0; i < seedCount; i++) {
            const seed = document.createElement('div');
            seed.className = 'seed';
            const angle  = (i / seedCount) * 2 * Math.PI;
            const radius = Math.min(15, 20 - seedCount);
            const x = Math.cos(angle) * radius;
            const y = Math.sin(angle) * radius;
            seed.style.left = `calc(50% + ${x}px - 6px)`;
            seed.style.top  = `calc(50% + ${y}px - 6px)`;
            seedsContainer.appendChild(seed);
        }
    }

    /**
     * Rend les graines dans une granaire.
     * Les positions sont mises en cache par (elementId, seedCount) pour éviter
     * de recalculer Math.random() à chaque coup.
     */
    _renderGranarySeeds(granaryElement, seedCount) {
        const cacheKey = `${granaryElement.id}_${seedCount}`;
        if (granaryElement.dataset.count == seedCount) return;  // rien à faire

        granaryElement.innerHTML = '';
        granaryElement.dataset.count = seedCount;

        if (seedCount === 0) return;

        // Utilise le cache ou calcule et stocke
        if (!this._granaryCache[cacheKey]) {
            const displayCount = Math.min(seedCount, 50);
            const positions = [];
            for (let i = 0; i < displayCount; i++) {
                positions.push({
                    x: Math.random() * 80 + 5,   // pourcentage relatif — granaire ~50px wide
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
        this.gameStatus.textContent = message;
        const dot = this.statusDot;
        dot.className = 'status-dot ' + state;
    }

    // Compat alias — appelé par plusieurs endroits
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
        t.innerHTML = `<i class="${icons[type] || icons.info}"></i><span>${message}</span>`;
        this.toastZone.appendChild(t);

        setTimeout(() => {
            t.classList.add('toast-out');
            t.addEventListener('animationend', () => t.remove(), { once: true });
        }, durationMs);
    }

    /**
     * Met à jour le panneau "Analyse du coup IA".
     * Remplace l'ancienne updateTelemetry().
     */
    updateTelemetry(telemetry) {
        if (!telemetry) return;

        this._lastTelemetry = telemetry;

        // ── Accumulation des stats de performance ─────────────────
        const ms = telemetry.computation_time;
        if (ms != null) {
            const p = this._perfStats;
            p.totalMoves++;
            p.totalTime += ms;
            if (p.bestTime === null || ms < p.bestTime) {
                p.bestTime = ms;
                p.bestPit  = telemetry.pit_played ?? null;
            }
            if (p.worstTime === null || ms > p.worstTime) {
                p.worstTime = ms;
            }
        }

        const agent       = telemetry.agent || '';
        const isRandom    = agent === 'random';
        const isQLearning = agent === 'qlearning';

        // Cache le message "aucune IA"
        if (this.analysisEmpty) this.analysisEmpty.style.display = 'none';

        // ── Barre de temps ──────────────────────────────────
        this.telemetryTime.textContent = ms != null ? `${ms} ms` : '--';

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
            const lvl = this._depthLabel(d, agent);
            this.telemetryDepth.textContent = d != null ? `${d}  (${lvl.split('—')[1]?.trim() || ''})` : '--';
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
        const row   = pitIndex < 6 ? 'Bas' : 'Haut';
        const caseN = pitIndex < 6 ? pitIndex + 1 : pitIndex - 5;
        const badgeClass = playerKey === 'player1' ? 'badge-p1' : 'badge-p2';

        historyItem.innerHTML = `
            <span class="history-turn">#${this._turnCount}</span>
            <span class="history-player ${badgeClass}">${playerName}</span>
            <span class="history-move">${row} C${caseN}</span>
            ${captured > 0 ? `<span class="history-capture">+${captured}</span>` : ''}
        `;

        const emptyMessage = this.moveHistoryContainer.querySelector('.empty-history');
        if (emptyMessage) emptyMessage.remove();

        this.moveHistoryContainer.prepend(historyItem);   // derniers coups en haut
    }

    clearHistory() {
        this.moveHistoryContainer.innerHTML = '<p class="empty-history">Aucun coup joué</p>';
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
            if (!validMoves || validMoves.length === 0) return;
            if (validMoves.includes(idx)) {
                pit.classList.add('pit--playable');
            } else {
                pit.classList.add('pit--disabled');
            }
        });
    }

    /** Efface toute surbrillance */
    _clearHighlights() {
        this.pits.forEach(pit => {
            pit.classList.remove('pit--playable', 'pit--disabled', 'pit--active', 'pit--captured');
        });
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
        const seq = this.sowSequence(hole, seedCount);

        const working = [...boardSnapshot];
        working[hole] = 0;

        // Vide la case de départ immédiatement
        const startPit = document.querySelector(`.pit[data-index="${hole}"]`);
        if (startPit) this._renderSeeds(startPit, 0);

        for (let step = 0; step < seq.length; step++) {
            const idx   = seq[step];
            const pitEl = document.querySelector(`.pit[data-index="${idx}"]`);
            if (!pitEl) continue;

            working[idx]++;
            pitEl.classList.add('pit--active');
            this._renderSeeds(pitEl, working[idx]);

            await new Promise(r => setTimeout(r, delayMs));
            pitEl.classList.remove('pit--active');
        }

        // Flash sur les cases capturées
        if (capturedCells.length > 0) {
            capturedCells.forEach(idx => {
                const el = document.querySelector(`.pit[data-index="${idx}"]`);
                if (el) el.classList.add('pit--captured');
            });
            await new Promise(r => setTimeout(r, 500));
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

        this.pits.forEach((pit, index) => {
            this._renderSeeds(pit, this.gameState.board[index]);
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
            this._updateAiButton();

            const winner = this.gameState.winner;
            const msg = winner
                ? `${this.players[winner].name} gagne !`
                : 'Match nul !';
            this.setStatus(`Partie terminée — ${msg}`, winner ? 'win' : 'draw');

            // Modale différée de 600ms pour laisser l'animation finir
            setTimeout(() => this._showVictoryModal(), 600);
            return;
        }

        // Surbrillance des cases jouables uniquement si c'est le tour d'un humain
        const currentPlayer = this.players[this.gameState.current_player];
        if (currentPlayer.type === 'human') {
            this._highlightValidMoves(this.gameState.valid_moves);
        } else {
            this._clearHighlights();
        }

        this._updateAiButton();
    }

    // ─── Modale victoire ─────────────────────────────────────────────────────

    _showVictoryModal() {
        const gs     = this.gameState;
        const winner = gs.winner;
        const isDraw = winner === null;

        const s1 = gs.scores.player1;
        const s2 = gs.scores.player2;

        // ── Titre + icône ───────────────────────────────────────
        const winnerLabel = document.getElementById('modal-winner-label');

        if (isDraw) {
            this.modalTitle.textContent    = 'Match nul !';
            this.modalIcon.innerHTML       = '<i class="fa-solid fa-handshake"></i>';
            this.modalIcon.className       = 'modal-icon draw';
            if (winnerLabel) winnerLabel.textContent = 'Résultat';
            this.modalWinner.textContent   = 'Égalité parfaite';
        } else {
            this.modalTitle.textContent    = 'Victoire !';
            this.modalIcon.innerHTML       = '<i class="fa-solid fa-trophy"></i>';
            this.modalIcon.className       = 'modal-icon win';
            if (winnerLabel) winnerLabel.textContent = 'Vainqueur';
            this.modalWinner.innerHTML     =
                `<i class="fa-solid fa-crown" style="color:var(--accent-gold);margin-right:6px;font-size:0.9em"></i>`
                + this.players[winner].name;
        }

        // ── Scores ──────────────────────────────────────────────
        // Noms complets (pas les labels courts J1/J2)
        this.modalSnameP1.textContent = this.players.player1.name;
        this.modalSnameP2.textContent = this.players.player2.name;
        this.modalSnumP1.textContent  = s1;
        this.modalSnumP2.textContent  = s2;
        this.modalScoreP1.classList.toggle('winner', winner === 'player1');
        this.modalScoreP2.classList.toggle('winner', winner === 'player2');

        // ── Performance IA ──────────────────────────────────────
        const t      = this._lastTelemetry;
        const p      = this._perfStats;
        const hasAi  = this.players.player1.type === 'ai' || this.players.player2.type === 'ai';

        if (t && hasAi) {
            this.modalPerf.classList.add('visible');

            const agentLabel  = AGENT_LABELS[t.agent] || t.agent || '--';
            const depth       = t.depth != null ? `${t.depth}` : 'N/A';
            const lastTime    = t.computation_time != null ? `${t.computation_time} ms` : 'N/A';
            const nodes       = t.nodes_explored   != null ? t.nodes_explored.toLocaleString('fr-FR') : 'N/A';
            const bestTime    = p.bestTime  != null ? `${p.bestTime} ms`  : 'N/A';
            const avgTime     = p.totalMoves > 0
                ? `${(p.totalTime / p.totalMoves).toFixed(1)} ms`
                : 'N/A';

            // Meilleur coup : rang lisible (Bas C1-6 / Haut C1-6)
            let bestPitLabel = 'N/A';
            if (p.bestPit != null) {
                const row   = p.bestPit < 6 ? 'Bas' : 'Haut';
                const caseN = p.bestPit < 6 ? p.bestPit + 1 : p.bestPit - 5;
                bestPitLabel = `${row} C${caseN}`;
            }

            this.modalPerfGrid.innerHTML = `
                <div class="modal-perf-item">
                  <span class="pi-label"><i class="fa-solid fa-robot"></i> Modèle IA</span>
                  <span class="pi-value">${agentLabel}</span>
                </div>
                <div class="modal-perf-item">
                  <span class="pi-label"><i class="fa-solid fa-sitemap"></i> Niveau d'analyse</span>
                  <span class="pi-value">${depth}</span>
                </div>
                <div class="modal-perf-item">
                  <span class="pi-label"><i class="fa-solid fa-bolt"></i> Meilleur temps</span>
                  <span class="pi-value pi-best">${bestTime}</span>
                </div>
                <div class="modal-perf-item">
                  <span class="pi-label"><i class="fa-solid fa-chess-knight"></i> Coup le + rapide</span>
                  <span class="pi-value pi-best">${bestPitLabel}</span>
                </div>
                <div class="modal-perf-item">
                  <span class="pi-label"><i class="fa-regular fa-clock"></i> Temps moyen</span>
                  <span class="pi-value">${avgTime}</span>
                </div>
                <div class="modal-perf-item">
                  <span class="pi-label"><i class="fa-solid fa-circle-nodes"></i> Coups évalués</span>
                  <span class="pi-value">${nodes}</span>
                </div>`;
        } else {
            this.modalPerf.classList.remove('visible');
        }

        // Confettis uniquement en cas de victoire
        const confettiEl = this.modalEnd.querySelector('.confetti');
        if (confettiEl) confettiEl.style.display = isDraw ? 'none' : '';

        // Ouverture
        this.modalEnd.setAttribute('aria-hidden', 'false');
        void this.modalEnd.offsetWidth;           // force reflow → déclenche transition
        this.modalEnd.classList.add('visible');
    }

    _closeModal() {
        this.modalEnd.classList.remove('visible');
        this.modalEnd.setAttribute('aria-hidden', 'true');
    }

    // ─── Verrou d'état ───────────────────────────────────────────────────────

    _setBusy(busy) {
        this._busy = busy;
        this.pits.forEach(pit => {
            pit.style.pointerEvents = busy ? 'none' : '';
        });
        this.btnAiPlay.disabled  = busy;
        // Le bouton "Nouvelle partie" reste actif même pendant une animation
        // (on gère le double-clic séparément via disabled pendant le fetch)
    }

    // ─── Appels API ───────────────────────────────────────────────────────────

    async startGame() {
        // Confirmation si partie en cours
        if (this.gameState && !this.gameState.game_over) {
            if (!confirm('Une partie est en cours. Voulez-vous vraiment recommencer ?')) return;
        }

        const player1Name = document.getElementById('player1-name').value || 'Joueur 1';
        const player2Name = document.getElementById('player2-name').value || 'Joueur 2';
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
        this._perfStats = { bestTime: null, worstTime: null, bestPit: null, totalMoves: 0, totalTime: 0 };
        // Reset barre de temps à zéro
        if (this.atbFill) { this.atbFill.style.width = '0%'; }
        if (this.telemetryTime) { this.telemetryTime.textContent = '--'; }
        if (this.analysisEmpty) { this.analysisEmpty.style.display = ''; }

        // Désactiver le bouton pendant le fetch pour éviter le double-clic
        this.btnNewGame.disabled = true;
        this.btnNewGame.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Chargement…';

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player1: { name: player1Name, type: player1Type },
                    player2: { name: player2Name, type: player2Type }
                })
            });

            const data = await response.json();

            if (!response.ok) {
                this.showToast(`Impossible de démarrer : ${data.detail}`, 'error');
                this.setStatus('Erreur au démarrage', 'error');
                return;
            }

            this.gameState = data;
            this._lastTelemetry = null;         // reset analyse
            this.renderGameState();
            const currentP = this.players[this.gameState.current_player];
            this.setStatus(`Tour de ${currentP.name}`, currentP.type === 'ai' ? 'ai' : 'playing');
            this.showToast('Partie démarrée — bonne chance !', 'success', 2500);

            // Auto-play IA si les deux sont IA
            if (this.players.player1.type === 'ai' && this.players.player2.type === 'ai') {
                setTimeout(() => this.playAI(), 800);
            }

        } catch (error) {
            console.error('Error starting game:', error);
            this.showToast('Serveur inaccessible — vérifiez que le backend tourne sur le port 8000.', 'error', 6000);
            this.setStatus('Serveur inaccessible', 'error');
        } finally {
            this.btnNewGame.disabled = false;
            this.btnNewGame.innerHTML = '<i class="fa-solid fa-play"></i> Nouvelle partie';
        }
    }

    async sendMove(pitIndex) {
        if (!this.gameState || this.gameState.game_over) {
            this.updateStatus('Veuillez démarrer une nouvelle partie');
            return;
        }

        // Verrou anti double-clic
        if (this._busy) return;

        const currentPlayerKey = this.gameState.current_player;
        const currentPlayer    = this.players[currentPlayerKey];

        if (currentPlayer.type === 'ai') {
            this.showToast(`C'est au tour de l'IA (${currentPlayer.name}). Cliquez sur "IA joue".`, 'info', 2500);
            return;
        }

        // Validation client : case dans les coups valides
        if (!this.gameState.valid_moves.includes(pitIndex)) {
            this.showToast('Case invalide — choisissez une case en surbrillance.', 'warning', 2500);
            return;
        }

        this._setBusy(true);
        this._clearHighlights();
        this.updateStatus('Envoi du coup…');

        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pit_index: pitIndex, player: currentPlayerKey })
            });

            // BUG FIX : lire le corps UNE seule fois avant de tester response.ok
            const data = await response.json();

            if (!response.ok) {
                this.showToast(`Coup refusé : ${data.detail}`, 'warning');
                this.setStatus('Coup invalide', 'error');
                this._setBusy(false);
                this._highlightValidMoves(this.gameState.valid_moves);
                return;
            }

            const scoresBefore   = { ...this.gameState.scores };
            const seedCount      = this.gameState.board[pitIndex];
            const boardSnapshot  = [...this.gameState.board];
            const capturedCells  = this._findCapturedCells(pitIndex, boardSnapshot, data.board, currentPlayerKey);

            await this.animateSow(pitIndex, seedCount, boardSnapshot, capturedCells);

            this.gameState = data;

            const captured = (this.gameState.scores[currentPlayerKey] || 0)
                           - (scoresBefore[currentPlayerKey] || 0);

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
                    this._setBusy(false);
                    this.playAI();
                }, 800);
                return;
            }

        } catch (error) {
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

        const currentPlayerKey = this.gameState.current_player;
        const currentPlayer    = this.players[currentPlayerKey];

        if (currentPlayer.type !== 'ai') {
            this.showToast(`${currentPlayer.name} n'est pas une IA.`, 'info');
            return;
        }

        this._setBusy(true);
        this.setStatus(`${currentPlayer.name} réfléchit…`, 'ai');

        try {
            const scoresBefore = { ...this.gameState.scores };

            const response = await fetch(`${this.apiBaseUrl}/api/game/ai-move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player: currentPlayerKey,
                    agent:  currentPlayer.agent,
                    depth:  currentPlayer.depth,
                    board:  this.gameState.board
                })
            });

            const data = await response.json();

            if (!response.ok) {
                this.showToast(`Erreur IA : ${data.detail}`, 'error');
                this.setStatus('Erreur IA', 'error');
                this._setBusy(false);
                return;
            }

            const pitIndex      = data.telemetry.pit_played;
            const seedCount     = this.gameState.board[pitIndex];
            const boardSnapshot = [...this.gameState.board];
            const capturedCells = this._findCapturedCells(pitIndex, boardSnapshot, data.game_state.board, currentPlayerKey);

            await this.animateSow(pitIndex, seedCount, boardSnapshot, capturedCells);

            this.gameState = data.game_state;
            this.updateTelemetry(data.telemetry);

            const captured = (this.gameState.scores[currentPlayerKey] || 0)
                           - (scoresBefore[currentPlayerKey] || 0);

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
                    this._setBusy(false);
                    this.playAI();
                }, 800);
                return;
            }

        } catch (error) {
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
