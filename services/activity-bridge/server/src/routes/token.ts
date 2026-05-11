import { Router } from "express";
import { createActivitySession } from "../activitySessions.js";
import { env } from "../env.js";

export const tokenRouter = Router();

async function fetchDiscordUserId(accessToken: string): Promise<string | null> {
  const response = await fetch("https://discord.com/api/users/@me", {
    headers: { Authorization: `Bearer ${accessToken}` }
  });
  if (!response.ok) return null;
  const payload = (await response.json()) as { id?: unknown };
  return typeof payload.id === "string" ? payload.id : null;
}

tokenRouter.post("/token", async (req, res) => {
  const code = typeof req.body?.code === "string" ? req.body.code : "";
  if (!code) {
    res.status(400).json({ error: "missing_code" });
    return;
  }

  if (!env.discordClientId || !env.discordClientSecret) {
    res.status(500).json({ error: "discord_oauth_not_configured" });
    return;
  }

  try {
    const response = await fetch("https://discord.com/api/oauth2/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: env.discordClientId,
        client_secret: env.discordClientSecret,
        grant_type: "authorization_code",
        code
      })
    });

    const payload = (await response.json()) as Record<string, unknown>;
    const accessToken = typeof payload.access_token === "string" ? payload.access_token : "";
    const userId = accessToken ? await fetchDiscordUserId(accessToken) : null;
    if (userId) {
      const session = createActivitySession(userId);
      res.status(response.status).json({
        ...payload,
        activity_session_token: session.token,
        activity_session_expires_at: session.expiresAt,
        user_id: userId
      });
      return;
    }
    res.status(response.status).json(payload);
  } catch {
    res.status(502).json({ error: "discord_oauth_exchange_failed" });
  }
});
