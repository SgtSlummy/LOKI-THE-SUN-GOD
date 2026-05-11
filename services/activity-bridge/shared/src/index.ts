export type PlaybackStatus = "idle" | "playing" | "paused" | "ended";

export type StreamTarget = "twitch" | "discord-go-live" | "obs-recording";

export type QueueItem = {
  id: string;
  url: string;
  title?: string;
  addedByUserId?: string;
  addedAt: number;
};

export type RoomState = {
  roomId: string;
  guildId?: string | null;
  channelId?: string | null;
  instanceId?: string | null;
  hostUserId?: string | null;
  locked: boolean;
  currentUrl?: string | null;
  currentTitle?: string | null;
  currentQueueItemId?: string | null;
  status: PlaybackStatus;
  positionSeconds: number;
  updatedAt: number;
  queue: QueueItem[];
  obs: {
    connected: boolean;
    currentScene?: string | null;
    streaming?: boolean;
    recording?: boolean;
  };
  twitch: {
    channelTitle?: string | null;
    gameName?: string | null;
    live?: boolean;
  };
};

export type ServerToClientMessage =
  | { type: "ROOM_STATE"; room: RoomState }
  | { type: "PLAY"; room: RoomState }
  | { type: "PAUSE"; room: RoomState }
  | { type: "SEEK"; room: RoomState }
  | { type: "SET_VIDEO"; room: RoomState }
  | { type: "QUEUE_UPDATE"; room: RoomState }
  | { type: "OBS_UPDATE"; room: RoomState }
  | { type: "TWITCH_UPDATE"; room: RoomState }
  | { type: "ROOM_ENDED"; roomId: string }
  | { type: "ERROR"; message: string; code?: string };

export type ClientToServerMessage =
  | { type: "JOIN_ROOM"; roomId: string; guildId?: string | null; channelId?: string | null; instanceId?: string | null; userId?: string | null; sessionToken?: string | null }
  | { type: "REQUEST_STATE"; roomId: string }
  | { type: "CLIENT_READY"; roomId: string }
  | { type: "CONTROL_PLAY"; roomId: string; userId?: string | null; sessionToken?: string | null }
  | { type: "CONTROL_PAUSE"; roomId: string; userId?: string | null; sessionToken?: string | null }
  | { type: "CONTROL_SEEK"; roomId: string; seconds: number; userId?: string | null; sessionToken?: string | null };

export type CommandResult = {
  ok: boolean;
  message: string;
  room?: RoomState;
};

export function createRoomId(guildId?: string | null, channelId?: string | null, instanceId?: string | null): string {
  if (guildId && channelId) return `${guildId}:${channelId}`;
  if (instanceId) return `activity:${instanceId}`;
  return "local:default";
}

export function createInitialRoom(roomId: string, partial: Partial<RoomState> = {}): RoomState {
  const now = Date.now();

  return {
    roomId,
    guildId: partial.guildId ?? null,
    channelId: partial.channelId ?? null,
    instanceId: partial.instanceId ?? null,
    hostUserId: partial.hostUserId ?? null,
    locked: partial.locked ?? false,
    currentUrl: partial.currentUrl ?? null,
    currentTitle: partial.currentTitle ?? null,
    currentQueueItemId: partial.currentQueueItemId ?? null,
    status: partial.status ?? "idle",
    positionSeconds: partial.positionSeconds ?? 0,
    updatedAt: partial.updatedAt ?? now,
    queue: partial.queue ?? [],
    obs: {
      connected: partial.obs?.connected ?? false,
      currentScene: partial.obs?.currentScene ?? null,
      streaming: partial.obs?.streaming ?? false,
      recording: partial.obs?.recording ?? false
    },
    twitch: {
      channelTitle: partial.twitch?.channelTitle ?? null,
      gameName: partial.twitch?.gameName ?? null,
      live: partial.twitch?.live ?? false
    }
  };
}

export function getSyncedPositionSeconds(room: RoomState, now = Date.now()): number {
  if (room.status !== "playing") return room.positionSeconds;
  const elapsed = Math.max(0, (now - room.updatedAt) / 1000);
  return room.positionSeconds + elapsed;
}

export function safeJsonParse<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function makeQueueItem(url: string, addedByUserId?: string | null, title?: string | null): QueueItem {
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    url,
    title: title ?? undefined,
    addedByUserId: addedByUserId ?? undefined,
    addedAt: Date.now()
  };
}

export function isHttpVideoUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}
