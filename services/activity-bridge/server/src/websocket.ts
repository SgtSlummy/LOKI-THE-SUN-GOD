import http from "node:http";
import { WebSocket, WebSocketServer } from "ws";
import {
  ClientToServerMessage,
  RoomState,
  ServerToClientMessage,
  createRoomId,
  safeJsonParse
} from "@activity/shared";
import { getActivitySession } from "./activitySessions.js";
import { env } from "./env.js";
import { logger } from "./logger.js";
import { RoomManager } from "./rooms.js";

type ClientMeta = {
  roomId?: string;
  userId?: string | null;
  sessionToken?: string | null;
};

function send(ws: WebSocket, message: ServerToClientMessage) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

function hasString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isClientMessage(message: unknown): message is ClientToServerMessage {
  if (!isRecord(message) || typeof message.type !== "string") return false;
  if (message.type === "JOIN_ROOM") return true;
  if (message.type === "REQUEST_STATE" || message.type === "CLIENT_READY") return hasString(message.roomId);
  if (message.type === "CONTROL_PLAY" || message.type === "CONTROL_PAUSE") return hasString(message.roomId);
  if (message.type === "CONTROL_SEEK") {
    return hasString(message.roomId) && typeof message.seconds === "number" && Number.isFinite(message.seconds);
  }
  return false;
}

export function attachWebSocketServer(server: http.Server, rooms: RoomManager) {
  const wss = new WebSocketServer({ server, path: "/ws" });
  const clients = new Map<WebSocket, ClientMeta>();

  function broadcast(roomId: string, message: ServerToClientMessage) {
    for (const [client, meta] of clients) {
      if (meta.roomId === roomId) send(client, message);
    }
  }

  function verifiedUserId(meta: ClientMeta, sessionToken?: string | null): string | null {
    const session = getActivitySession(sessionToken ?? meta.sessionToken);
    return session?.userId ?? null;
  }

  function canControlFromActivity(room: RoomState | undefined, userId: string | null): string | null {
    if (!room) return "Room does not exist.";
    if (!userId) return "Activity-side controls require an authenticated Discord session.";
    if (room.locked && room.hostUserId !== userId) return "Room is locked to the assigned host.";
    if (room.hostUserId && room.hostUserId !== userId) return "Only the assigned host can control this room.";
    return null;
  }

  rooms.on("change", (room, reason) => {
    const type: ServerToClientMessage["type"] =
      reason === "play" ? "PLAY" :
      reason === "pause" ? "PAUSE" :
      reason === "seek" ? "SEEK" :
      reason === "set-video" || reason === "next" ? "SET_VIDEO" :
      reason === "queue-update" ? "QUEUE_UPDATE" :
      reason.startsWith("obs") ? "OBS_UPDATE" :
      reason.startsWith("twitch") ? "TWITCH_UPDATE" :
      "ROOM_STATE";

    broadcast(room.roomId, { type, room } as ServerToClientMessage);
  });

  rooms.on("end", (roomId) => {
    broadcast(roomId, { type: "ROOM_ENDED", roomId });
  });

  wss.on("connection", (ws, request) => {
    const origin = request.headers.origin;
    logger.info("Activity websocket connected", { origin });
    clients.set(ws, {});

    ws.on("message", (raw) => {
      const parsed = safeJsonParse<unknown>(raw.toString());
      if (!parsed) {
        send(ws, { type: "ERROR", message: "Invalid JSON message." });
        return;
      }
      if (!isClientMessage(parsed)) {
        send(ws, { type: "ERROR", message: "Unsupported or malformed client message." });
        return;
      }
      const message = parsed;

      const meta = clients.get(ws) ?? {};

      if (message.type === "JOIN_ROOM") {
        const roomId = message.roomId || createRoomId(message.guildId, message.channelId, message.instanceId);
        const sessionUserId = verifiedUserId(meta, message.sessionToken);
        const room = rooms.getOrCreate(roomId, {
          guildId: message.guildId,
          channelId: message.channelId,
          instanceId: message.instanceId
        });
        clients.set(ws, { roomId, userId: sessionUserId ?? message.userId, sessionToken: message.sessionToken });
        send(ws, { type: "ROOM_STATE", room });
        return;
      }

      if (message.type === "REQUEST_STATE") {
        const room = rooms.getOrCreate(message.roomId);
        clients.set(ws, { ...meta, roomId: message.roomId });
        send(ws, { type: "ROOM_STATE", room });
        return;
      }

      if (!env.allowActivitySideControls && message.type.startsWith("CONTROL_")) {
        send(ws, { type: "ERROR", message: "Activity-side controls are disabled." });
        return;
      }

      if (message.type === "CONTROL_PLAY") {
        const userId = verifiedUserId(meta, message.sessionToken);
        const controlError = canControlFromActivity(rooms.get(message.roomId), userId);
        if (controlError) {
          send(ws, { type: "ERROR", message: controlError });
          return;
        }
        const result = rooms.play(message.roomId);
        if (!result.ok) send(ws, { type: "ERROR", message: result.message });
        return;
      }

      if (message.type === "CONTROL_PAUSE") {
        const userId = verifiedUserId(meta, message.sessionToken);
        const controlError = canControlFromActivity(rooms.get(message.roomId), userId);
        if (controlError) {
          send(ws, { type: "ERROR", message: controlError });
          return;
        }
        const result = rooms.pause(message.roomId);
        if (!result.ok) send(ws, { type: "ERROR", message: result.message });
        return;
      }

      if (message.type === "CONTROL_SEEK") {
        const userId = verifiedUserId(meta, message.sessionToken);
        const controlError = canControlFromActivity(rooms.get(message.roomId), userId);
        if (controlError) {
          send(ws, { type: "ERROR", message: controlError });
          return;
        }
        const result = rooms.seek(message.roomId, message.seconds);
        if (!result.ok) send(ws, { type: "ERROR", message: result.message });
      }
    });

    ws.on("close", () => clients.delete(ws));
  });

  return { wss, broadcast };
}
