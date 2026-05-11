import { EventEmitter } from "node:events";
import {
  CommandResult,
  RoomState,
  createInitialRoom,
  getSyncedPositionSeconds,
  isHttpVideoUrl,
  makeQueueItem
} from "@activity/shared";

type RoomEvents = {
  change: [room: RoomState, reason: string];
  end: [roomId: string];
};

type Listener<K extends keyof RoomEvents> = (...args: RoomEvents[K]) => void;

export class RoomManager {
  private rooms = new Map<string, RoomState>();
  private events = new EventEmitter();

  on<K extends keyof RoomEvents>(event: K, listener: Listener<K>) {
    this.events.on(event, listener as (...args: unknown[]) => void);
    return () => this.events.off(event, listener as (...args: unknown[]) => void);
  }

  getOrCreate(roomId: string, partial: Partial<RoomState> = {}): RoomState {
    const existing = this.rooms.get(roomId);
    if (existing) {
      const merged = {
        ...existing,
        guildId: existing.guildId ?? partial.guildId ?? null,
        channelId: existing.channelId ?? partial.channelId ?? null,
        instanceId: existing.instanceId ?? partial.instanceId ?? null
      };
      this.rooms.set(roomId, merged);
      return merged;
    }

    const room = createInitialRoom(roomId, partial);
    this.rooms.set(roomId, room);
    return room;
  }

  get(roomId: string): RoomState | undefined {
    return this.rooms.get(roomId);
  }

  list(): RoomState[] {
    return [...this.rooms.values()];
  }

  setVideo(roomId: string, url: string, title?: string | null): CommandResult {
    if (!isHttpVideoUrl(url)) {
      return { ok: false, message: "Only http(s) video/source URLs are accepted in this starter." };
    }

    const room = this.getOrCreate(roomId);
    room.currentUrl = url;
    room.currentTitle = title ?? null;
    room.currentQueueItemId = null;
    room.status = "paused";
    room.positionSeconds = 0;
    room.updatedAt = Date.now();
    this.emitChange(room, "set-video");
    return { ok: true, message: "Video/source URL set.", room };
  }

  queue(roomId: string, url: string, userId?: string | null, title?: string | null): CommandResult {
    if (!isHttpVideoUrl(url)) {
      return { ok: false, message: "Only http(s) queue URLs are accepted in this starter." };
    }

    const room = this.getOrCreate(roomId);
    const item = makeQueueItem(url, userId, title);
    room.queue.push(item);
    room.updatedAt = Date.now();
    this.emitChange(room, "queue-update");
    return { ok: true, message: `Queued item ${item.id}.`, room };
  }

  play(roomId: string): CommandResult {
    const room = this.getOrCreate(roomId);
    if (!room.currentUrl) return { ok: false, message: "No current video/source URL. Use /watch set first.", room };
    room.positionSeconds = getSyncedPositionSeconds(room);
    room.status = "playing";
    room.updatedAt = Date.now();
    this.emitChange(room, "play");
    return { ok: true, message: "Playback started.", room };
  }

  pause(roomId: string): CommandResult {
    const room = this.getOrCreate(roomId);
    room.positionSeconds = getSyncedPositionSeconds(room);
    room.status = "paused";
    room.updatedAt = Date.now();
    this.emitChange(room, "pause");
    return { ok: true, message: "Playback paused.", room };
  }

  seek(roomId: string, seconds: number): CommandResult {
    if (!Number.isFinite(seconds) || seconds < 0) {
      return { ok: false, message: "Seek value must be a non-negative number." };
    }

    const room = this.getOrCreate(roomId);
    room.positionSeconds = seconds;
    room.updatedAt = Date.now();
    this.emitChange(room, "seek");
    return { ok: true, message: `Seeked to ${seconds.toFixed(1)} seconds.`, room };
  }

  next(roomId: string): CommandResult {
    const room = this.getOrCreate(roomId);
    const nextItem = room.queue.shift();
    if (!nextItem) return { ok: false, message: "Queue is empty.", room };

    room.currentUrl = nextItem.url;
    room.currentTitle = nextItem.title ?? null;
    room.currentQueueItemId = nextItem.id;
    room.positionSeconds = 0;
    room.status = "paused";
    room.updatedAt = Date.now();
    this.emitChange(room, "next");
    return { ok: true, message: "Loaded next queue item.", room };
  }

  lock(roomId: string, locked: boolean): CommandResult {
    const room = this.getOrCreate(roomId);
    room.locked = locked;
    room.updatedAt = Date.now();
    this.emitChange(room, "lock");
    return { ok: true, message: locked ? "Room locked." : "Room unlocked.", room };
  }

  setHost(roomId: string, hostUserId: string): CommandResult {
    const room = this.getOrCreate(roomId);
    room.hostUserId = hostUserId;
    room.updatedAt = Date.now();
    this.emitChange(room, "host");
    return { ok: true, message: `Host set to ${hostUserId}.`, room };
  }

  setObsStatus(roomId: string, obs: Partial<RoomState["obs"]>, reason = "obs-update"): RoomState {
    const room = this.getOrCreate(roomId);
    room.obs = { ...room.obs, ...obs };
    room.updatedAt = Date.now();
    this.emitChange(room, reason);
    return room;
  }

  setTwitchStatus(roomId: string, twitch: Partial<RoomState["twitch"]>, reason = "twitch-update"): RoomState {
    const room = this.getOrCreate(roomId);
    room.twitch = { ...room.twitch, ...twitch };
    room.updatedAt = Date.now();
    this.emitChange(room, reason);
    return room;
  }

  end(roomId: string): CommandResult {
    const room = this.rooms.get(roomId);
    this.rooms.delete(roomId);
    this.events.emit("end", roomId);
    return { ok: true, message: room ? "Room ended." : "Room did not exist." };
  }

  private emitChange(room: RoomState, reason: string) {
    this.rooms.set(room.roomId, { ...room, queue: [...room.queue], obs: { ...room.obs }, twitch: { ...room.twitch } });
    this.events.emit("change", this.rooms.get(room.roomId), reason);
  }
}

export const rooms = new RoomManager();
