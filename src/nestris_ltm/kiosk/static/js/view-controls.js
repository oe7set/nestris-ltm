/* Remote-controlled presentation of the public highscore list.
 *
 * The admin panel drives three things over the WebSocket:
 *   - view_settings { font_scale, autoscroll } : persistent display settings
 *   - view_scroll   { position }               : a one-shot scroll command
 *
 * Font scale is applied as a CSS custom property on the list so the rows grow/
 * shrink (app.css uses calc(... * var(--lb-font-scale))). Auto-scroll slowly
 * pans the list from top to bottom and back, pausing briefly at each end.
 *
 * Auto-scroll design: the loop keeps its OWN logical position (`pos`, a float in
 * pixels) and writes it to el.scrollTop on every frame. It never reads scrollTop
 * back as the source of truth. This matters because the list re-renders on every
 * leaderboard poll (innerHTML is rebuilt -> scrollTop snaps to 0); by re-asserting
 * `pos` each frame, that reset self-heals on the next frame instead of yanking
 * the pan back to the top. Tracking a float also avoids losing sub-pixel motion
 * at slow speeds (reading the rounded scrollTop back would stall the pan).
 */
(function () {
    const LIST_ID = "leaderboard";

    let autoscrollOn = false;
    let rafId = null;
    let direction = 1; // 1 = down, -1 = up
    let pos = 0; // our own logical scroll position (px, float)
    let pauseUntil = 0; // timestamp (performance.now) to resume after an end pause
    let lastTs = null;
    const SPEED = 30; // pixels per second (slow, readable pan)
    const END_PAUSE_MS = 1500;

    function list() {
        return document.getElementById(LIST_ID);
    }

    function applyViewSettings(settings) {
        if (!settings) return;
        const el = list();
        if (el && typeof settings.font_scale === "number") {
            el.style.setProperty("--lb-font-scale", settings.font_scale);
        }
        // Box transparency: drive the global --box-opacity var so the panels /
        // match boxes / stat cards let the background tetrominoes show through.
        if (typeof settings.box_opacity === "number") {
            document.documentElement.style.setProperty("--box-opacity", settings.box_opacity);
        }
        setAutoscroll(!!settings.autoscroll);
    }

    function setAutoscroll(on) {
        if (on === autoscrollOn) return;
        autoscrollOn = on;
        if (on) {
            const el = list();
            direction = 1;
            pos = el ? el.scrollTop : 0; // start from the current position
            pauseUntil = 0;
            lastTs = null;
            rafId = requestAnimationFrame(step);
        } else if (rafId != null) {
            cancelAnimationFrame(rafId);
            rafId = null;
        }
    }

    function step(ts) {
        if (!autoscrollOn) return;
        rafId = requestAnimationFrame(step); // keep the loop alive up-front

        const el = list();
        if (!el) return;

        const maxScroll = el.scrollHeight - el.clientHeight;
        // List fits entirely — nothing to pan, just idle (loop stays alive so it
        // starts panning automatically once the list grows past the viewport).
        if (maxScroll <= 1) {
            lastTs = ts;
            return;
        }

        if (lastTs == null) lastTs = ts;
        const dt = (ts - lastTs) / 1000;
        lastTs = ts;

        if (ts >= pauseUntil) {
            pos += direction * SPEED * dt;
            if (pos >= maxScroll) {
                pos = maxScroll;
                direction = -1;
                pauseUntil = ts + END_PAUSE_MS; // pause at the bottom
            } else if (pos <= 0) {
                pos = 0;
                direction = 1;
                pauseUntil = ts + END_PAUSE_MS; // pause at the top
            }
        } else {
            // Keep pos valid if the list shrank while we were paused.
            pos = Math.max(0, Math.min(pos, maxScroll));
        }
        // Re-assert our position every frame so a list re-render (scrollTop -> 0)
        // can't fight the pan; we own the scroll position while auto-scroll is on.
        el.scrollTop = pos;
    }

    // One-shot scroll to a fractional position (0 = top, 1 = bottom). Smooth.
    function scrollViewTo(position) {
        const el = list();
        if (!el) return;
        const maxScroll = el.scrollHeight - el.clientHeight;
        const target = Math.max(0, Math.min(1, position)) * maxScroll;
        // Keep the auto-scroll loop's logical position in sync so it resumes from
        // here instead of snapping back on the next frame.
        pos = target;
        lastTs = null;
        el.scrollTo({ top: target, behavior: autoscrollOn ? "auto" : "smooth" });
    }

    // Expose for view.html WebSocket wiring.
    window.ViewControls = { applyViewSettings, scrollViewTo, setAutoscroll };
})();
