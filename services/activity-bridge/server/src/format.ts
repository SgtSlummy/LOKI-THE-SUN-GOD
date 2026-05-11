import { RoomState, getSyncedPositionSeconds } from "@activity/shared";

export function formatRoomStatus(room: RoomState) {
  const position = getSyncedPositionSeconds(room).toFixed(1);
  const queue = room.queue.length;
  const url = room.currentUrl ? room.currentUrl.slice(0, 120) : "none";
  const scene = room.obs.currentScene ?? "unknown";
  const twitch = room.twitch.live ? "live" : "not live/unknown";

  return [
    `Room: ${room.roomId}`,
    `Status: ${room.status}`,
    `Position: ${position}s`,
    `Current: ${room.currentTitle ?? url}`,
    `Queue: ${queue}`,
    `Locked: ${room.locked ? "yes" : "no"}`,
    `OBS: ${room.obs.connected ? "connected" : "not connected"}, scene=${scene}, streaming=${room.obs.streaming ? "yes" : "no"}`,
    `Twitch: ${twitch}`
  ].join("\n");
}
