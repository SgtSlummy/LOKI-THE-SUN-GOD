import { RoomState, ServerToClientMessage, getSyncedPositionSeconds } from "@activity/shared";
import { mustGet } from "./dom";

export class PlayerController {
  private player = mustGet<HTMLVideoElement>("#player");

  apply(message: ServerToClientMessage) {
    if (message.type === "ERROR") {
      console.warn(message.message);
      return;
    }

    if (message.type === "ROOM_ENDED") {
      this.player.pause();
      this.player.removeAttribute("src");
      this.player.load();
      return;
    }

    if (!("room" in message)) return;
    const room = message.room;

    if (room.currentUrl && this.player.src !== room.currentUrl) {
      this.player.src = room.currentUrl;
      this.player.load();
    }

    if (message.type === "PLAY") {
      this.syncTo(room);
      void this.player.play().catch((error) => console.warn("play failed", error));
      return;
    }

    if (message.type === "PAUSE") {
      this.player.pause();
      this.player.currentTime = room.positionSeconds;
      return;
    }

    if (message.type === "SEEK") {
      this.player.currentTime = room.positionSeconds;
      return;
    }

    if (message.type === "SET_VIDEO" || message.type === "ROOM_STATE") {
      this.syncTo(room);
    }
  }

  syncTo(room: RoomState) {
    if (!room.currentUrl) return;
    const target = getSyncedPositionSeconds(room);
    if (Number.isFinite(target) && Math.abs(this.player.currentTime - target) > 1.5) {
      this.player.currentTime = target;
    }

    if (room.status === "playing" && this.player.paused) {
      void this.player.play().catch(() => undefined);
    }

    if (room.status === "paused" && !this.player.paused) {
      this.player.pause();
    }
  }

  currentTime() {
    return this.player.currentTime;
  }
}
