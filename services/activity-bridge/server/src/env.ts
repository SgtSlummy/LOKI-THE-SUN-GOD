import dotenv from "dotenv";

dotenv.config({ path: process.env.ENV_FILE ?? ".env" });

function bool(name: string, fallback = false): boolean {
  const value = process.env[name];
  if (value == null || value === "") return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function numberEnv(name: string, fallback: number): number {
  const value = process.env[name];
  if (!value) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export const env = {
  discordApplicationId: process.env.DISCORD_APPLICATION_ID ?? "",
  discordClientId: process.env.DISCORD_CLIENT_ID ?? "",
  discordClientSecret: process.env.DISCORD_CLIENT_SECRET ?? "",
  discordBotToken: process.env.DISCORD_BOT_TOKEN ?? "",
  discordPublicKey: process.env.DISCORD_PUBLIC_KEY ?? "",
  discordDevGuildId: process.env.DISCORD_DEV_GUILD_ID ?? "",

  host: process.env.SERVER_HOST ?? "0.0.0.0",
  port: numberEnv("SERVER_PORT", numberEnv("PORT", 3001)),
  publicServerOrigin: process.env.PUBLIC_SERVER_ORIGIN ?? "http://localhost:3001",
  publicClientOrigin: process.env.PUBLIC_CLIENT_ORIGIN ?? "http://localhost:5173",
  bridgeToken: process.env.ACTIVITY_BRIDGE_TOKEN ?? "",
  enableDiscordBot: bool("ENABLE_BRIDGE_DISCORD_BOT", false),

  obsWebSocketUrl: process.env.OBS_WEBSOCKET_URL ?? "ws://127.0.0.1:4455",
  obsWebSocketPassword: process.env.OBS_WEBSOCKET_PASSWORD ?? "",
  obsSceneLive: process.env.OBS_SCENE_LIVE ?? "Live",
  obsSceneBrb: process.env.OBS_SCENE_BRB ?? "BRB",
  obsSceneActivity: process.env.OBS_SCENE_ACTIVITY ?? "Activity",

  twitchClientId: process.env.TWITCH_CLIENT_ID ?? "",
  twitchClientSecret: process.env.TWITCH_CLIENT_SECRET ?? "",
  twitchBroadcasterId: process.env.TWITCH_BROADCASTER_ID ?? "",
  twitchAccessToken: process.env.TWITCH_ACCESS_TOKEN ?? "",

  allowActivitySideControls: bool("ALLOW_ACTIVITY_SIDE_CONTROLS", false),
  allowStreamStartStop: bool("ALLOW_STREAM_START_STOP", false)
};

export function requireEnv(value: string, name: string): string {
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}
