/* NestrisLTM addition to the ported highscore view: portrait screens.
 *
 * "?layout=portrait" puts the highscore on top and the bracket below
 * (css/view-portrait.css). The bracket gets the largest zoom at which the
 * whole tree is visible without scrolling, kept up to date while the bracket
 * changes and when the window is resized. A small bracket grows (up to
 * ZOOM_MAX) so it fills the wide, short area.
 */
(function () {
    if (!document.body.classList.contains("portrait")) return;
    const ZOOM_MIN = 0.3;
    const ZOOM_MAX = 1.6;
    const bracket = document.getElementById("bracket");
    if (!bracket) return;

    function setZoom(z) {
        bracket.style.setProperty("--bracket-zoom", String(z));
    }

    function fits(z) {
        setZoom(z);
        return bracket.scrollWidth <= bracket.clientWidth + 1
            && bracket.scrollHeight <= bracket.clientHeight + 1;
    }

    // Layout is not linear in the zoom (gaps, min-widths), so search for it.
    function fit() {
        if (!bracket.children.length) return;
        if (fits(ZOOM_MAX)) return;
        let lo = ZOOM_MIN;
        let hi = ZOOM_MAX;
        for (let i = 0; i < 9; i++) {
            const mid = (lo + hi) / 2;
            if (fits(mid)) lo = mid;
            else hi = mid;
        }
        setZoom(Math.floor(lo * 100) / 100);
    }

    let pending = 0;
    function refit() {
        cancelAnimationFrame(pending);
        pending = requestAnimationFrame(fit);
    }
    new MutationObserver(refit).observe(bracket, { childList: true });
    window.addEventListener("resize", refit);
    refit();
})();
