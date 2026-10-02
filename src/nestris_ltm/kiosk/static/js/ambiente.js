/* Retro CRT + drifting-tetromino background ambiente for the kiosk view.
 *
 * Two sublayers (styled in effects.css):
 *   #ambiente-bg  z-index:-1  a <canvas> of slowly falling/drifting tetrominoes
 *                             at very low alpha, BEHIND all page content.
 *   #ambiente-fg  z-index:50  pure-CSS scanlines + vignette + flicker, ABOVE
 *                             content so the whole screen reads as a CRT tube.
 *
 * Self-contained vanilla JS + <canvas> (no library) so the kiosk works offline.
 * Auto-starts on load and exposes window.Ambiente = { start, stop }.
 *
 * Performance: a fixed object pool of pieces (the array never grows), the rAF
 * loop pauses while the tab is hidden (visibilitychange) so a backgrounded
 * kiosk doesn't burn CPU.
 *
 * Respects prefers-reduced-motion: no animation loop, a single static frame of
 * scattered tetrominoes is drawn instead (the CSS flicker is disabled too).
 */
(function () {
    const reduceMotion =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Muted palette (the celebration colours, used here at very low alpha so the
    // pieces sit far in the background rather than competing with content).
    const COLORS = [
        "#fbbf24", "#f59e0b", "#4dd2ff", "#46e07a",
        "#c084fc", "#ff5d6c", "#fde68a",
    ];

    // The seven tetrominoes as filled-cell offsets on a small grid.
    const SHAPES = [
        [[0, 0], [1, 0], [2, 0], [3, 0]], // I
        [[0, 0], [1, 0], [0, 1], [1, 1]], // O
        [[0, 0], [1, 0], [2, 0], [1, 1]], // T
        [[1, 0], [2, 0], [0, 1], [1, 1]], // S
        [[0, 0], [1, 0], [1, 1], [2, 1]], // Z
        [[0, 0], [0, 1], [1, 1], [2, 1]], // J
        [[2, 0], [0, 1], [1, 1], [2, 1]], // L
    ];

    let bgEl = null;
    let fgEl = null;
    let canvas = null;
    let ctx = null;
    let pieces = [];
    let rafId = null;
    let running = false;
    let lastTs = null;
    let enabled = true; // admin effects toggle

    function rand(a, b) {
        return a + Math.random() * (b - a);
    }

    function ensureDom() {
        if (bgEl) return;
        bgEl = document.getElementById("ambiente-bg");
        if (!bgEl) {
            bgEl = document.createElement("div");
            bgEl.id = "ambiente-bg";
            document.body.appendChild(bgEl);
        }
        canvas = document.createElement("canvas");
        canvas.className = "tetromino-canvas";
        bgEl.appendChild(canvas);
        ctx = canvas.getContext("2d");

        // The scanline/vignette overlay is pure CSS; just needs the element.
        fgEl = document.getElementById("ambiente-fg");
        if (!fgEl) {
            fgEl = document.createElement("div");
            fgEl.id = "ambiente-fg";
            document.body.appendChild(fgEl);
        }

        window.addEventListener("resize", () => {
            resizeCanvas();
            if (reduceMotion) drawStaticFrame();
        });
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) stop();
            else if (enabled && !reduceMotion) start();
        });
    }

    function resizeCanvas() {
        if (!canvas) return;
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function pieceCount() {
        // Scale with width but stay modest so the look reads as "ambient".
        return Math.max(8, Math.min(18, Math.round(window.innerWidth / 110)));
    }

    function spawnPiece(initial) {
        const cell = rand(16, 34);
        return {
            shape: SHAPES[(Math.random() * SHAPES.length) | 0],
            cell,
            x: rand(0, canvas.width),
            // Start scattered up the screen on first fill, just above the top after.
            y: initial ? rand(-canvas.height, canvas.height) : rand(-cell * 5, -cell * 2),
            color: COLORS[(Math.random() * COLORS.length) | 0],
            alpha: rand(0.05, 0.12),
            vy: rand(10, 26),                 // slow fall (px/s)
            rot: rand(0, Math.PI * 2),
            vrot: rand(-0.25, 0.25),          // slow spin (rad/s)
            driftPhase: rand(0, Math.PI * 2),
            driftAmp: rand(8, 26),
            driftSpeed: rand(0.2, 0.5),
        };
    }

    function buildPieces() {
        pieces = [];
        const n = pieceCount();
        for (let i = 0; i < n; i++) pieces.push(spawnPiece(true));
    }

    function drawPiece(p) {
        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.fillStyle = p.color;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        const c = p.cell;
        const gap = Math.max(1, c * 0.12);
        for (const [cx, cy] of p.shape) {
            ctx.fillRect(cx * c, cy * c, c - gap, c - gap);
        }
        ctx.restore();
    }

    function drawStaticFrame() {
        if (!ctx) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (const p of pieces) drawPiece(p);
    }

    function frame(ts) {
        if (!running) return;
        rafId = requestAnimationFrame(frame);
        if (lastTs == null) lastTs = ts;
        let dt = (ts - lastTs) / 1000;
        lastTs = ts;
        if (dt > 0.05) dt = 0.05; // clamp after a tab stall

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const margin = 80;
        for (const p of pieces) {
            p.y += p.vy * dt;
            p.rot += p.vrot * dt;
            p.driftPhase += p.driftSpeed * dt;
            const drawX = p.x + Math.cos(p.driftPhase) * p.driftAmp;
            // Respawn at the top once fully below the screen (object pool).
            if (p.y - margin > canvas.height) {
                Object.assign(p, spawnPiece(false), { x: rand(0, canvas.width) });
                continue;
            }
            const saved = p.x;
            p.x = drawX;
            drawPiece(p);
            p.x = saved;
        }
    }

    function start() {
        ensureDom();
        if (!enabled || running) return;
        resizeCanvas();
        if (!pieces.length) buildPieces();
        if (reduceMotion) {
            drawStaticFrame();
            return; // no loop under reduced motion
        }
        running = true;
        lastTs = null;
        rafId = requestAnimationFrame(frame);
    }

    function stop() {
        running = false;
        if (rafId != null) cancelAnimationFrame(rafId);
        rafId = null;
        if (ctx && canvas) ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    // Admin effects toggle: hide/show both sublayers and pause/resume the loop.
    function setEnabled(on) {
        enabled = !!on;
        ensureDom();
        bgEl.classList.toggle("fx-hidden", !enabled);
        if (fgEl) fgEl.classList.toggle("fx-hidden", !enabled);
        if (enabled) {
            if (!document.hidden) start();
        } else {
            stop();
        }
    }

    window.Ambiente = { start, stop, setEnabled };

    // Auto-start: the script tag sits at the end of <body>, so body exists.
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
