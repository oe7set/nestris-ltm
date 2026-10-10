// Changing a heart of a 1-vs-1 match, with "undo" in the confirmation toast.

import { api } from "./api";
import { t } from "./i18n.svelte";
import { toasts } from "./toast.svelte";

export async function changeHeart(
  matchId: string,
  playerId: number,
  playerName: string,
  action: "lose" | "gain",
  after?: () => void | Promise<void>,
): Promise<void> {
  const res = await api<{ event_id?: number }>(`/api/tournament/matches/${matchId}/lives`, {
    method: "POST",
    body: { player_id: playerId, action },
  });
  const text = t(action === "lose" ? "hearts.lost" : "hearts.gained", { name: playerName });
  if (res.event_id === undefined) {
    toasts.ok(text);
    return;
  }
  const eventId = res.event_id;
  toasts.withAction(text, {
    label: t("common.undo"),
    run: async () => {
      await api(`/api/tournament/lives/undo/${eventId}`, { method: "POST" });
      toasts.ok(t("hearts.undone"));
      await after?.();
    },
  });
}
