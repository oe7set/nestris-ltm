// Copy text to the clipboard.
//
// The async Clipboard API only exists on secure origins: it works in the
// desktop app (http://127.0.0.1) and on https, but not when the admin UI is
// opened from another PC over plain http://<host-ip>:7990. There the old
// execCommand("copy") on a hidden text area still works.

export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // denied (permissions, focus): try the fallback below
    }
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    if (!document.execCommand("copy")) throw new Error("copy failed");
  } finally {
    area.remove();
  }
}
