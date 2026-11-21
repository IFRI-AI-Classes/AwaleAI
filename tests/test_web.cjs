const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup() {
    const timers = [];
    const inputs = {
        'player1-name': 'IA', 'player2-name': 'Humain',
        'player1-type': 'ai', 'player2-type': 'human',
        'player1-agent': 'minimax', 'player2-agent': 'minimax',
        'player1-depth': '2', 'player2-depth': '2',
    };
    const context = vm.createContext({
        AbortController, console, confirm: () => true,
        setTimeout: fn => timers.push(fn),
        document: {
            addEventListener() {}, querySelector: () => null,
            getElementById: id => ({ value: inputs[id] }),
        },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8') + '\nglobalThis.GameClass = AwaleGame;', context);
    const game = Object.create(context.GameClass.prototype);
    Object.assign(game, {
        _generation: 0, _abortController: new AbortController(), _busy: false,
        gameState: { game_id: 'game-a', version: 3, current_player: 'player1',
            board: [4,4,4,4,4,4,4,4,4,4,4,4], scores: { player1: 0, player2: 0 }, valid_moves: [0], game_over: false },
        players: { player1: { name: 'A', type: 'human' }, player2: { name: 'B', type: 'human' } },
        pits: [], btnNewGame: {}, btnStop: {}, _granaryCache: [],
        _setBusy(value) { this._busy = value; },
        _clearHighlights() {}, updateStatus() {}, setStatus() {}, showToast() {},
        updatePlayerLabels() {}, clearHistory() {}, renderInitialBoard() {}, updateScores() {},
        _closeModal() {}, _highlightValidMoves() {}, addToHistory() {}, updateTelemetry() {},
        _findCapturedCells: () => [], animateSow: async () => {},
        renderGameState() { this.renders = (this.renders || 0) + 1; },
    });
    return { context, game, timers };
}

test('human request sends game id and version', async () => {
    const { context, game } = setup();
    let payload;
    context.fetch = async (_, options) => {
        payload = JSON.parse(options.body);
        return { ok: true, json: async () => ({ ...game.gameState, version: 4, current_player: 'player2' }) };
    };
    await game.sendMove(0);
    assert.equal(payload.game_id, 'game-a');
    assert.equal(payload.version, 3);
    assert.equal(game.gameState.version, 4);
});

test('stopping a game ignores its delayed response', async () => {
    const { context, game } = setup();
    const responseState = { ...game.gameState, version: 4 };
    let finish;
    let signal;
    context.fetch = (_, options) => {
        signal = options.signal;
        return new Promise(resolve => { finish = resolve; });
    };
    const request = game.sendMove(0);
    game.resetGame();
    finish({ ok: true, json: async () => responseState });
    await request;
    assert.equal(signal.aborted, true);
    assert.equal(game.gameState, null);
    assert.equal(game.renders, undefined);
});

test('stopping during animation cannot restore the old game', async () => {
    const { context, game } = setup();
    const responseState = { ...game.gameState, version: 4 };
    let finish;
    let entered;
    const animating = new Promise(resolve => { entered = resolve; });
    context.fetch = async () => ({ ok: true, json: async () => responseState });
    game.animateSow = () => { entered(); return new Promise(resolve => { finish = resolve; }); };
    const request = game.sendMove(0);
    await animating;
    game.resetGame();
    finish();
    await request;
    assert.equal(game.gameState, null);
    assert.equal(game.renders, undefined);
});

test('AI starts when the first player is AI and the other is human', async () => {
    const { context, game, timers } = setup();
    const state = { ...game.gameState, game_id: 'new-game', version: 0 };
    context.fetch = async () => ({ ok: true, json: async () => state });
    let plays = 0;
    game.playAI = () => { plays++; };
    await game.startGame();
    timers.forEach(fn => fn());
    assert.equal(plays, 1);
    assert.equal(game._busy, false);
});

test('scheduled AI turn is discarded after stop', async () => {
    const { context, game, timers } = setup();
    const state = { ...game.gameState, game_id: 'new-game', version: 0 };
    context.fetch = async () => ({ ok: true, json: async () => state });
    let plays = 0;
    game.playAI = () => { plays++; };
    await game.startGame();
    game.resetGame();
    timers.forEach(fn => fn());
    assert.equal(plays, 0);
    assert.equal(game.btnNewGame.disabled, false);
});

for (const kind of ['human', 'ai']) {
    test(`${kind} terminal moves retain captures and exclude blockade leftovers`, async () => {
        const cases = [
            {
                hole: 11, player: 'player2', scores: { player1: 18, player2: 23 },
                board: [1,0,1,0,0,0,1,2,0,0,1,1],
                nextBoard: [0,0,1,0,0,0,1,2,0,0,1,0],
                nextScores: { player1: 18, player2: 25 }, reason: 'score', expected: 2,
            },
            {
                hole: 0, player: 'player1', scores: { player1: 23, player2: 24 },
                board: [1,0,0,0,0,0,0,0,0,0,0,0],
                nextBoard: [0,1,0,0,0,0,0,0,0,0,0,0],
                nextScores: { player1: 24, player2: 24 }, reason: 'blocage', expected: 0,
            },
        ];
        for (const position of cases) {
            const { context, game } = setup();
            game.gameState = { ...game.gameState, board: position.board, scores: position.scores,
                current_player: position.player, valid_moves: [position.hole], game_over: false };
            game.players[position.player].type = kind;
            game.players[position.player].agent = 'alphabeta';
            game.players[position.player].depth = 2;
            const next = { ...game.gameState, version: 4, board: position.nextBoard,
                scores: position.nextScores, game_over: true, valid_moves: [], end_reason: position.reason };
            let displayedCapture;
            game.addToHistory = (_name, _hole, captured) => { displayedCapture = captured; };
            context.fetch = async () => ({ ok: true, json: async () => kind === 'ai'
                ? { game_state: next, telemetry: { pit_played: position.hole } } : next });
            await (kind === 'ai' ? game.playAI() : game.sendMove(position.hole));
            assert.equal(displayedCapture, position.expected, `${kind}: ${position.reason}`);
            assert.equal(game._busy, false);
        }
    });
}

test('seed layouts preserve every grain, stay inside the circle and never overlap', () => {
    const context = vm.createContext({document: {addEventListener() {}}});
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
        + '\nglobalThis.layout = seedLayout;', context);
    for (let count = 0; count <= 48; count++) {
        const points = context.layout(count);
        assert.equal(points.length, count);
        if (!count) continue;
        const centroid = points.reduce((c,p)=>({x:c.x+p.x,y:c.y+p.y}),{x:0,y:0});
        assert.ok(Math.abs(centroid.x / count - 50) < 1e-8);
        assert.ok(Math.abs(centroid.y / count - 50) < 1e-8);
        for (let i = 0; i < points.length; i++) {
            const p = points[i];
            assert.ok(p.size > 0);
            assert.ok(Math.hypot(p.x - 50, p.y - 50) + p.size / 2 <= 45 + 1e-8, `count ${count}, grain ${i} escapes`);
            for (let j = 0; j < i; j++) {
                const q = points[j];
                assert.ok(Math.hypot(p.x-q.x,p.y-q.y) > (p.size+q.size)/2, `count ${count}, grains ${i}/${j} overlap`);
            }
        }
    }
});
