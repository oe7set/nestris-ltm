/* Live-drama banners for the public kiosk view.
 *
 * The backend only ever sends full-state snapshots (no "event" message type),
 * so this module derives the dramatic moments CLIENT-SIDE by diffing each
 * snapshot against the previous one, then fires a brief full-width banner:
 *
 *   NEW HIGH SCORE          <- stats_update    (stats.highest_score rises)
 *   <name> TAKES THE LEAD   <- leaderboard_update (top user_id changes)
 *   <n> POINTS!             <- train_update    (current_milestone rises)
 *   <name> OVERTAKES!       <- leaderboard_update (live player climbs into top N)
 *
 * Self-contained vanilla JS; exposes window.Drama. Banners live in #drama-layer
 * (styled in effects.css) and are throttled through a small priority queue so
 * near-simultaneous events don't strobe.
 *
 * CRITICAL — no false-fire on connect/reconnect: KioskSocket re-sends `init`
 * (a full snapshot) on every (re)connect. observeInit ONLY re-seeds the
 * baselines and NEVER enqueues a banner, so a reconnect can't produce a phantom
 * "lead change"/"new record" — the baseline is overwritten to the just-received
 * truth and only genuine later *_update diffs fire.
 *
 * Respects prefers-reduced-motion via CSS (banners appear instantly, no slide).
 */
