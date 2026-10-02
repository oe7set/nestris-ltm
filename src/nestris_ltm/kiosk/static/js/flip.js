/* flip.js — full-screen FLIP animation for the tournament bracket.
 *
 * Player boxes (`.slot[data-player-id]`) glide along CURVED paths to their new
 * positions when the seeding changes. Because the motion must not be clipped by
 * the bracket container's `overflow:auto`, each moving box is animated as a
 * CLONE inside a fixed full-viewport overlay (`#flip-layer`); the real box is
 * hidden until its clone lands.
 *
 *   MOVED  — a box that existed before and after: flies old → new position.
 *   ENTER  — a box new to the bracket: flies in from the player's highscore-list
 *            row (if on screen) else from the nearest screen edge.
 *   EXIT   — a box that left the bracket: flies out to its list row / screen edge
 *            and fades.
 *
 * In-flight animations are cancelled and finalized when a new render arrives, so
 * frequent WebSocket pushes never cause double-vision. Respects reduced-motion.
 *
 * Public API:
 *   Flip.animatedRender(renderFn)        // bracket region, cross-viewport flights
 *   Flip.animatedList(listEl, renderFn)  // simple in-place FLIP for list rows
 */
(function () {
    const DURATION = 2000;
    const EASING = "cubic-bezier(0.2, 0.8, 0.2, 1)";
    const MAX_FLIGHTS = 40; // beyond this, skip the choreography (just swap DOM)

    const reduceMotion =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let generation = 0;
    // Live flights this generation: { anim, clone, realEl }.
    let active = [];

    function layer() {
        let el = document.getElementById("flip-layer");
        if (!el) {
            el = document.createElement("div");
            el.id = "flip-layer";
            document.body.appendChild(el);
        }
        return el;
    }

    /* Finalize every in-flight animation immediately: reveal hidden reals,
       remove clones. Called before a new render so FIRST rects are measured
       from settled, visible elements. */
    function finishAll() {
        for (const f of active) {
            try { f.anim.cancel(); } catch (e) {}
            if (f.realEl) f.realEl.style.visibility = "";
            if (f.clone && f.clone.parentNode) f.clone.remove();
        }
        active = [];
    }

    function rectsBySlot(root) {
        const map = new Map();
        if (!root) return map;
        root.querySelectorAll(".slot[data-player-id]").forEach((el) => {
            if (el.closest(".match-hidden")) return; // padding match — never animate
            map.set(el.dataset.playerId, { el, rect: el.getBoundingClientRect() });
        });
        return map;
    }

    function listAnchors() {
        const map = new Map();
        const list = document.getElementById("leaderboard");
        if (!list) return map;
        list.querySelectorAll("li[data-player-id]").forEach((el) => {
            const r = el.getBoundingClientRect();
            // Only usable as an anchor when actually on screen.
            if (r.width > 0 && r.bottom > 0 && r.top < window.innerHeight) {
                map.set(el.dataset.playerId, r);
            }
        });
        return map;
    }

    function nearestEdgeRect(rect) {
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const dist = {
            left: cx,
            right: window.innerWidth - cx,
            top: cy,
            bottom: window.innerHeight - cy,
        };
        const edge = Object.keys(dist).reduce((a, b) => (dist[a] < dist[b] ? a : b));
        const off = 80;
        let left = rect.left;
        let top = rect.top;
        if (edge === "left") left = -rect.width - off;
        else if (edge === "right") left = window.innerWidth + off;
        else if (edge === "top") top = -rect.height - off;
        else top = window.innerHeight + off;
        return { left, top, width: rect.width, height: rect.height };
    }

    /* Build a clone of `srcEl` positioned (fixed) at `destRect`. */
    function makeClone(srcEl, destRect) {
        const clone = srcEl.cloneNode(true);
        clone.classList.add("flip-clone");
        clone.style.left = destRect.left + "px";
        clone.style.top = destRect.top + "px";
        clone.style.width = destRect.width + "px";
        clone.style.height = destRect.height + "px";
        layer().appendChild(clone);
        return clone;
    }

    /* Curved keyframes for transform going (x0,y0) -> (x1,y1). */
    function curve(x0, y0, x1, y1, op0, op1) {
        const dx = x1 - x0;
        const dy = y1 - y0;
        const dist = Math.hypot(dx, dy) || 1;
        const k = Math.max(20, Math.min(120, dist * 0.2));
        // Unit normal of the travel vector.
        const nx = -dy / dist;
        const ny = dx / dist;
        const mx = (x0 + x1) / 2 + nx * k;
        const my = (y0 + y1) / 2 + ny * k;
        return [
            { transform: `translate(${x0}px, ${y0}px)`, opacity: op0, offset: 0 },
            { transform: `translate(${mx}px, ${my}px)`, opacity: (op0 + op1) / 2, offset: 0.5 },
            { transform: `translate(${x1}px, ${y1}px)`, opacity: op1, offset: 1 },
        ];
    }

    function flight(clone, keyframes, realEl, gen) {
        const anim = clone.animate(keyframes, {
            duration: DURATION,
            easing: EASING,
            fill: "both",
        });
        const entry = { anim, clone, realEl };
        active.push(entry);
        anim.finished
            .then(() => {
                if (gen !== generation) return; // superseded — finishAll handled it
                if (realEl) realEl.style.visibility = "";
                clone.remove();
                active = active.filter((e) => e !== entry);
            })
            .catch(() => {});
    }

    function animatedRender(renderFn) {
        if (reduceMotion) {
            renderFn();
            return;
        }
        finishAll();
        const gen = ++generation;

        const container = document.getElementById("bracket");
        const first = rectsBySlot(container);
        // Clone the old elements now (they get detached on re-render) for EXITs.
        const oldEls = new Map();
        first.forEach((v, id) => oldEls.set(id, v.el));
        const anchors = listAnchors();

        renderFn();

        const last = rectsBySlot(container);

        // Classify ids.
        const moved = [];
        const entered = [];
        const exited = [];
        last.forEach((v, id) => (first.has(id) ? moved : entered).push(id));
        first.forEach((_, id) => {
            if (!last.has(id)) exited.push(id);
        });

        const total = moved.length + entered.length + exited.length;
        if (total === 0 || total > MAX_FLIGHTS) return; // nothing to do / too many

        // MOVED: clone sits at the new rect; fly from old offset to 0.
        for (const id of moved) {
            const f = first.get(id).rect;
            const l = last.get(id);
            const dx = f.left - l.rect.left;
            const dy = f.top - l.rect.top;
            if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue; // didn't move
            const clone = makeClone(l.el, l.rect);
            l.el.style.visibility = "hidden";
            flight(clone, curve(dx, dy, 0, 0, 1, 1), l.el, gen);
        }

        // ENTER: fly from the list row (if visible) else nearest edge -> new rect.
        for (const id of entered) {
            const l = last.get(id);
            const fromRect = anchors.get(id) || nearestEdgeRect(l.rect);
            const dx = fromRect.left - l.rect.left;
            const dy = fromRect.top - l.rect.top;
            const clone = makeClone(l.el, l.rect);
            l.el.style.visibility = "hidden";
            flight(clone, curve(dx, dy, 0, 0, 0.3, 1), l.el, gen);
        }

        // EXIT: clone sits at the old rect; fly to the list row / edge and fade.
        for (const id of exited) {
            const f = first.get(id).rect;
            const toRect = anchors.get(id) || nearestEdgeRect(f);
            const dx = toRect.left - f.left;
            const dy = toRect.top - f.top;
            const clone = makeClone(oldEls.get(id), f);
            flight(clone, curve(0, 0, dx, dy, 1, 0), null, gen);
        }
    }

    /* Lightweight in-place FLIP for the highscore list (no clipping concern). */
    function animatedList(listEl, renderFn) {
        if (reduceMotion || !listEl) {
            renderFn();
            return;
        }
        const first = new Map();
        listEl.querySelectorAll("li[data-player-id]").forEach((el) => {
            first.set(el.dataset.playerId, el.getBoundingClientRect());
        });

        renderFn();

        listEl.querySelectorAll("li[data-player-id]").forEach((el) => {
            const id = el.dataset.playerId;
            const f = first.get(id);
            if (!f) {
                // New row: subtle fade-in.
                el.animate(
                    [{ opacity: 0, transform: "translateY(-6px)" }, { opacity: 1, transform: "none" }],
                    { duration: 700, easing: EASING }
                );
                return;
            }
            const l = el.getBoundingClientRect();
            const dy = f.top - l.top;
            if (Math.abs(dy) < 1) return;
            el.animate(
                [{ transform: `translateY(${dy}px)` }, { transform: "translateY(0)" }],
                { duration: 900, easing: EASING }
            );
        });
    }

    window.Flip = { animatedRender, animatedList };
})();
