/* Bracket victory "juice" for the public kiosk view.
 *
 * When a match gains a winner between two bracket snapshots, the freshly-decided
 * winner slot pops/flashes and a short radial particle burst fires over it. The
 * champion (final match) gets a bigger flourish that leads straight into the
 * existing celebration podium.
 *
 * Observes from OUTSIDE bracket-view.js (no edits there): view.html computes the
 * diff in its bracket_update handler BEFORE the re-render, then schedules the
 * visuals to land AFTER the FLIP re-seed flight settles.
 *
 * TIMING: flip.js animates re-seed flights for ~2000ms (its DURATION). The real
 * winner slot is hidden under a flying clone until then, so the pop/burst must
 * wait until flights settle. FLIP_SETTLE below MUST stay >= flip.js DURATION.
 *
 * Self-contained vanilla JS + <canvas>; exposes window.BracketJuice. The burst
 * particle math mirrors celebration.js's explode(). Respects prefers-reduced-
 * motion (no burst, no scale-pop; a static highlight + immediate celebration).
 */
(function () {
    const reduceMotion =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const FLIP_SETTLE = 2100;   // ms; must be >= flip.js DURATION (2000)
    const FLOURISH_MS = 1200;   // champion flourish before the celebration podium
    const MAX_BURSTS = 6;       // cap simultaneous bursts (bye cascades)
    const GOLD = "#fbbf24";

    let prevWinners = new Map(); // match_id -> winner user_id (last seen)
    let enabled = true;          // admin effects toggle
    let canvas = null;
    let ctx = null;
    let sparks = [];
    let rafId = null;
    let running = false;
    let lastTs = null;

    // --- winner extraction / completeness ---------------------------------

    function winnersOf(bracket) {
        const m = new Map();
        if (!bracket || !bracket.rounds) return m;
        for (const round of bracket.rounds) {
            for (const mt of round.matches || []) {
                if (mt.hidden) continue; // padding match — no burst over a hidden box
                const w = mt.winner || mt.auto_winner;
                if (w) m.set(mt.match_id, w.user_id);
            }
        }
        const tpm = bracket.third_place_match;
        if (tpm) {
            const w = tpm.winner || tpm.auto_winner;
            if (w) m.set(tpm.match_id, w.user_id);
        }
        return m;
    }

    function finalMatchId(bracket) {
        if (!bracket || !bracket.rounds || !bracket.rounds.length) return null;
        const fr = bracket.rounds[bracket.rounds.length - 1];
        const champ = fr && fr.matches && fr.matches[0];
        return champ ? champ.match_id : null;
    }

    // Mirrors celebration.js readPodium: champion + runner-up + third all set.
    function isComplete(bracket) {
        if (!bracket || !bracket.rounds || !bracket.rounds.length) return false;
        const fr = bracket.rounds[bracket.rounds.length - 1];
        const champ = fr && fr.matches && fr.matches[0];
        if (!champ) return false;
        const winner = champ.winner || champ.auto_winner;
        if (!winner) return false;
        let runnerUp = null;
        if (champ.player1 && champ.player1.user_id === winner.user_id) runnerUp = champ.player2;
        else if (champ.player2 && champ.player2.user_id === winner.user_id) runnerUp = champ.player1;
        const tpm = bracket.third_place_match;
        const third = tpm && (tpm.winner || tpm.auto_winner);
        return !!(runnerUp && third);
    }

    // --- diff: which matches newly decided since the previous snapshot -----

    function observeInit(bracket) {
        prevWinners = winnersOf(bracket);
    }

    function diffAndSchedule(prevBracket, nextBracket) {
        // Prefer our tracked baseline (survives across calls); fall back to the
        // passed-in prev for safety.
        const before = prevWinners.size ? prevWinners : winnersOf(prevBracket);
        const after = winnersOf(nextBracket);
        const newlyDecided = [];
        for (const [matchId, userId] of after) {
            const had = before.get(matchId);
            if (had == null) newlyDecided.push({ matchId, userId }); // none -> someone
        }
        prevWinners = after;
        const finalId = finalMatchId(nextBracket);
        const champion = newlyDecided.some((d) => d.matchId === finalId);
        return { newlyDecided, champion, championMatchId: champion ? finalId : null };
    }

    // --- visuals -----------------------------------------------------------

    function ensureCanvas() {
        if (canvas) return;
        let layer = document.getElementById("juice-layer");
        if (!layer) {
            layer = document.createElement("div");
            layer.id = "juice-layer";
            document.body.appendChild(layer);
        }
        canvas = document.createElement("canvas");
        canvas.className = "juice-canvas";
        layer.appendChild(canvas);
        ctx = canvas.getContext("2d");
        resizeCanvas();
        window.addEventListener("resize", resizeCanvas);
    }
    function resizeCanvas() {
        if (!canvas) return;
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function slotFor(matchId) {
        return document.querySelector(
            '#bracket .match[data-match-id="' + cssEscape(matchId) + '"] .slot.winner'
        );
    }
    function cssEscape(s) {
        if (window.CSS && CSS.escape) return CSS.escape(s);
        return String(s).replace(/["\\]/g, "\\$&");
    }

    function popSlot(slot, champion) {
        if (!slot) return;
        if (reduceMotion) {
            slot.classList.add("slot-juice-static");
            setTimeout(() => slot.classList.remove("slot-juice-static"), 1500);
            return;
        }
        const cls = champion ? "slot-juice-champ" : "slot-juice-pop";
        slot.classList.remove(cls);
        void slot.offsetWidth; // restart the animation if re-applied
        slot.classList.add(cls);
        slot.addEventListener(
            "animationend",
            () => slot.classList.remove(cls),
            { once: true }
        );
    }

    function burstAt(x, y, n) {
        for (let i = 0; i < n; i++) {
            const ang = (Math.PI * 2 * i) / n + (Math.random() - 0.5) * 0.2;
            const speed = 90 + Math.random() * 170;
            sparks.push({
                x, y,
                vx: Math.cos(ang) * speed,
                vy: Math.sin(ang) * speed,
                life: 1,
                color: Math.random() < 0.3 ? "#ffffff" : GOLD,
            });
        }
        startAnim();
    }

    function startAnim() {
        if (running) return;
        running = true;
        lastTs = null;
        rafId = requestAnimationFrame(frame);
    }

    function frame(ts) {
        if (lastTs == null) lastTs = ts;
        let dt = (ts - lastTs) / 1000;
        lastTs = ts;
        if (dt > 0.05) dt = 0.05;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let i = sparks.length - 1; i >= 0; i--) {
            const s = sparks[i];
            s.vy += 150 * dt; // gravity
            s.x += s.vx * dt;
            s.y += s.vy * dt;
            s.life -= dt * 0.9;
            if (s.life <= 0) { sparks.splice(i, 1); continue; }
            ctx.save();
            ctx.globalAlpha = Math.max(0, s.life);
            ctx.fillStyle = s.color;
            ctx.beginPath();
            ctx.arc(s.x, s.y, 2.6, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }
        if (sparks.length) {
            rafId = requestAnimationFrame(frame);
        } else {
            running = false;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    function fireOne(matchId, champion) {
        const slot = slotFor(matchId);
        popSlot(slot, champion);
        if (reduceMotion || !slot) return;
        const r = slot.getBoundingClientRect();
        burstAt(r.left + r.width / 2, r.top + r.height / 2, champion ? 48 : 30);
    }

    /* Schedule the juice after the FLIP flight settles. When `champion` is true,
     * `doneCb` (the celebration trigger) runs AFTER the flourish so the podium
     * leads out of the crowning moment instead of stepping on it. */
    function fireAfterFlip(newly, champion, doneCb) {
        // Effects off: skip all visuals, but STILL run the celebration callback
        // immediately so the (separately-toggled) podium isn't blocked. The
        // win/baseline diff in diffAndSchedule keeps running regardless, so no
        // stale events fire when effects are switched back on.
        if (!enabled) {
            if (champion && doneCb) doneCb();
            return;
        }
        ensureCanvas();
        const matches = (newly && newly.newlyDecided) || [];
        // Prioritise later-round matches; cap the count for bye cascades.
        const ordered = matches.slice().reverse().slice(0, MAX_BURSTS);

        const champMatchId = newly && newly.championMatchId;
        const settle = reduceMotion ? 0 : FLIP_SETTLE;
        setTimeout(() => {
            for (const d of ordered) {
                fireOne(d.matchId, champion && d.matchId === champMatchId);
            }
            if (champion && doneCb) {
                // Let the flourish play, then bring on the celebration podium.
                setTimeout(doneCb, reduceMotion ? 0 : FLOURISH_MS);
            }
        }, settle);
    }

    // Admin effects toggle. When off, fireAfterFlip skips visuals (above) and any
    // in-flight burst is cleared; the diff baseline keeps tracking either way.
    function setEnabled(on) {
        enabled = !!on;
        if (!enabled) {
            sparks = [];
            running = false;
            if (rafId != null) cancelAnimationFrame(rafId);
            rafId = null;
            if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }

    window.BracketJuice = {
        observeInit,
        diffAndSchedule,
        isComplete,
        fireAfterFlip,
        setEnabled,
    };
})();
