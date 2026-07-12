// Awalé AI Frontend - JavaScript Module
// This file handles UI interactions and REST API communication with the Python backend
// No game logic is implemented here - all game rules and AI are handled by the backend

class AwaleGame {
    constructor() {
        this.apiBaseUrl = 'http://localhost:8000'; // TODO: Update with actual backend URL
        this.gameState = null;
        this.players = {
            player1: { name: 'Joueur 1', type: 'human', level: null },
            player2: { name: 'Joueur 2', type: 'human', level: null }
        };
        
        this.initializeUI();
        this.attachEventListeners();
    }

    initializeUI() {
        this.pits = document.querySelectorAll('.pit');
        this.scorePlayer1 = document.getElementById('score-player1');
        this.scorePlayer2 = document.getElementById('score-player2');
        this.labelPlayer1 = document.getElementById('label-player1');
        this.labelPlayer2 = document.getElementById('label-player2');
        this.gameStatus = document.getElementById('game-status');
        this.moveHistoryContainer = document.getElementById('move-history');
        this.telemetryTime = document.getElementById('telemetry-time');
        this.telemetryDepth = document.getElementById('telemetry-depth');
        this.telemetryNodes = document.getElementById('telemetry-nodes');
        this.telemetryWinrate = document.getElementById('telemetry-winrate');
        this.granarySeedsPlayer1 = document.getElementById('granary-seeds-player1');
        this.granarySeedsPlayer2 = document.getElementById('granary-seeds-player2');
        
        this.updatePlayerLabels();
        this.renderInitialBoard();
    }

    attachEventListeners() {
        document.getElementById('btn-new-game').addEventListener('click', () => this.startGame());
        document.getElementById('btn-ai-play').addEventListener('click', () => this.playAI());
        
        this.pits.forEach(pit => {
            pit.addEventListener('click', () => {
                const pitIndex = parseInt(pit.dataset.index);
                this.sendMove(pitIndex);
            });
        });

        // Player type change handlers
        document.getElementById('player1-type').addEventListener('change', (e) => {
            this.handlePlayerTypeChange('player1', e.target.value);
        });
        
        document.getElementById('player2-type').addEventListener('change', (e) => {
            this.handlePlayerTypeChange('player2', e.target.value);
        });

        // Player name change handlers
        document.getElementById('player1-name').addEventListener('input', (e) => {
            this.players.player1.name = e.target.value || 'Joueur 1';
            this.updatePlayerLabels();
        });
        
        document.getElementById('player2-name').addEventListener('input', (e) => {
            this.players.player2.name = e.target.value || 'Joueur 2';
            this.updatePlayerLabels();
        });

        // Level change handlers — met à jour players[].level en direct
        // si l'utilisateur change de niveau APRES avoir sélectionné "IA"
        document.getElementById('player1-algorithm').addEventListener('change', (e) => {
            this.players.player1.level = e.target.value;
            this.updatePlayerLabels();
        });

        document.getElementById('player2-algorithm').addEventListener('change', (e) => {
            this.players.player2.level = e.target.value;
            this.updatePlayerLabels();
        });
    }

    handlePlayerTypeChange(playerKey, type) {
        const aiConfig = document.getElementById(`${playerKey}-ai-config`);
        const levelSelect = document.getElementById(`${playerKey}-algorithm`);
        
        this.players[playerKey].type = type;
        
        if (type === 'ai') {
            aiConfig.style.display = 'flex';
            this.players[playerKey].level = levelSelect.value;
            this.updatePlayerLabels();
        } else {
            aiConfig.style.display = 'none';
            this.players[playerKey].level = null;
            this.updatePlayerLabels();
        }
    }

    updatePlayerLabels() {
        const getDisplayName = (player) => {
            if (player.type === 'ai') {
                return player.level ? `IA ${player.level.charAt(0).toUpperCase() + player.level.slice(1)}` : 'IA';
            }
            return player.name;
        };
        
        this.labelPlayer1.textContent = getDisplayName(this.players.player1);
        this.labelPlayer2.textContent = getDisplayName(this.players.player2);
    }

