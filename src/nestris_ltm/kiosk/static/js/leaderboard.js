/* Renders the live highscore list and aggregate stats (left column). */

function fmt(n) {
    return (n ?? 0).toLocaleString("en-US");
}

// User ids the admin has disabled (excluded from the tournament). Sourced from
// bracket.disabled_user_ids so the highscore list can flag them as "not playing".
let disabledIds = new Set();

// Replace the disabled set; returns true if it actually changed (so the caller
// can re-render the list only when needed).
function setDisabledIds(ids) {
    const next = new Set(ids || []);
    let changed = next.size !== disabledIds.size;
    if (!changed) {
        for (const id of next) {
            if (!disabledIds.has(id)) {
                changed = true;
                break;
            }
        }
    }
    disabledIds = next;
    return changed;
}

function renderLeaderboard(entries) {
    const list = document.getElementById("leaderboard");
    if (!list) return;
    list.innerHTML = "";
    for (const e of entries) {
        const li = document.createElement("li");
        const isDisabled = disabledIds.has(e.user_id);
        li.className =
            "lb-row" +
            (e.rank <= 3 ? ` top${e.rank}` : "") +
            (isDisabled ? " disabled" : "");
        // Anchor for the cross-region flight animation (list row <-> bracket box).
        if (e.user_id != null) li.dataset.playerId = e.user_id;
        // A disabled player isn't competing in the bracket -> show the OUT tag
        // instead of the live dot (the two states are mutually exclusive).
        const marker = isDisabled
            ? '<span class="out-badge" title="nicht im Turnier">OUT</span>'
            : e.is_live
              ? '<span class="live-dot" title="LIVE"></span>'
              : "";
        li.innerHTML = `
            <span class="rank col-span-1">${e.rank}</span>
            <span class="name col-span-6 truncate">${marker}${escapeHtml(e.nickname)}</span>
            <span class="score col-span-3">${fmt(e.score)}</span>
            <span class="col-span-2 text-right text-muted">${e.level ?? "—"}</span>
        `;
        list.appendChild(li);
    }
}

function renderStats(stats) {
    const grid = document.getElementById("stats-grid");
    if (!grid) return;
    const cards = [
        { lbl: "GAMES", val: fmt(stats.total_games) },
        { lbl: "PLAYERS", val: fmt(stats.active_players) },
        { lbl: "AVG", val: fmt(Math.round(stats.avg_score)) },
    ];
    grid.innerHTML = cards
        .map(
            (c) => `<div class="stat-card"><div class="val">${c.val}</div>
                    <div class="lbl">${c.lbl}</div></div>`
        )
        .join("");
}

function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s ?? "";
    return div.innerHTML;
}
