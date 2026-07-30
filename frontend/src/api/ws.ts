// One multiplexed WebSocket for all live job events (§7A.9 / §7A.10).
// A single connection carries every job's stream; the client subscribes to the job IDs
// it cares about. Auto-reconnects with backoff; re-sends subscriptions on reconnect.

import type { WSClientMessage, WSEvent } from "./types";

type Listener = (ev: WSEvent) => void;
type StatusListener = (status: WsStatus) => void;
export type WsStatus = "connecting" | "open" | "closed";

function wsUrl(): string {
  const base = import.meta.env.VITE_WS_BASE;
  if (base) return base.replace(/\/$/, "") + "/ws/jobs";
  // Same-origin: derive ws(s):// from the page origin. Dev proxy / nginx forwards /ws.
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/jobs`;
}

class JobStream {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<StatusListener>();
  private subscribedAll = false;
  private jobIds = new Set<string>();
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private appPassword = import.meta.env.VITE_APP_PASSWORD || "";
  private status: WsStatus = "closed";

  private ensureConnected() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.setStatus("connecting");
    try {
      // App password (if any) is passed as a query param since browsers can't set WS headers.
      const url = this.appPassword
        ? `${wsUrl()}?app_password=${encodeURIComponent(this.appPassword)}`
        : wsUrl();
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.setStatus("open");
      this.resendSubscriptions();
    };
    this.ws.onmessage = (msg) => {
      let ev: WSEvent;
      try {
        ev = JSON.parse(msg.data);
      } catch {
        return;
      }
      this.listeners.forEach((l) => l(ev));
    };
    this.ws.onclose = () => {
      this.setStatus("closed");
      this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      // onclose will follow and trigger reconnect.
      this.ws?.close();
    };
  }

  private setStatus(s: WsStatus) {
    this.status = s;
    this.statusListeners.forEach((l) => l(s));
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    if (this.listeners.size === 0) return; // nobody listening, don't churn
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 15000);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.ensureConnected();
    }, delay);
  }

  private send(m: WSClientMessage) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(m));
    }
  }

  private resendSubscriptions() {
    if (this.subscribedAll) {
      this.send({ op: "subscribe_all" });
    } else if (this.jobIds.size > 0) {
      this.send({ op: "subscribe", job_ids: [...this.jobIds] });
    }
  }

  getStatus() {
    return this.status;
  }

  onStatus(l: StatusListener): () => void {
    this.statusListeners.add(l);
    l(this.status);
    return () => this.statusListeners.delete(l);
  }

  /** Subscribe a listener to all events. Returns an unsubscribe fn. */
  addListener(l: Listener): () => void {
    this.listeners.add(l);
    this.ensureConnected();
    return () => {
      this.listeners.delete(l);
      if (this.listeners.size === 0) {
        // Keep the socket warm briefly; close if still idle.
        setTimeout(() => {
          if (this.listeners.size === 0) this.ws?.close();
        }, 5000);
      }
    };
  }

  subscribeAll() {
    this.subscribedAll = true;
    this.ensureConnected();
    this.send({ op: "subscribe_all" });
  }

  subscribeJobs(ids: string[]) {
    ids.forEach((id) => this.jobIds.add(id));
    this.ensureConnected();
    this.send({ op: "subscribe", job_ids: ids });
  }
}

// Module-level singleton — one socket for the whole app.
export const jobStream = new JobStream();