    /**
     * Calcule la séquence de cases touchées par un semis depuis `hole`
     * en suivant le sens +1 % 12 du moteur Python (saute la case de départ
     * si le tour est assez long pour y revenir).
     * Retourne un tableau d'index dans l'ordre de distribution.
     */
    sowSequence(hole, seedCount) {
        const seq = [];
        let current = hole;
        let seeds = seedCount;
        while (seeds > 0) {
            current = (current + 1) % 12;
            if (current === hole) continue;   // règle Kroo : on saute le départ
            seq.push(current);
            seeds--;
        }
        return seq;
    }

    /**
     * Anime le semis : illumine les cases une par une dans l'ordre de
     * distribution, puis retire les surlignages.
     * `boardSnapshot` est le tableau board[] AVANT le coup (pour afficher
     * l'état intermédiaire +1 graine à chaque case).
     */
    async animateSow(hole, seedCount, boardSnapshot, delayMs = 120) {
        const seq = this.sowSequence(hole, seedCount);

        // Copie de travail du plateau (avant coup) : on vide le départ
        const working = [...boardSnapshot];
        working[hole] = 0;

        // Compte combien de graines chaque case reçoit
        const bonus = new Array(12).fill(0);
        for (const idx of seq) bonus[idx]++;

        // Affiche le départ vide immédiatement
        const startPit = document.querySelector(`.pit[data-index="${hole}"]`);
        if (startPit) this.renderSeeds(startPit, 0);

        // Parcourt case par case
        for (let step = 0; step < seq.length; step++) {
            const idx = seq[step];
            const pitEl = document.querySelector(`.pit[data-index="${idx}"]`);
            if (!pitEl) continue;

            // +1 graine sur la copie de travail
            working[idx]++;

            // Surlignage
            pitEl.classList.add('pit--active');
            this.renderSeeds(pitEl, working[idx]);

            await new Promise(r => setTimeout(r, delayMs));
            pitEl.classList.remove('pit--active');
        }
    }

    renderInitialBoard() {
        const initialSeeds = [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4];
        this.pits.forEach((pit, index) => {
            this.renderSeeds(pit, initialSeeds[index]);
        });
        this.renderGranarySeeds(this.granarySeedsPlayer1, 0);
        this.renderGranarySeeds(this.granarySeedsPlayer2, 0);
    }

    renderSeeds(pitElement, seedCount) {
        const seedsContainer = pitElement.querySelector('.seeds');
        seedsContainer.innerHTML = '';
        
        if (seedCount === 0) return;
        
        for (let i = 0; i < seedCount; i++) {
            const seed = document.createElement('div');
            seed.className = 'seed';
            const angle = (i / seedCount) * 2 * Math.PI;
            const radius = Math.min(15, 20 - seedCount);
            const x = Math.cos(angle) * radius;
            const y = Math.sin(angle) * radius;
            seed.style.left = `calc(50% + ${x}px - 6px)`;
            seed.style.top = `calc(50% + ${y}px - 6px)`;
            seedsContainer.appendChild(seed);
        }
    }

    renderGranarySeeds(granaryElement, seedCount) {
        granaryElement.innerHTML = '';
        
        if (seedCount === 0) return;
        
        const displayCount = Math.min(seedCount, 50);
        
        for (let i = 0; i < displayCount; i++) {
            const seed = document.createElement('div');
            seed.className = 'granary-seed';
            
            const granaryRect = granaryElement.getBoundingClientRect();
            const width = granaryRect.width || 50;
            const height = granaryRect.height || 250;
            
            const x = Math.random() * (width - 15) + 5;
            const y = Math.random() * (height - 15) + 5;
            
            seed.style.left = `${x}px`;
            seed.style.top = `${y}px`;
            
            granaryElement.appendChild(seed);
        }
    }

