/* Renders the score-train progress bar (cumulative total toward 1M milestones).
 *
 * The total-score number tweens (counts up) to its new value on each update so
 * a rising score visibly climbs instead of snapping. The bar fill / locomotive
 * are animated by their CSS transitions.
 */

const _reduceMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let _trainValue = 0; // last displayed total-score value
let _trainAnim = null; // active count-up animation handle (rAF id)

function _animateCount(el, from, to, duration) {
    if (_trainAnim) cancelAnimationFrame(_trainAnim);
    if (_reduceMotion || from === to) {
        el.textContent = to.toLocaleString("en-US");
        _trainValue = to;
        return;
    }
    const start = performance.now();
    const delta = to - from;
    const tick = (now) => {
        const t = Math.min(1, (now - start) / duration);
        // ease-out cubic
        const eased = 1 - Math.pow(1 - t, 3);
        const val = Math.round(from + delta * eased);
        el.textContent = val.toLocaleString("en-US");
        if (t < 1) {
            _trainAnim = requestAnimationFrame(tick);
        } else {
            el.textContent = to.toLocaleString("en-US");
            _trainValue = to;
            _trainAnim = null;
        }
    };
    _trainAnim = requestAnimationFrame(tick);
}

function renderTrain(train) {
    const total = document.getElementById("train-total");
    const fill = document.getElementById("train-fill");
    const loco = document.getElementById("train-loco");
    const cur = document.getElementById("train-current");
    const next = document.getElementById("train-next");
    if (!fill) return;

    const pct = Math.round((train.progress ?? 0) * 100);
    if (total) _animateCount(total, _trainValue, train.total_score ?? 0, 800);
    fill.style.width = pct + "%";
    if (loco) loco.style.left = pct + "%";
    if (cur) cur.textContent = (train.current_milestone ?? 0).toLocaleString("en-US");
    if (next) {
        next.textContent =
            train.next_milestone != null
                ? train.next_milestone.toLocaleString("en-US")
                : "—";
    }
}
