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

for (const kind of ['human', 'ai']) {
    for (const invalid of ['other game', 'old version', 'skipped version']) {
        test(`${kind} ignores a response for ${invalid}`, async () => {
            const { context, game } = setup();
            game.players.player1.type = kind;
            game.players.player1.agent = 'minimax';
            game.players.player1.depth = 2;
            const before = game.gameState;
            const next = { ...before, version: invalid === 'old version' ? 2
                : invalid === 'skipped version' ? 5 : 4,
                game_id: invalid === 'other game' ? 'game-b' : before.game_id,
                scores: { player1: 12, player2: 9 }, current_player: 'player2' };
            let animated = false;
            game.animateSow = async () => { animated = true; };
            context.fetch = async () => ({ ok: true, json: async () => kind === 'ai'
                ? { game_state: next, telemetry: { pit_played: 0 } } : next });
            await (kind === 'ai' ? game.playAI() : game.sendMove(0));
            assert.equal(game.gameState, before);
            assert.equal(game.renders, undefined);
            assert.equal(animated, false);
            assert.equal(game._busy, false);
        });
    }

    test(`${kind} does not replace a newer state after animation`, async () => {
        const { context, game } = setup();
        game.players.player1.type = kind;
        game.players.player1.agent = 'random';
        const next = { ...game.gameState, version: 4, current_player: 'player2' };
        const newer = { ...next, version: 5, scores: { player1: 2, player2: 3 } };
        context.fetch = async () => ({ ok: true, json: async () => kind === 'ai'
            ? { game_state: next, telemetry: { pit_played: 0 } } : next });
        game.animateSow = async () => { game.gameState = newer; };
        await (kind === 'ai' ? game.playAI() : game.sendMove(0));
        assert.equal(game.gameState, newer);
        assert.equal(game.renders, undefined);
        assert.equal(game._busy, false);
    });
}

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
    const state = { ...game.gameState, game_id: '19f64771-4989-4672-9bc1-76a27ac437a8', version: 0 };
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
    const state = { ...game.gameState, game_id: '19f64771-4989-4672-9bc1-76a27ac437a8', version: 0 };
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

test('AI request sends its own id, version, board and parameters without cache', async () => {
    const { context, game } = setup();
    Object.assign(game.players.player1, {type: 'ai', agent: 'alphabeta', depth: 2});
    let payload, cache;
    context.fetch = async (_, options) => {
        payload = JSON.parse(options.body);
        cache = options.cache;
        return {ok: true, json: async () => ({game_state: {...game.gameState, version: 4,
            current_player: 'player2'}, telemetry: {pit_played: 0}})};
    };
    await game.playAI();
    assert.deepEqual(payload, {game_id: 'game-a', version: 3, player: 'player1',
        agent: 'alphabeta', depth: 2, board: Array(12).fill(4)});
    assert.equal(cache, 'no-store');
});

test('a delayed start response cannot replace a newer game', async () => {
    const {context, game} = setup();
    const oldState = {...game.gameState, game_id: '19f64771-4989-4672-9bc1-76a27ac437a8', version: 0};
    const newState = {...oldState, game_id: 'ab47cb6e-a3ec-4e14-a345-27ead7fdbba7'};
    let finish;
    context.fetch = () => new Promise(resolve => {finish = resolve;});
    const oldStart = game.startGame();
    const finishOld = finish;
    const newStart = game.startGame();
    finish({ok: true, json: async () => newState});
    await newStart;
    finishOld({ok: true, json: async () => oldState});
    await oldStart;
    assert.equal(game.gameState, newState);
    assert.equal(game.renders, 1);
});

test('start refuses an invalid id or a reused id', async () => {
    for (const id of [null, 'broken', '19f64771-4989-4672-9bc1-76a27ac437a8']) {
        const {context, game} = setup();
        game.gameState.game_id = '19f64771-4989-4672-9bc1-76a27ac437a8';
        const state = {...game.gameState, game_id: id, version: 0};
        context.fetch = async () => ({ok: true, json: async () => state});
        await game.startGame();
        assert.equal(game.gameState, null);
        assert.equal(game.renders, undefined);
        assert.equal(game._busy, false);
    }
});

test('two independent frontend clients apply only their own responses', async () => {
    const a = setup(), b = setup();
    b.game.gameState.game_id = 'game-b';
    let finishA, finishB;
    a.context.fetch = () => new Promise(resolve => {finishA = resolve;});
    b.context.fetch = () => new Promise(resolve => {finishB = resolve;});
    const nextA = {...a.game.gameState, version: 4, current_player: 'player2', scores: {player1: 2, player2: 0}};
    const nextB = {...b.game.gameState, version: 4, current_player: 'player2', scores: {player1: 0, player2: 3}};
    const moves = [a.game.sendMove(0), b.game.sendMove(0)];
    finishB({ok: true, json: async () => nextB});
    await moves[1];
    assert.equal(a.game.gameState.version, 3);
    finishA({ok: true, json: async () => nextA});
    await moves[0];
    assert.equal(a.game.gameState, nextA);
    assert.equal(b.game.gameState, nextB);
});

