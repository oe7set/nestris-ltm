/* Admin console logic: bracket mutations + player management (no auth). */

(function () {
    // Latest data we render the player list from.
    let leaderboard = [];
    let disabledIds = new Set();

    function toast(msg, ok = true) {
        const el = document.getElementById("toast");
        el.textContent = msg;
        el.className = ok ? "ok" : "err";
        el.classList.remove("hidden");
        el.style.position = "fixed";
        setTimeout(() => el.classList.add("hidden"), 2500);
    }

    async function post(path, body) {
        try {
            const res = await fetch(path, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: body ? JSON.stringify(body) : null,
            });
            if (!res.ok) {
                const detail = await res.json().catch(() => ({}));
                toast(detail.detail || `Error ${res.status}`, false);
                return null;
            }
            // The server broadcasts updates over the socket; no local render needed.
            return await res.json();
        } catch (e) {
            toast("Network error", false);
            return null;
        }
    }

    // Expose admin hooks consumed by bracket-view.js (only used once seeded).
    window.__bracketAdmin = {
        onPickWinner: (matchId, userId) =>
            post("/api/tournament/winner", { match_id: matchId, user_id: userId }),
        onClearWinner: (matchId) =>
            post("/api/tournament/clear-winner", { match_id: matchId }),
    };

    // --- Player management sidebar ---------------------------------------

    function renderPlayers() {
        const list = document.getElementById("player-list");
        if (!list) return;
        list.innerHTML = "";
        leaderboard.forEach((p, i) => {
            const disabled = disabledIds.has(p.user_id);
            // Rank shown is the live highscore rank; "out" styling if disabled.
            const card = document.createElement("div");
            card.className = "player-card flex items-center justify-between" + (disabled ? " disabled" : "");
            card.innerHTML = `
                <div class="flex items-center gap-2 min-w-0">
                    <span class="pc-rank ${disabled ? "out" : ""}">#${p.rank}</span>
                    <span class="pc-name font-medium truncate">${escapeHtml(p.nickname)}</span>
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <span class="pc-score">${(p.score ?? 0).toLocaleString("en-US")}</span>
                    <span class="pc-toggle ${disabled ? "off" : "on"}">${disabled ? "enable" : "disable"}</span>
                </div>
            `;
            card.querySelector(".pc-toggle").addEventListener("click", () => {
                const path = disabled ? "/api/tournament/players/enable" : "/api/tournament/players/disable";
                post(path, { user_id: p.user_id });
            });
            list.appendChild(card);
        });
    }

    // --- Control bar buttons ---------------------------------------------

    document.getElementById("btn-fix").addEventListener("click", async () => {
        if (confirm("Freeze the current line-up as bracket seeds? This restarts the tournament."))
            if (await post("/api/tournament/fix")) toast("Bracket seeded");
    });
    document.getElementById("btn-reset").addEventListener("click", async () => {
        if (confirm("Clear all winners (keep seeds)?"))
            if (await post("/api/tournament/reset")) toast("Winners cleared");
    });
    document.getElementById("btn-unseed").addEventListener("click", async () => {
        if (confirm("Unseed the bracket and resume live auto-fill?"))
            if (await post("/api/tournament/unseed")) toast("Bracket unseeded");
    });

    // Tournament-size controls: slider, +/- steppers and presets all funnel
    // through setSize() so they share one clamp + debounced POST path.
    const slider = document.getElementById("active-count");
    const sliderVal = document.getElementById("active-count-val");
    const sizeMin = parseInt(slider.min, 10);
    const sizeMax = parseInt(slider.max, 10);
    let sliderTimer = null;

    // Update the UI for `count` and (unless `silent`) push it to the server.
    // `silent` is used when syncing from a server broadcast to avoid echoing.
    function setSize(count, silent = false) {
        const n = Math.min(sizeMax, Math.max(sizeMin, count));
        slider.value = n;
        sliderVal.textContent = n;
        if (silent) return;
        clearTimeout(sliderTimer);
        sliderTimer = setTimeout(
            () => post("/api/tournament/active-count", { count: n }),
            250
        );
    }

    slider.addEventListener("input", () => setSize(parseInt(slider.value, 10)));
    document.getElementById("size-minus").addEventListener("click",
        () => setSize(parseInt(slider.value, 10) - 1));
    document.getElementById("size-plus").addEventListener("click",
        () => setSize(parseInt(slider.value, 10) + 1));
    document.querySelectorAll("[data-size]").forEach((b) =>
        b.addEventListener("click", () => setSize(parseInt(b.dataset.size, 10))));

    // --- View remote-control (public highscore list) ---------------------

    const fontSlider = document.getElementById("font-scale");
    const fontVal = document.getElementById("font-scale-val");
    const autoscrollBtn = document.getElementById("btn-autoscroll");
    const scrollSlider = document.getElementById("scroll-pos");
    let autoscrollOn = false;
    let fontTimer = null;

    // Update the SIZE UI for `scale` and (unless `silent`) push it to the server.
    function setFontScale(scale, silent = false) {
        const n = Math.min(2.5, Math.max(0.6, Math.round(scale * 10) / 10));
        fontSlider.value = n;
        fontVal.textContent = `${n.toFixed(1)}×`;
        if (silent) return;
        clearTimeout(fontTimer);
        fontTimer = setTimeout(
            () => post("/api/tournament/view/settings", { font_scale: n }),
            200
        );
    }

    function setAutoscrollUI(on) {
        autoscrollOn = on;
        autoscrollBtn.textContent = `AUTOSCROLL: ${on ? "ON" : "OFF"}`;
        autoscrollBtn.classList.toggle("btn-accent", on);
    }

    fontSlider.addEventListener("input",
        () => setFontScale(parseFloat(fontSlider.value)));
    document.getElementById("font-minus").addEventListener("click",
        () => setFontScale(parseFloat(fontSlider.value) - 0.1));
    document.getElementById("font-plus").addEventListener("click",
        () => setFontScale(parseFloat(fontSlider.value) + 0.1));

    autoscrollBtn.addEventListener("click", () => {
        // Optimistically flip the UI; the server broadcast confirms it.
        setAutoscrollUI(!autoscrollOn);
        post("/api/tournament/view/settings", { autoscroll: autoscrollOn });
    });

    // Scroll position: live drag sends fractional position (debounced lightly).
    let scrollTimer = null;
    function sendScroll(pct) {
        clearTimeout(scrollTimer);
        scrollTimer = setTimeout(
            () => post("/api/tournament/view/scroll", { position: pct / 100 }),
            60
        );
    }
    scrollSlider.addEventListener("input",
        () => sendScroll(parseInt(scrollSlider.value, 10)));
    document.getElementById("scroll-top").addEventListener("click", () => {
        scrollSlider.value = 0;
        sendScroll(0);
    });
    document.getElementById("scroll-bottom").addEventListener("click", () => {
        scrollSlider.value = 100;
        sendScroll(100);
    });

    // Reflect server-pushed view settings (init + other admins' changes).
    function syncViewSettings(s) {
        if (!s) return;
        if (typeof s.font_scale === "number") setFontScale(s.font_scale, true);
        setAutoscrollUI(!!s.autoscroll);
        if (typeof s.effects_enabled === "boolean") setEffectsUI(s.effects_enabled);
        if (typeof s.banners_enabled === "boolean") setBannersUI(s.banners_enabled);
        if (typeof s.box_opacity === "number") {
            setBoxTransparency(Math.round((1 - s.box_opacity) * 100), true);
        }
    }

    // --- Visual effects toggle (CRT ambiente + bracket victory bursts) ---
    // Carried on the view_settings message (not a separate endpoint).

    const effectsBtn = document.getElementById("btn-effects");
    let effectsOn = true;

    function setEffectsUI(on) {
        effectsOn = on;
        effectsBtn.querySelector(".lbl").textContent = `EFFEKTE: ${on ? "ON" : "OFF"}`;
        effectsBtn.classList.toggle("btn-accent", on);
    }

    effectsBtn.addEventListener("click", () => {
        setEffectsUI(!effectsOn);
        post("/api/tournament/view/settings", { effects_enabled: effectsOn });
    });

    // --- Live-drama banners toggle (independent of EFFEKTE) ---

    const bannersBtn = document.getElementById("btn-banners");
    let bannersOn = true;

    function setBannersUI(on) {
        bannersOn = on;
        bannersBtn.querySelector(".lbl").textContent = `MELDUNGEN: ${on ? "ON" : "OFF"}`;
        bannersBtn.classList.toggle("btn-accent", on);
    }

    bannersBtn.addEventListener("click", () => {
        setBannersUI(!bannersOn);
        post("/api/tournament/view/settings", { banners_enabled: bannersOn });
    });

    // --- Box transparency slider (lets the background tetrominoes show through) ---
    // The slider value is TRANSPARENCY in % (0 = solid); the server stores opacity.

    const boxSlider = document.getElementById("box-opacity");
    const boxVal = document.getElementById("box-opacity-val");
    let boxTimer = null;

    function setBoxTransparency(pct, silent = false) {
        const n = Math.min(75, Math.max(0, Math.round(pct / 5) * 5));
        boxSlider.value = n;
        boxVal.textContent = `${n}%`;
        if (silent) return;
        clearTimeout(boxTimer);
        boxTimer = setTimeout(
            () => post("/api/tournament/view/settings", { box_opacity: 1 - n / 100 }),
            200
        );
    }

    boxSlider.addEventListener("input",
        () => setBoxTransparency(parseInt(boxSlider.value, 10)));

    // --- Celebration effect toggle (auto-shows on the view when complete) ---

    const celebrationBtn = document.getElementById("btn-celebration");
    let celebrationOn = true;

    function setCelebrationUI(on) {
        celebrationOn = on;
        celebrationBtn.querySelector(".lbl").textContent = `CELEBRATION: ${on ? "ON" : "OFF"}`;
        celebrationBtn.classList.toggle("btn-accent", on);
    }

    celebrationBtn.addEventListener("click", () => {
        setCelebrationUI(!celebrationOn);
        post("/api/tournament/celebration", { enabled: celebrationOn });
    });

    // Reflect server-pushed celebration state (init + other admins' changes).
    function syncCelebration(s) {
        if (!s) return;
        setCelebrationUI(s.enabled !== false);
    }

    // --- Single mode toggle: cycles through three control groups ---
    // One button steps TOURNAMENT -> VIEW HIGHSCORE -> EFFEKT -> (wrap). Only the
    // active group is shown; the label is the mode currently active.

    const modeToggle = document.getElementById("mode-toggle");
    const MODES = [
        { group: "admin-group", label: "TOURNAMENT" },
        { group: "view-group", label: "VIEW HIGHSCORE" },
        { group: "effects-group", label: "EFFEKT" },
    ];
    let modeIndex = 0;

    function applyMode() {
        MODES.forEach((m, i) => {
            document.getElementById(m.group).classList.toggle("hidden", i !== modeIndex);
        });
        modeToggle.textContent = MODES[modeIndex].label;
    }
    modeToggle.addEventListener("click", () => {
        modeIndex = (modeIndex + 1) % MODES.length;
        applyMode();
    });
    applyMode();

    // --- WebSocket wiring -------------------------------------------------

    function syncSeedStatus(bracket) {
        const badge = document.getElementById("seed-status");
        const fixBtn = document.getElementById("btn-fix");
        const resetBtn = document.getElementById("btn-reset");
        const unseedBtn = document.getElementById("btn-unseed");
        const sizeControls = document.getElementById("size-controls");
        const seeded = !!bracket.is_seeded;

        if (badge) {
            // Same format/length style as the LIVE badge (timestamp lives in
            // #bracket-meta) so the two states render identically.
            badge.textContent = seeded ? "● SEED FIXED" : "● LIVE — not fixed";
            badge.classList.toggle("is-fixed", seeded);
            badge.classList.toggle("live", !seeded);
        }
        // Show FIX while live; show UNSEED + RESET only once fixed.
        if (fixBtn) {
            fixBtn.classList.toggle("hidden", seeded);
            fixBtn.classList.toggle("is-active", !seeded);
        }
        if (resetBtn) resetBtn.classList.toggle("hidden", !seeded);
        if (unseedBtn) unseedBtn.classList.toggle("hidden", !seeded);

        // Tournament size is locked once seeded: changing N would reshape a
        // running tournament. Disable every control inside #size-controls and
        // grey it out. UNSEED re-enables it.
        if (sizeControls) {
            sizeControls.classList.toggle("is-locked", seeded);
            sizeControls
                .querySelectorAll("input, button")
                .forEach((el) => {
                    el.disabled = seeded;
                });
        }
    }

    function syncFromBracket(bracket) {
        if (!bracket) return;
        if (typeof bracket.active_count === "number") {
            setSize(bracket.active_count, true);
        }
        disabledIds = new Set(bracket.disabled_user_ids || []);
        syncSeedStatus(bracket);
        renderPlayers();
    }

    const ws = new KioskSocket();
    ws.on("init", (d) => {
        leaderboard = d.leaderboard || [];
        renderBracket(d.bracket);
        syncFromBracket(d.bracket);
        syncViewSettings(d.view_settings);
        syncCelebration(d.celebration);
    });
    ws.on("leaderboard_update", (lb) => {
        leaderboard = lb || [];
        renderPlayers();
    });
    ws.on("bracket_update", (b) => {
        renderBracket(b);
        syncFromBracket(b);
    });
    ws.on("view_settings", syncViewSettings);
    ws.on("celebration", syncCelebration);
    ws.onStatus(setConnStatus);
    ws.connect();
})();
