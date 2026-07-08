// Awalé AI Frontend - JavaScript Module
// This file handles UI interactions and REST API communication with the Python backend
// No game logic is implemented here - all game rules and AI are handled by the backend

class AwaleGame {
    constructor() {
        this.apiBaseUrl = 'http://localhost:8000'; // TODO: Update with actual backend URL
        this.gameState = null;
        this.players = {
            player1: { name: 'Joueur 1', type: 'human', algorithm: null },
            player2: { name: 'Joueur 2', type: 'human', algorithm: null }
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
    }

    handlePlayerTypeChange(playerKey, type) {
        const aiConfig = document.getElementById(`${playerKey}-ai-config`);
        const algorithmSelect = document.getElementById(`${playerKey}-algorithm`);
        
        this.players[playerKey].type = type;
        
        if (type === 'ai') {
            aiConfig.style.display = 'flex';
            this.players[playerKey].algorithm = algorithmSelect.value;
            this.updatePlayerLabels();
        } else {
            aiConfig.style.display = 'none';
            this.players[playerKey].algorithm = null;
            this.updatePlayerLabels();
        }
    }

    updatePlayerLabels() {
        const getDisplayName = (player) => {
            if (player.type === 'ai') {
                return player.algorithm ? `IA ${player.algorithm.charAt(0).toUpperCase() + player.algorithm.slice(1)}` : 'IA';
            }
            return player.name;
        };
        
        this.labelPlayer1.textContent = getDisplayName(this.players.player1);
        this.labelPlayer2.textContent = getDisplayName(this.players.player2);
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

    addToHistory(playerName, pitIndex, captured) {
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        
        const captureText = captured > 0 ? ` (+${captured})` : '';
        
        historyItem.innerHTML = `
            <span class="history-player">${playerName}</span>
            <span class="history-move">Case ${pitIndex + 1}${captureText}</span>
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
        const player1Algorithm = document.getElementById('player1-algorithm').value;
        const player2Algorithm = document.getElementById('player2-algorithm').value;
        
        this.players.player1 = {
            name: player1Name,
            type: player1Type,
            algorithm: player1Type === 'ai' ? player1Algorithm : null
        };
        this.players.player2 = {
            name: player2Name,
            type: player2Type,
            algorithm: player2Type === 'ai' ? player2Algorithm : null
        };
        
        this.updatePlayerLabels();
        this.updateStatus('Initialisation de la partie...');
        this.clearHistory();
        
        try {
            // TODO: Connect FastAPI endpoint
            // const response = await fetch(`${this.apiBaseUrl}/api/game/start`, {
            //     method: 'POST',
            //     headers: {
            //         'Content-Type': 'application/json',
            //     },
            //     body: JSON.stringify({
            //         player1: {
            //             name: player1Name,
            //             type: player1Type,
            //             algorithm: player1Type === 'ai' ? player1Algorithm : null
            //         },
            //         player2: {
            //             name: player2Name,
            //             type: player2Type,
            //             algorithm: player2Type === 'ai' ? player2Algorithm : null
            //         }
            //     })
            // });
            
            // const data = await response.json();
            // this.gameState = data;
            
            // Simulated response for testing
            this.gameState = {
                board: [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
                scores: { player1: 0, player2: 0 },
                granaries: { player1: 0, player2: 0 },
                current_player: 'player1',
                game_over: false,
                winner: null,
                move_history: []
            };
            
            this.renderGameState();
            this.updateStatus(`Tour de ${this.players[this.gameState.current_player].name}`);
            
            // Auto-play AI if both players are AI
            if (this.players.player1.type === 'ai' && this.players.player2.type === 'ai') {
                setTimeout(() => this.playAI(), 1000);
            }
            
        } catch (error) {
            console.error('Error starting game:', error);
            this.updateStatus('Erreur lors de l\'initialisation');
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
            // TODO: Connect FastAPI endpoint
            // const response = await fetch(`${this.apiBaseUrl}/api/game/move`, {
            //     method: 'POST',
            //     headers: {
            //         'Content-Type': 'application/json',
            //     },
            //     body: JSON.stringify({
            //         pit_index: pitIndex,
            //         player: currentPlayerKey
            //     })
            // });
            
            // const data = await response.json();
            // this.gameState = data;
            
            // Simulated response for testing
            const captured = Math.floor(Math.random() * 5);
            this.gameState.board[pitIndex] = 0;
            this.gameState.scores[currentPlayerKey] += captured;
            this.gameState.granaries[currentPlayerKey] += captured;
            this.gameState.current_player = currentPlayerKey === 'player1' ? 'player2' : 'player1';
            
            this.renderGameState();
            this.addToHistory(currentPlayer.name, pitIndex, captured);
            
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
            // TODO: Connect FastAPI endpoint
            // const response = await fetch(`${this.apiBaseUrl}/api/game/ai-move`, {
            //     method: 'POST',
            //     headers: {
            //         'Content-Type': 'application/json',
            //     },
            //     body: JSON.stringify({
            //         player: currentPlayerKey,
            //         algorithm: currentPlayer.algorithm,
            //         board: this.gameState.board
            //     })
            // });
            
            // const data = await response.json();
            // this.gameState = data.game_state;
            // this.updateTelemetry(data.telemetry);
            
            // Simulated response for testing
            const validPits = this.gameState.board
                .map((seeds, index) => seeds > 0 ? index : -1)
                .filter(index => index !== -1);
            
            const pitIndex = validPits[Math.floor(Math.random() * validPits.length)];
            const captured = Math.floor(Math.random() * 5);
            
            this.gameState.board[pitIndex] = 0;
            this.gameState.scores[currentPlayerKey] += captured;
            this.gameState.granaries[currentPlayerKey] += captured;
            this.gameState.current_player = currentPlayerKey === 'player1' ? 'player2' : 'player1';
            
            // Simulated telemetry
            this.updateTelemetry({
                computation_time: Math.floor(Math.random() * 500) + 50,
                depth: Math.floor(Math.random() * 10) + 3,
                nodes_explored: Math.floor(Math.random() * 10000) + 1000,
                win_rate: 0.5 + Math.random() * 0.3
            });
            
            this.renderGameState();
            this.addToHistory(currentPlayer.name, pitIndex, captured);
            
            const nextPlayer = this.players[this.gameState.current_player];
            this.updateStatus(`Tour de ${nextPlayer.name}`);
            
            // Auto-play AI if next player is also AI
            if (nextPlayer.type === 'ai' && !this.gameState.game_over) {
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
