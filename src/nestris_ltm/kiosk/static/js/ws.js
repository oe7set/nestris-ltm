/* KioskSocket: thin WebSocket client with auto-reconnect + keepalive.
 *
 * Usage:
 *   const ws = new KioskSocket();
 *   ws.on("bracket_update", (data) => ...);
 *   ws.onStatus((connected) => ...);
 *   ws.connect();
 */
class KioskSocket {
    constructor() {
        this._handlers = {};          // type -> fn(data)
        this._statusCb = null;        // fn(connected: bool)
        this._ws = null;
        this._retry = 0;
        this._pingTimer = null;
        this._closed = false;
    }

    on(type, fn) { this._handlers[type] = fn; return this; }
    onStatus(fn) { this._statusCb = fn; return this; }

    connect() {
        this._closed = false;
        const proto = location.protocol === "https:" ? "wss" : "ws";
        const url = `${proto}://${location.host}/ws/kiosk`;
        this._ws = new WebSocket(url);

        this._ws.onopen = () => {
            this._retry = 0;
            if (this._statusCb) this._statusCb(true);
            // Keepalive ping every 25s.
            clearInterval(this._pingTimer);
            this._pingTimer = setInterval(() => this._send({ type: "ping" }), 25000);
        };

        this._ws.onmessage = (evt) => {
            let msg;
            try { msg = JSON.parse(evt.data); } catch { return; }
            const fn = this._handlers[msg.type];
            if (fn) fn(msg.data);
        };

        this._ws.onclose = () => {
            clearInterval(this._pingTimer);
            if (this._statusCb) this._statusCb(false);
            if (!this._closed) this._scheduleReconnect();
        };

        this._ws.onerror = () => { try { this._ws.close(); } catch {} };
    }

    _scheduleReconnect() {
        // Exponential backoff capped at 10s.
        this._retry += 1;
        const delay = Math.min(10000, 500 * Math.pow(1.6, this._retry));
        setTimeout(() => { if (!this._closed) this.connect(); }, delay);
    }

    _send(obj) {
        if (this._ws && this._ws.readyState === WebSocket.OPEN) {
            this._ws.send(JSON.stringify(obj));
        }
    }

    close() { this._closed = true; clearInterval(this._pingTimer); if (this._ws) this._ws.close(); }
}

/* Shared helper used by both pages to reflect the connection dot. */
function setConnStatus(ok) {
    const el = document.getElementById("conn-status");
    if (!el) return;
    el.textContent = ok ? "live" : "offline";
    el.classList.toggle("conn-up", ok);
    el.classList.toggle("conn-down", !ok);
}
