import { RoomState, ServerToClientMessage, getSyncedPositionSeconds } from "@activity/shared";
import { setText } from "./dom";

let lastRoom: RoomState | null = null;

export function renderMessage(message: ServerToClientMessage) {
  if (message.type === "ERROR") {
    setText("#connection-status", `Error: ${message.message}`);
    return;
  }

  if (message.type === "ROOM_ENDED") {
    lastRoom = null;
    setText("#connection-status", "Room ended");
    setText("#room-state", "No active room.");
    return;
  }

  if ("room" in message) {
    lastRoom = message.room;
    renderRoom(message.room);
  }
}

export function renderRoom(room: RoomState) {
  setText("#connection-status", `Connected. Playback=${room.status}`);
  setText("#room-badge", `room: ${room.roomId}`);

  const state = {
    roomId: room.roomId,
    hostUserId: room.hostUserId,
    locked: room.locked,
    currentTitle: room.currentTitle,
    currentUrl: room.currentUrl,
    status: room.status,
    positionSeconds: Number(getSyncedPositionSeconds(room).toFixed(1)),
    queueItems: room.queue.length,
    obs: room.obs,
    twitch: room.twitch
  };

  setText("#room-state", JSON.stringify(state, null, 2));
}

export function getLastRoom() {
  return lastRoom;
}
