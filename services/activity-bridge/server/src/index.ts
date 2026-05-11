import http from "node:http";
import express from "express";
import { env } from "./env.js";
import { logger } from "./logger.js";
import { rooms } from "./rooms.js";
import { attachWebSocketServer } from "./websocket.js";
import { startBot } from "./bot.js";
import { tokenRouter } from "./routes/token.js";
import { roomRouter } from "./routes/rooms.js";

const app = express();

app.use(express.json());
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", env.publicClientOrigin || "*");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type,Authorization");
  if (req.method === "OPTIONS") {
    res.status(204).end();
    return;
  }
  next();
});

app.get("/health", (_req, res) => {
  res.json({
    ok: true,
    service: "activity-bridge",
    discordBotEnabled: env.enableDiscordBot,
    apiAuthConfigured: Boolean(env.bridgeToken),
    activitySideControls: env.allowActivitySideControls,
    streamStartStopEnabled: env.allowStreamStartStop,
    time: new Date().toISOString()
  });
});

app.get("/healthz", (_req, res) => {
  res.json({
    ok: true,
    service: "activity-bridge",
    discordBotEnabled: env.enableDiscordBot,
    apiAuthConfigured: Boolean(env.bridgeToken),
    activitySideControls: env.allowActivitySideControls,
    streamStartStopEnabled: env.allowStreamStartStop,
    time: new Date().toISOString()
  });
});

app.use("/api", tokenRouter);
app.use("/api", roomRouter(rooms));

const server = http.createServer(app);
attachWebSocketServer(server, rooms);

server.listen(env.port, env.host, () => {
  logger.info("Server listening", { host: env.host, port: env.port });
});

if (env.enableDiscordBot) {
  void startBot(rooms);
} else {
  logger.info("Discord gateway bot disabled; LOKI Python owns Discord commands.");
}
