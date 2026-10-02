/* Tournament-finish celebration overlay for the public kiosk view.
 *
 * Shows a big centered winners' podium (Stockerl: 🥇 highest in the middle, 🥈
 * left, 🥉 right) with a full-screen canvas of falling confetti and rockets that
 * launch from the bottom and explode into radial bursts.
 *
 * Self-contained vanilla JS + <canvas> (no external library) so the kiosk works
 * offline. Exposes window.Celebration.
 *
 * Trigger model (see plan): the effect is visible when the tournament is COMPLETE
 * (champion + runner-up + third all decided) AND the admin has it enabled. The
 * view calls Celebration.evaluate(bracket, enabled) on every bracket/celebration
 * update; this module derives completeness from the bracket the same way the
 * podium renderer does, then shows/hides itself accordingly.
 *
 * Respects prefers-reduced-motion: the podium still appears, but without the
 * animated confetti/rocket particles.
 */
(function () {
    const reduceMotion =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const CONFETTI_COLORS = [
        "#fbbf24", "#f59e0b", "#4dd2ff", "#46e07a",
        "#ff5d6c", "#c084fc", "#ffffff", "#fde68a",
    ];

    let layer = null; // #celebration-layer
    let podiumEl = null; // the centered podium block
    let canvas = null;
    let ctx = null;
    let rafId = null;
    let running = false; // animation loop active
    let shown = false; // overlay currently visible
    let lastKey = null; // identity of the currently-shown podium (champion/runner/third)

    let confetti = [];
    let rockets = [];
    let sparks = [];
    let lastTs = null;
    let rocketTimer = 0;

    // --- DOM construction (lazy, once) ------------------------------------

    function ensureDom() {
        if (layer) return;
        layer = document.getElementById("celebration-layer");
        if (!layer) {
            layer = document.createElement("div");
            layer.id = "celebration-layer";
            document.body.appendChild(layer);
        }
        canvas = document.createElement("canvas");
        canvas.className = "celebration-canvas";
        layer.appendChild(canvas);
        ctx = canvas.getContext("2d");

        podiumEl = document.createElement("div");
        podiumEl.className = "celebration-podium";
        layer.appendChild(podiumEl);

        layer.classList.add("hidden");
        window.addEventListener("resize", resizeCanvas);
    }

    function resizeCanvas() {
        if (!canvas) return;
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    // --- Tournament completeness (mirrors bracket-view.js renderPodium) ----

    function readPodium(bracket) {
        if (!bracket || !bracket.rounds || !bracket.rounds.length) return null;
        const finalRound = bracket.rounds[bracket.rounds.length - 1];
        const champ = finalRound && finalRound.matches && finalRound.matches[0];
        if (!champ) return null;
        const winner = champ.winner || champ.auto_winner;
        if (!winner) return null;
        let runnerUp = null;
        if (champ.player1 && champ.player1.user_id === winner.user_id) runnerUp = champ.player2;
        else if (champ.player2 && champ.player2.user_id === winner.user_id) runnerUp = champ.player1;
        const tpm = bracket.third_place_match;
        const third = tpm && (tpm.winner || tpm.auto_winner);
        if (!runnerUp || !third) return null; // not fully decided yet
        return { winner, runnerUp, third };
    }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s ?? "";
        return d.innerHTML;
    }

    function podiumKey(p) {
        return [p.winner.user_id, p.runnerUp.user_id, p.third.user_id].join("-");
    }

    // --- Public entry: decide whether to show or hide ----------------------

    function evaluate(bracket, enabled) {
        ensureDom();
        const podium = enabled ? readPodium(bracket) : null;
        if (podium) {
            show(podium);
        } else {
            hide();
        }
    }

    function show(podium) {
        const key = podiumKey(podium);
        if (shown && key === lastKey) return; // already showing these winners
        lastKey = key;
        shown = true;

        const fmtScore = (p) => (p.highscore ?? 0).toLocaleString("en-US");
        // Order on screen: silver (left), gold (middle, tallest), bronze (right).
        podiumEl.innerHTML = `
            <div class="cp-title">CLASSIC TETRIS</br>RETROVERSE CHAMPIONS</div>
            <div class="cp-stage">
                <div class="cp-place cp-silver">
                    <div class="cp-medal"><img class="tw-icon" src="/kiosk/static/icons/medal-silver.svg" alt=""></div>
                    <div class="cp-name">${esc(podium.runnerUp.nickname)}</div>
                    <div class="cp-score">${fmtScore(podium.runnerUp)}</div>
                    <div class="cp-block"><span class="cp-rank">2</span></div>
                </div>
                <div class="cp-place cp-gold">
                    <div class="cp-crown"><img class="tw-icon" src="/kiosk/static/icons/crown.svg" alt=""></div>
                    <div class="cp-medal"><img class="tw-icon" src="/kiosk/static/icons/medal-gold.svg" alt=""></div>
                    <div class="cp-name">${esc(podium.winner.nickname)}</div>
                    <div class="cp-score">${fmtScore(podium.winner)}</div>
                    <div class="cp-block"><span class="cp-rank">1</span></div>
                </div>
                <div class="cp-place cp-bronze">
                    <div class="cp-medal"><img class="tw-icon" src="/kiosk/static/icons/medal-bronze.svg" alt=""></div>
                    <div class="cp-name">${esc(podium.third.nickname)}</div>
                    <div class="cp-score">${fmtScore(podium.third)}</div>
                    <div class="cp-block"><span class="cp-rank">3</span></div>
                </div>
            </div>
        `;
        // Restart the entrance animation.
        podiumEl.classList.remove("cp-enter");
        // force reflow so re-adding the class re-triggers the animation
        void podiumEl.offsetWidth;
        podiumEl.classList.add("cp-enter");

        layer.classList.remove("hidden");
        if (!reduceMotion) startAnim();
    }

    function hide() {
        if (!shown) return;
        shown = false;
        lastKey = null;
        if (layer) layer.classList.add("hidden");
        stopAnim();
        confetti = [];
        rockets = [];
        sparks = [];
    }

    // --- Particle animation -----------------------------------------------

    function startAnim() {
        if (running) return;
        running = true;
        resizeCanvas();
        lastTs = null;
        rocketTimer = 0;
        // Seed an initial burst of confetti.
        for (let i = 0; i < 120; i++) confetti.push(spawnConfetti(true));
        rafId = requestAnimationFrame(frame);
    }

    function stopAnim() {
        running = false;
        if (rafId != null) cancelAnimationFrame(rafId);
        rafId = null;
        if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    function rand(a, b) {
        // No Math.random ban here (browser side); vary freely.
        return a + Math.random() * (b - a);
    }

    function spawnConfetti(initial) {
        const w = canvas.width;
        const h = canvas.height;
        return {
            x: rand(0, w),
            y: initial ? rand(-h, 0) : rand(-40, -10),
            size: rand(6, 12),
            color: CONFETTI_COLORS[(Math.random() * CONFETTI_COLORS.length) | 0],
            vx: rand(-30, 30),
            vy: rand(60, 160),
            rot: rand(0, Math.PI * 2),
            vrot: rand(-6, 6),
            sway: rand(0.5, 2),
            phase: rand(0, Math.PI * 2),
        };
    }

    function spawnRocket() {
        const w = canvas.width;
        const h = canvas.height;
        const targetY = rand(h * 0.12, h * 0.45);
        const x = rand(w * 0.15, w * 0.85);
        return {
            x,
            y: h + 10,
            targetY,
            vy: rand(-560, -440),
            color: CONFETTI_COLORS[(Math.random() * CONFETTI_COLORS.length) | 0],
        };
    }

    function explode(x, y, color) {
        const n = 36;
        for (let i = 0; i < n; i++) {
            const ang = (Math.PI * 2 * i) / n + rand(-0.1, 0.1);
            const speed = rand(80, 240);
            sparks.push({
                x, y,
                vx: Math.cos(ang) * speed,
                vy: Math.sin(ang) * speed,
                life: 1,
                color: Math.random() < 0.3 ? "#ffffff" : color,
            });
        }
    }

    function frame(ts) {
        if (!running) return;
        rafId = requestAnimationFrame(frame);
        if (lastTs == null) lastTs = ts;
        let dt = (ts - lastTs) / 1000;
        lastTs = ts;
        if (dt > 0.05) dt = 0.05; // clamp after a tab stall
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        // Confetti: keep a steady population while running.
        if (confetti.length < 160 && Math.random() < 0.9) confetti.push(spawnConfetti(false));
        for (let i = confetti.length - 1; i >= 0; i--) {
            const c = confetti[i];
            c.phase += dt * c.sway;
            c.x += (c.vx + Math.cos(c.phase) * 20) * dt;
            c.y += c.vy * dt;
            c.rot += c.vrot * dt;
            if (c.y > h + 20) { confetti.splice(i, 1); continue; }
            ctx.save();
            ctx.translate(c.x, c.y);
            ctx.rotate(c.rot);
            ctx.fillStyle = c.color;
            ctx.fillRect(-c.size / 2, -c.size / 2, c.size, c.size * 0.6);
            ctx.restore();
        }

        // Rockets: launch one periodically.
        rocketTimer -= dt;
        if (rocketTimer <= 0) {
            rockets.push(spawnRocket());
            rocketTimer = rand(0.35, 0.9);
        }
        for (let i = rockets.length - 1; i >= 0; i--) {
            const r = rockets[i];
            r.y += r.vy * dt;
            // Trail.
            ctx.save();
            ctx.globalAlpha = 0.9;
            ctx.fillStyle = r.color;
            ctx.beginPath();
            ctx.arc(r.x, r.y, 3, 0, Math.PI * 2);
            ctx.fill();
            ctx.globalAlpha = 0.3;
            ctx.fillRect(r.x - 1.5, r.y, 3, 16);
            ctx.restore();
            if (r.y <= r.targetY) {
                explode(r.x, r.y, r.color);
                rockets.splice(i, 1);
            }
        }

        // Sparks from explosions (gravity + fade).
        for (let i = sparks.length - 1; i >= 0; i--) {
            const s = sparks[i];
            s.vy += 140 * dt; // gravity
            s.x += s.vx * dt;
            s.y += s.vy * dt;
            s.life -= dt * 0.8;
            if (s.life <= 0) { sparks.splice(i, 1); continue; }
            ctx.save();
            ctx.globalAlpha = Math.max(0, s.life);
            ctx.fillStyle = s.color;
            ctx.beginPath();
            ctx.arc(s.x, s.y, 2.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }
    }

    window.Celebration = { evaluate };
})();