for (const kind of ['human', 'ai']) {
    test(`${kind} reloads its own game after a version conflict`, async () => {
        const {context, game} = setup();
        Object.assign(game.players.player1, {type: kind, agent: 'minimax', depth: 2});
        const latest = {...game.gameState, version: 4, current_player: 'player2',
            scores: {player1: 2, player2: 0}, valid_moves: [6]};
        const requests = [];
        let animated = false;
        game.animateSow = async () => {animated = true;};
        context.fetch = async (url, options) => {
            requests.push({url, options});
            return requests.length === 1
                ? {ok: false, status: 409, json: async () => ({detail: 'Version conflict'})}
                : {ok: true, json: async () => latest};
        };
        await (kind === 'ai' ? game.playAI() : game.sendMove(0));
        assert.equal(requests.length, 2);
        assert.equal(requests[1].url, `${game.apiBaseUrl}/api/game/game-a`);
        assert.equal(requests[1].options.cache, 'no-store');
        assert.equal(game.gameState, latest);
        assert.equal(animated, false);
        assert.equal(game._busy, false);
    });
}

test('the next move after a conflict uses the refreshed version and player', async () => {
    const {context, game} = setup();
    const refreshed = {...game.gameState, version: 4, current_player: 'player2', valid_moves: [6]};
    const requests = [];
    context.fetch = async (_, options) => {
        requests.push(options);
        if (requests.length === 1) return {ok: false, status: 409, json: async () => ({detail: 'Conflict'})};
        if (requests.length === 2) return {ok: true, json: async () => refreshed};
        return {ok: true, json: async () => ({...refreshed, version: 5, current_player: 'player1'})};
    };
    await game.sendMove(0);
    await game.sendMove(6);
    const payload = JSON.parse(requests[2].body);
    assert.equal(payload.version, 4);
    assert.equal(payload.player, 'player2');
    assert.equal(payload.game_id, 'game-a');
    assert.equal(game.gameState.version, 5);
});

for (const invalid of ['other game', 'old version', 'HTTP error']) {
    test(`conflict refresh rejects ${invalid}`, async () => {
        const {context, game} = setup();
        const before = game.gameState;
        const latest = {...before, game_id: invalid === 'other game' ? 'game-b' : 'game-a',
            version: invalid === 'old version' ? 2 : 4};
        let calls = 0;
        context.fetch = async () => ++calls === 1
            ? {ok: false, status: 409, json: async () => ({detail: 'Conflict'})}
            : {ok: invalid !== 'HTTP error', json: async () => latest};
        await game.sendMove(0);
        assert.equal(game.gameState, before);
        assert.equal(game.renders, undefined);
        assert.equal(game._busy, false);
    });
}

for (const change of ['new game', 'new version']) {
    test(`delayed conflict refresh cannot overwrite a ${change}`, async () => {
        const {context, game} = setup();
        const refreshed = {...game.gameState, version: 4};
        let finish, entered;
        const refreshing = new Promise(resolve => {entered = resolve;});
        let calls = 0;
        context.fetch = () => {
            if (++calls === 1) return Promise.resolve({ok: false, status: 409,
                json: async () => ({detail: 'Conflict'})});
            entered();
            return new Promise(resolve => {finish = resolve;});
        };
        const move = game.sendMove(0);
        await refreshing;
        if (change === 'new game') game.resetGame();
        const newer = {...refreshed, game_id: change === 'new game' ? 'game-b' : 'game-a', version: 5};
        game.gameState = newer;
        if (change === 'new game') game._busy = true;
        finish({ok: true, json: async () => refreshed});
        await move;
        assert.equal(game.gameState, newer);
        assert.equal(game.renders, undefined);
        assert.equal(game._busy, change === 'new game');
    });
}

test('AI resumes after conflict refresh and its scheduled turn expires on stop', async () => {
    for (const stop of [false, true]) {
        const {context, game, timers} = setup();
        game.players.player2.type = 'ai';
        const refreshed = {...game.gameState, version: 4, current_player: 'player2', valid_moves: [6]};
        let calls = 0, plays = 0;
        context.fetch = async () => ++calls === 1
            ? {ok: false, status: 409, json: async () => ({detail: 'Conflict'})}
            : {ok: true, json: async () => refreshed};
        game.playAI = () => {plays++;};
        await game.sendMove(0);
        if (stop) game.resetGame();
        timers.forEach(fn => fn());
        assert.equal(plays, stop ? 0 : 1);
    }
});
