import { ClientToServerMessage, ServerToClientMessage } from "@activity/shared";
import { clientEnv } from "./env";

export class ActivitySocket {
  private ws?: WebSocket;
  private listeners = new Set<(message: ServerToClientMessage) => void>();

  connect() {
    const url = `${clientEnv.wsOrigin.replace(/\/$/, "")}/ws`;
    this.ws = new WebSocket(url);

    this.ws.addEventListener("message", (event) => {
      try {
        const message = JSON.parse(event.data) as ServerToClientMessage;
        for (const listener of this.listeners) listener(message);
      } catch (error) {
        console.warn("Invalid websocket message", error);
      }
    });

    return new Promise<void>((resolve, reject) => {
      if (!this.ws) return reject(new Error("WebSocket not created"));
      this.ws.addEventListener("open", () => resolve(), { once: true });
      this.ws.addEventListener("error", () => reject(new Error("WebSocket failed")), { once: true });
    });
  }

  onMessage(listener: (message: ServerToClientMessage) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(message: ClientToServerMessage) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify(message));
  }
}
