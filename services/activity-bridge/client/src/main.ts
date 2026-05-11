import "./style.css";
import { PlayerController } from "./player";
import { ActivitySocket } from "./socket";
import { initDiscordActivity } from "./discord";
import { getLastRoom, renderMessage } from "./render";
import { setText } from "./dom";

async function main() {
  const context = await initDiscordActivity();
  setText("#connection-status", "Connecting to backend...");
  setText("#room-badge", `room: ${context.roomId}`);

  const player = new PlayerController();
  const socket = new ActivitySocket();

  socket.onMessage((message) => {
    renderMessage(message);
    player.apply(message);
  });

  await socket.connect();

  socket.send({
    type: "JOIN_ROOM",
    roomId: context.roomId,
    guildId: context.guildId,
    channelId: context.channelId,
    instanceId: context.instanceId,
    userId: context.userId,
    sessionToken: context.sessionToken
  });

  document.querySelector("#play-button")?.addEventListener("click", () => {
    socket.send({ type: "CONTROL_PLAY", roomId: context.roomId, userId: context.userId, sessionToken: context.sessionToken });
  });

  document.querySelector("#pause-button")?.addEventListener("click", () => {
    socket.send({ type: "CONTROL_PAUSE", roomId: context.roomId, userId: context.userId, sessionToken: context.sessionToken });
  });

  document.querySelector("#seek-button")?.addEventListener("click", () => {
    const room = getLastRoom();
    const seconds = room ? 0 : player.currentTime();
    socket.send({
      type: "CONTROL_SEEK",
      roomId: context.roomId,
      seconds,
      userId: context.userId,
      sessionToken: context.sessionToken
    });
  });
}

main().catch((error) => {
  console.error(error);
  setText("#connection-status", `Startup failed: ${String(error)}`);
});