(function () {
    const MIN_DISPLAY = 2600;        // ms a banner stays before the next replaces it
    const OVERTAKE_TOP_N = 5;        // a live player must climb into this to count
    const OVERTAKE_COOLDOWN = 20000; // ms before the same player can re-fire overtake
    const PRIORITY = { highscore: 4, lead: 3, milestone: 2, overtake: 1 };

    let primed = false;              // becomes true after the first init; gates firing
    let enabled = true;              // admin effects toggle; false suppresses all banners
    const prev = {
        topUserId: null,
        highestScore: null,
        milestone: null,
        liveRanks: new Map(),        // user_id -> rank, for is_live entries
    };
    const overtakeFiredAt = new Map(); // user_id -> performance.now() of last overtake

    const queue = [];
    let current = null;              // the banner currently on screen ({...banner, el})
    let showing = false;             // true while a banner occupies the layer
    let layer = null;

    // --- helpers ----------------------------------------------------------

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s ?? "";
        return d.innerHTML;
    }
    function fmt(n) {
        return (n ?? 0).toLocaleString("en-US");
    }
    function ensureLayer() {
        if (layer) return;
        layer = document.getElementById("drama-layer");
        if (!layer) {
            layer = document.createElement("div");
            layer.id = "drama-layer";
            document.body.appendChild(layer);
        }
    }

    function seedLiveRanks(entries) {
        prev.liveRanks.clear();
        for (const e of entries || []) {
            if (e.is_live) prev.liveRanks.set(e.user_id, e.rank);
        }
    }

    // --- baseline seeding (init / reconnect): NEVER fires ------------------

    function observeInit(snapshot) {
        const s = snapshot || {};
        const lb = s.leaderboard || [];
        prev.topUserId = lb.length ? lb[0].user_id : null;
        prev.highestScore = (s.stats || {}).highest_score ?? null;
        prev.milestone = (s.train || {}).current_milestone ?? null;
        seedLiveRanks(lb);
        // Drop anything in flight so a reconnect can't leave a stale banner.
        clearAll();
        primed = true;
    }

    // --- per-message detectors --------------------------------------------

    function observeStats(stats) {
        if (!stats) return;
        const hs = stats.highest_score ?? null;
        if (primed && hs != null && prev.highestScore != null && hs > prev.highestScore) {
            enqueue({
                type: "highscore",
                priority: PRIORITY.highscore,
                title: "NEUER REKORD",
                subtitle: fmt(hs) + " PUNKTE",
                key: "highscore:" + hs,
            });
        }
        if (hs != null) prev.highestScore = hs;
    }

    function observeTrain(train) {
        if (!train) return;
        const m = train.current_milestone ?? null;
        if (primed && m != null && prev.milestone != null && m > prev.milestone) {
            enqueue({
                type: "milestone",
                priority: PRIORITY.milestone,
                title: fmt(m) + " PUNKTE!",
                subtitle: "SCORE-TRAIN MEILENSTEIN",
                key: "milestone:" + m,
            });
        }
        if (m != null) prev.milestone = m;
    }

    function observeLeaderboard(entries) {
        const lb = entries || [];
        const top = lb.length ? lb[0] : null;

        // Lead change: compare TOP user_id (the message fires on any field change,
        // so array equality is the wrong test). Guard against the empty->filled
        // first population (that's a fill, not a takeover).
        if (
            primed && top &&
            top.user_id !== prev.topUserId &&
            prev.topUserId !== null
        ) {
            enqueue({
                type: "lead",
                priority: PRIORITY.lead,
                title: esc(top.nickname) + " ÜBERNIMMT DIE FÜHRUNG",
                subtitle: fmt(top.score) + " PUNKTE",
                key: "lead:" + top.user_id + ":" + top.score,
            });
        }

        // Live overtake: a currently-playing entry climbing into the top N for
        // the first time. Conservative + per-user cooldown to avoid spam.
        if (primed) {
            const now = performance.now();
            for (const e of lb) {
                if (!e.is_live) continue;
                const wasRank = prev.liveRanks.get(e.user_id);
                const climbedIntoTop =
                    e.rank <= OVERTAKE_TOP_N &&
                    (wasRank == null || wasRank > OVERTAKE_TOP_N) &&
                    e.user_id !== (top && top.user_id); // lead banner already covers #1
                const cooled =
                    !overtakeFiredAt.has(e.user_id) ||
                    now - overtakeFiredAt.get(e.user_id) > OVERTAKE_COOLDOWN;
                if (climbedIntoTop && cooled) {
                    overtakeFiredAt.set(e.user_id, now);
                    enqueue({
                        type: "overtake",
                        priority: PRIORITY.overtake,
                        title: esc(e.nickname) + " ZIEHT VORBEI!",
                        subtitle: "JETZT #" + e.rank + " · " + fmt(e.score) + " PUNKTE",
                        key: "overtake:" + e.user_id + ":" + e.rank,
                    });
                }
            }
        }

        if (top) prev.topUserId = top.user_id;
        seedLiveRanks(lb);
    }

    // --- queue + display ---------------------------------------------------
    //
    // Robustness: exactly ONE banner element may exist at a time. showBanner
    // empties the layer first, so any element that somehow outlived its timer is
    // removed on the next show. Each banner's retire works on its OWN captured
    // element (banner.el), never a shared global, and a single linear timer chain
    // (`showing` gate) drives the queue — so a delayed/throttled timer can never
    // remove the wrong element and strand a banner on screen.

    function enqueue(banner) {
        if (!enabled) return;
        // De-dupe: skip if an identical banner is queued or currently showing.
        if (current && current.key === banner.key) return;
        if (queue.some((b) => b.key === banner.key)) return;
        queue.push(banner);
        queue.sort((a, b) => b.priority - a.priority);
        pump();
    }

    function pump() {
        if (showing || !enabled) return;       // a banner already owns the layer
        const next = queue.shift();
        if (!next) return;
        showBanner(next);
    }

    function showBanner(banner) {
        ensureLayer();
        // Guarantee a clean layer: drop any leftover element before showing.
        while (layer.firstChild) layer.removeChild(layer.firstChild);

        const el = document.createElement("div");
        el.className = "drama-banner drama-banner--" + banner.type;
        el.innerHTML =
            '<div class="db-title">' + banner.title + "</div>" +
            (banner.subtitle ? '<div class="db-sub">' + banner.subtitle + "</div>" : "");
        layer.appendChild(el);

        current = { ...banner, el };
        showing = true;
        // Force reflow so the .show transition runs from the start state.
        void el.offsetWidth;
        el.classList.add("show");

        // Schedule this banner's own retirement. retire() captures THIS el.
        setTimeout(() => retire(el), MIN_DISPLAY);
    }

    function retire(el) {
        // Slide out, then remove exactly this element after the transition.
        el.classList.remove("show");
        setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 500);
        // Only release the slot if this element is still the current banner
        // (a clearAll() may have already moved on).
        if (current && current.el === el) {
            current = null;
            showing = false;
            pump();
        }
    }

    // Wipe everything immediately (reconnect, or effects turned off).
    function clearAll() {
        queue.length = 0;
        current = null;
        showing = false;
        if (layer) while (layer.firstChild) layer.removeChild(layer.firstChild);
    }

    // Admin effects toggle. Off: suppress + wipe any visible/queued banner.
    function setEnabled(on) {
        enabled = !!on;
        if (!enabled) clearAll();
    }

    window.Drama = {
        observeInit,
        observeStats,
        observeTrain,
        observeLeaderboard,
        setEnabled,
    };
})();