    updateScores(score1, score2) {
        this.scorePlayer1.textContent = score1;
        this.scorePlayer2.textContent = score2;
        this.renderGranarySeeds(this.granarySeedsPlayer1, score1);
        this.renderGranarySeeds(this.granarySeedsPlayer2, score2);
    }

    updateStatus(message) {
        this.gameStatus.textContent = message;
    }

    updateTelemetry(telemetry) {
        if (telemetry) {
            this.telemetryTime.textContent = telemetry.computation_time ? `${telemetry.computation_time}ms` : '--';
            this.telemetryDepth.textContent = telemetry.depth ? telemetry.depth : '--';
            this.telemetryNodes.textContent = telemetry.nodes_explored ? telemetry.nodes_explored.toLocaleString() : '--';
            this.telemetryWinrate.textContent = telemetry.win_rate ? `${(telemetry.win_rate * 100).toFixed(1)}%` : '--';
        }
    }

    addToHistory(playerName, pitIndex, captured, playerKey) {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';

        const captureText = captured > 0 ? ` +${captured}` : '';
        // Classe de badge selon le joueur (p1 ou p2)
        const badgeClass = playerKey === 'player1' ? 'badge-p1' : 'badge-p2';

        historyItem.innerHTML = `
            <span class="history-player ${badgeClass}">${playerName}</span>
            <span class="history-move">Case ${pitIndex + 1}</span>
            ${captured > 0 ? `<span class="history-capture">${captureText}</span>` : ''}
        `;
        
        const emptyMessage = this.moveHistoryContainer.querySelector('.empty-history');
        if (emptyMessage) {
            emptyMessage.remove();
        }
        
        this.moveHistoryContainer.appendChild(historyItem);
        this.moveHistoryContainer.scrollTop = this.moveHistoryContainer.scrollHeight;
    }

    clearHistory() {
        this.moveHistoryContainer.innerHTML = '<p class="empty-history">Aucun coup joué</p>';
    }

    // API Communication Methods

