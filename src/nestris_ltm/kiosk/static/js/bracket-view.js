/* Renders the tournament bracket (right column / admin main area).
 *
 * The same renderer serves the read-only view and the editable admin page.
 * Admin behaviour is injected via window.__bracketAdmin, an optional object:
 *   { onPickWinner(matchId, userId), onClearWinner(matchId) }
 * When present (and the bracket is seeded), REAL-match slots become clickable
 * and decided matches show a small clear (×) control.
 *
 * The bracket size is dynamic: the server sends a capacity-sized tree (2/4/8/
 * 16/32/64 slots → 1..6 rounds) with each round already named. We render
 * whatever rounds arrive; round titles come from `round.name` (single source of
 * truth on the server). Bye/dead matches are hidden but keep their layout space.
 *
 * The re-seed animation is delegated to flip.js (`window.Flip`) when available:
 * it animates player boxes across the whole viewport (curved flights, enter from
 * / exit to the highscore list or screen edge). Without it we just swap the DOM.
 */

function renderBracket(bracket) {
    const container = document.getElementById("bracket");
    if (!container || !bracket) return;

    const doRender = () => buildBracket(container, bracket);

    if (window.Flip) {
        window.Flip.animatedRender(doRender);
    } else {
        doRender();
    }
}

function buildBracket(container, bracket) {
    const isAdmin = !!window.__bracketAdmin;

    container.innerHTML = "";
    // Expose capacity so CSS can scale the geometry for large brackets.
    container.dataset.capacity = bracket.rounds.length
        ? 1 << bracket.rounds.length
        : 0;
    updateMeta(bracket);

    for (const round of bracket.rounds) {
        const col = document.createElement("div");
        col.className = "round";
        const title = document.createElement("h3");
        title.textContent = round.name;
        col.appendChild(title);

        const matches = document.createElement("div");
        matches.className = "matches";
        for (const match of round.matches) {
            matches.appendChild(renderMatch(match, isAdmin, bracket.is_seeded));
        }
        col.appendChild(matches);
        container.appendChild(col);
    }

    container.appendChild(renderPodium(bracket, isAdmin));
}

function updateMeta(bracket) {
    const meta = document.getElementById("bracket-meta");
    if (!meta) return;
    const capacity = bracket.rounds.length ? 1 << bracket.rounds.length : 0;
    const size = `size ${bracket.active_count} (${capacity}-slot tree)`;
    if (!bracket.is_seeded) {
        meta.textContent = `auto-fill (live) · ${size} · press FIX to lock`;
    } else {
        const ts = bracket.seeded_at ? new Date(bracket.seeded_at).toLocaleString() : "";
        meta.textContent = `seeded ${ts} · ${size}`;
    }
}

function renderMatch(match, isAdmin, isSeeded) {
    const box = document.createElement("div");
    box.className = `match kind-${match.kind}`;
    // Only padding matches beyond the tournament size N are hidden (kept in the
    // layout). Every in-size match — including byes and not-yet-filled (TBD)
    // ones — stays visible so the full N-tree shows regardless of player count.
    if (match.hidden) {
        box.classList.add("match-hidden");
    }
    box.dataset.matchId = match.match_id;

    box.appendChild(renderSlot(match, match.player1, isAdmin, isSeeded));

    const vs = document.createElement("div");
    vs.className = "vs";
    vs.textContent = "VS";
    box.appendChild(vs);

    box.appendChild(renderSlot(match, match.player2, isAdmin, isSeeded));
    return box;
}

function renderSlot(match, player, isAdmin, isSeeded) {
    const slot = document.createElement("div");
    slot.className = "slot";

    if (!player) {
        slot.classList.add("empty");
        slot.innerHTML = `<span class="left"><span class="seed"></span><span class="name">TBD</span></span>`;
        return slot;
    }

    // Tag with player id so the FLIP animation can track this box across renders.
    slot.dataset.playerId = player.user_id;

    const winner = match.winner || match.auto_winner;
    const isWinner = winner && player.user_id === winner.user_id;
    if (player.status === "AUTO_LOST") slot.classList.add("auto-lost");
    if (isWinner) slot.classList.add("winner");

    slot.innerHTML = `
        <span class="left">
            <span class="seed">${player.seed ?? ""}</span>
            <span class="name">${escapeHtml(player.nickname)}</span>
        </span>
        <span class="pts">${(player.highscore ?? 0).toLocaleString("en-US")}</span>
    `;

    // Admin: winners can only be set once the bracket is frozen (seeded).
    if (isAdmin && isSeeded && match.kind === "REAL" && player.status === "ACTIVE") {
        slot.classList.add("clickable");
        slot.addEventListener("click", () =>
            window.__bracketAdmin.onPickWinner(match.match_id, player.user_id)
        );
        if (isWinner) {
            const x = document.createElement("span");
            x.className = "clear-btn";
            x.textContent = "×";
            x.title = "clear winner";
            x.addEventListener("click", (e) => {
                e.stopPropagation();
                window.__bracketAdmin.onClearWinner(match.match_id);
            });
            slot.appendChild(x);
        }
    }
    return slot;
}

function renderPodium(bracket, isAdmin) {
    const champ = bracket.rounds[bracket.rounds.length - 1].matches[0];
    const winner = champ.winner || champ.auto_winner;
    let runnerUp = null;
    if (winner) {
        if (champ.player1 && champ.player1.user_id === winner.user_id) runnerUp = champ.player2;
        else if (champ.player2 && champ.player2.user_id === winner.user_id) runnerUp = champ.player1;
    }
    const tpm = bracket.third_place_match;
    const third = tpm.winner || tpm.auto_winner;

    const podium = document.createElement("div");
    podium.className = "podium";
    podium.innerHTML = `
        <div class="crown gold">
            <div class="icon"><img class="tw-icon" src="/kiosk/static/icons/trophy.svg" alt=""></div>
            <div class="place">CHAMPION</div>
            <div class="who">${winner ? escapeHtml(winner.nickname) : "—"}</div>
        </div>
        <div class="crown silver">
            <div class="icon"><img class="tw-icon" src="/kiosk/static/icons/medal-silver.svg" alt=""></div>
            <div class="place">RUNNER-UP</div>
            <div class="who">${runnerUp ? escapeHtml(runnerUp.nickname) : "—"}</div>
        </div>
        <div class="crown bronze">
            <div class="icon"><img class="tw-icon" src="/kiosk/static/icons/medal-bronze.svg" alt=""></div>
            <div class="place">THIRD</div>
            <div class="who">${third ? escapeHtml(third.nickname) : "—"}</div>
        </div>
    `;

    // The third-place match is a real, visible, clickable match (when it exists,
    // i.e. capacity >= 4 → not DEAD). Render it under the crowns.
    if (tpm.kind !== "DEAD") {
        const label = document.createElement("div");
        label.className = "tpm-label";
        label.textContent = "3RD PLACE MATCH";
        podium.appendChild(label);
        podium.appendChild(renderMatch(tpm, isAdmin, bracket.is_seeded));
    }
    return podium;
}

/* Fallback escapeHtml when leaderboard.js isn't loaded (admin page). */
if (typeof escapeHtml === "undefined") {
    window.escapeHtml = function (s) {
        const div = document.createElement("div");
        div.textContent = s ?? "";
        return div.innerHTML;
    };
}
