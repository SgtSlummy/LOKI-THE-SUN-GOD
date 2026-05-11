export const clientEnv = {
  discordClientId: import.meta.env.VITE_DISCORD_CLIENT_ID || "",
  serverOrigin: import.meta.env.VITE_SERVER_ORIGIN || window.location.origin,
  wsOrigin: import.meta.env.VITE_WS_ORIGIN || `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`
};