    async startGame() {
        const player1Name = document.getElementById('player1-name').value || 'Joueur 1';
        const player2Name = document.getElementById('player2-name').value || 'Joueur 2';
        const player1Type = document.getElementById('player1-type').value;
        const player2Type = document.getElementById('player2-type').value;
        const player1Level = document.getElementById('player1-algorithm').value;
        const player2Level = document.getElementById('player2-algorithm').value;
        
        this.players.player1 = {
            name: player1Name,
            type: player1Type,
            level: player1Type === 'ai' ? player1Level : null
        };
        this.players.player2 = {
            name: player2Name,
            type: player2Type,
            level: player2Type === 'ai' ? player2Level : null
        };
        
        this.updatePlayerLabels();
        this.updateStatus('Initialisation de la partie...');
        this.clearHistory();
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player1: {
                        name: player1Name,
                        type: player1Type,
                        level: player1Type === 'ai' ? player1Level : null
                    },
                    player2: {
                        name: player2Name,
                        type: player2Type,
                        level: player2Type === 'ai' ? player2Level : null
                    }
                })
            });

            const data = await response.json();
            this.gameState = data;

            this.renderGameState();
            this.updateStatus(`Tour de ${this.players[this.gameState.current_player].name}`);

            // Auto-play AI if both players are AI
            if (this.players.player1.type === 'ai' && this.players.player2.type === 'ai') {
                setTimeout(() => this.playAI(), 1000);
            }

        } catch (error) {
            console.error('Error starting game:', error);
            this.updateStatus('Erreur lors de l\'initialisation — le serveur est-il lancé ?');
        }
    }

    async sendMove(pitIndex) {
        if (!this.gameState || this.gameState.game_over) {
            this.updateStatus('Veuillez démarrer une nouvelle partie');
            return;
        }
        
        const currentPlayerKey = this.gameState.current_player;
        const currentPlayer = this.players[currentPlayerKey];
        
        if (currentPlayer.type === 'ai') {
            this.updateStatus(`C'est le tour de ${currentPlayer.name}`);
            return;
        }
        
        this.updateStatus('Envoi du coup...');
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/api/game/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    pit_index: pitIndex,
                    player: currentPlayerKey
                })
            });

            if (!response.ok) {
                const err = await response.json();
                this.updateStatus(`Coup invalide : ${err.detail}`);
                return;
            }

            const scoresBefore = this.gameState
                ? { ...this.gameState.scores }
                : { player1: 0, player2: 0 };

            // Anime le semis AVANT d'appliquer l'état final
            const seedCount = this.gameState.board[pitIndex];
            const boardSnapshot = [...this.gameState.board];
            const newState = await response.json();

            await this.animateSow(pitIndex, seedCount, boardSnapshot);

            this.gameState = newState;

            const captured = (this.gameState.scores[currentPlayerKey] || 0)
                           - (scoresBefore[currentPlayerKey] || 0);

            this.renderGameState();
            this.addToHistory(currentPlayer.name, pitIndex, captured, currentPlayerKey);

            if (this.gameState.game_over) return;

            const nextPlayer = this.players[this.gameState.current_player];
            this.updateStatus(`Tour de ${nextPlayer.name}`);

            // Auto-play AI if next player is AI
            if (nextPlayer.type === 'ai') {
                setTimeout(() => this.playAI(), 1000);
            }

        } catch (error) {
            console.error('Error sending move:', error);
            this.updateStatus('Erreur lors de l\'envoi du coup');
        }
    }

    async playAI() {
        if (!this.gameState || this.gameState.game_over) {
            this.updateStatus('Veuillez démarrer une nouvelle partie');
            return;
        }
        
        const currentPlayerKey = this.gameState.current_player;
        const currentPlayer = this.players[currentPlayerKey];
        
        if (currentPlayer.type !== 'ai') {
            this.updateStatus(`${currentPlayer.name} n'est pas une IA`);
            return;
        }
        
        this.updateStatus(`${currentPlayer.name} réfléchit...`);
        
        try {
            const scoresBefore = { ...this.gameState.scores };

            const response = await fetch(`${this.apiBaseUrl}/api/game/ai-move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    player: currentPlayerKey,
                    level: currentPlayer.level,
                    board: this.gameState.board
                })
            });

            if (!response.ok) {
                const err = await response.json();
                this.updateStatus(`Erreur IA : ${err.detail}`);
                return;
            }

            const data = await response.json();
            const pitIndex = data.telemetry.pit_played;

            // Anime le semis AVANT d'appliquer l'état final
            const seedCount = this.gameState.board[pitIndex];
            const boardSnapshot = [...this.gameState.board];

            await this.animateSow(pitIndex, seedCount, boardSnapshot);

            this.gameState = data.game_state;
            this.updateTelemetry(data.telemetry);

            const captured = (this.gameState.scores[currentPlayerKey] || 0)
                           - (scoresBefore[currentPlayerKey] || 0);

            this.renderGameState();
            this.addToHistory(currentPlayer.name, pitIndex, captured, currentPlayerKey);

            if (this.gameState.game_over) return;

            const nextPlayer = this.players[this.gameState.current_player];
            this.updateStatus(`Tour de ${nextPlayer.name}`);

            // Auto-play AI if next player is also AI
            if (nextPlayer.type === 'ai') {
                setTimeout(() => this.playAI(), 1000);
            }

        } catch (error) {
            console.error('Error playing AI move:', error);
            this.updateStatus('Erreur lors du coup de l\'IA');
        }
    }

    renderGameState() {
        if (!this.gameState) return;
        
        this.pits.forEach((pit, index) => {
            this.renderSeeds(pit, this.gameState.board[index]);
        });
        
        this.updateScores(this.gameState.scores.player1, this.gameState.scores.player2);
        
        if (this.gameState.game_over) {
            const winnerName = this.gameState.winner ? this.players[this.gameState.winner].name : 'Match nul';
            this.updateStatus(`Partie terminée ! ${winnerName} gagne !`);
        }
    }
}

// Initialize the game when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.awaleGame = new AwaleGame();
});