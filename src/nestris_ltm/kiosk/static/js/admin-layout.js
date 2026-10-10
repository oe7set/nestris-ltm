/* NestrisLTM additions to the ported tournament console: room for the bracket.
 *
 * - "?embedded=1" (the admin UI's iframe): the phase banner around it has
 *   FIX / reset / UNSEED, so the console hides its copies (admin-layout.css).
 * - Player list and help texts can be folded away; bracket zoom with
 *   -, +, "fit" (largest zoom at which the whole tree is visible, kept up to
 *   date while the bracket changes) and 100 %.
 * Choices are kept per browser (localStorage), separately for the embedded
 * console and the one in its own window.
 */
(function () {
    const embedded = new URLSearchParams(location.search).get("embedded") === "1";
    const KEY = embedded ? "nltm.console-layout.embedded" : "nltm.console-layout";
    const ZOOM_MIN = 0.3;
    const ZOOM_MAX = 2;
    const ZOOM_STEP = 0.1;

    const defaults = { players: true, help: false, zoom: 1, fit: false };
    let prefs = { ...defaults };
    try {
        const stored = JSON.parse(localStorage.getItem(KEY) || "{}");
        prefs = {
            players: stored.players !== false,
            help: stored.help === true,
            zoom: Number.isFinite(stored.zoom) ? clamp(stored.zoom) : 1,
            fit: stored.fit === true,
        };
    } catch (e) {
        // storage blocked or broken: defaults
    }

    function clamp(z) {
        return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(z * 100) / 100));
    }

    function save() {
        try {
            localStorage.setItem(KEY, JSON.stringify(prefs));
        } catch (e) {
            // ignore
        }
    }

    const bracket = document.getElementById("bracket");
    const body = document.body;
    const $ = (id) => document.getElementById(id);

    function setZoom(z) {
        bracket.style.setProperty("--bracket-zoom", String(z));
        $("zoom-val").textContent = Math.round(z * 100) + " %";
    }

    // Largest zoom (<= 100 %) at which the tree needs no scrolling. Layout is
    // not linear in the zoom (gaps, min-widths), so search for it.
    function fit() {
        if (!bracket.children.length) return;
        const fits = (z) => {
            setZoom(z);
            return bracket.scrollWidth <= bracket.clientWidth + 1
                && bracket.scrollHeight <= bracket.clientHeight + 1;
        };
        if (fits(1)) {
            prefs.zoom = 1;
        } else {
            let lo = ZOOM_MIN;
            let hi = 1;
            for (let i = 0; i < 8; i++) {
                const mid = (lo + hi) / 2;
                if (fits(mid)) lo = mid;
                else hi = mid;
            }
            prefs.zoom = Math.floor(lo * 100) / 100;
        }
        setZoom(prefs.zoom);
    }

    function apply() {
        body.classList.toggle("embedded", embedded);
        body.classList.toggle("players-off", !prefs.players);
        body.classList.toggle("help-on", prefs.help);
        $("btn-players").classList.toggle("is-on", prefs.players);
        $("btn-help").classList.toggle("is-on", prefs.help);
        $("btn-zoom-fit").classList.toggle("is-on", prefs.fit);
        if (prefs.fit) fit();
        else setZoom(prefs.zoom);
    }

    function change(update) {
        Object.assign(prefs, update);
        save();
        apply();
    }

    $("btn-players").addEventListener("click", () => change({ players: !prefs.players }));
    $("btn-help").addEventListener("click", () => change({ help: !prefs.help }));
    $("btn-zoom-out").addEventListener("click", () =>
        change({ fit: false, zoom: clamp(prefs.zoom - ZOOM_STEP) }));
    $("btn-zoom-in").addEventListener("click", () =>
        change({ fit: false, zoom: clamp(prefs.zoom + ZOOM_STEP) }));
    $("btn-zoom-reset").addEventListener("click", () => change({ fit: false, zoom: 1 }));
    $("btn-zoom-fit").addEventListener("click", () => change({ fit: !prefs.fit }));

    // Ctrl + mouse wheel over the bracket zooms it (not the whole page).
    bracket.addEventListener("wheel", (e) => {
        if (!e.ctrlKey) return;
        e.preventDefault();
        change({ fit: false, zoom: clamp(prefs.zoom + (e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP)) });
    }, { passive: false });

    // "Fit" follows the bracket (re-render on every update) and the window.
    let pending = 0;
    function refit() {
        if (!prefs.fit) return;
        cancelAnimationFrame(pending);
        pending = requestAnimationFrame(fit);
    }
    new MutationObserver(refit).observe(bracket, { childList: true });
    window.addEventListener("resize", refit);

    apply();
})();
