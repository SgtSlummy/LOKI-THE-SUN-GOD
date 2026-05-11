import { env } from "../env.js";
import { logger } from "../logger.js";

export class TwitchService {
  hasCredentials() {
    return Boolean(env.twitchClientId && env.twitchAccessToken && env.twitchBroadcasterId);
  }

  async updateChannelMetadata(input: { title?: string; gameId?: string }) {
    if (!this.hasCredentials()) {
      logger.warn("Twitch credentials missing; skipping channel metadata update");
      return false;
    }

    const body: Record<string, string> = {};
    if (input.title) body.title = input.title;
    if (input.gameId) body.game_id = input.gameId;

    const response = await fetch(`https://api.twitch.tv/helix/channels?broadcaster_id=${env.twitchBroadcasterId}`, {
      method: "PATCH",
      headers: {
        "Client-Id": env.twitchClientId,
        Authorization: `Bearer ${env.twitchAccessToken}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      logger.warn("Twitch channel metadata update failed", { status: response.status, text: await response.text() });
      return false;
    }

    return true;
  }

  async getStreamStatus() {
    if (!this.hasCredentials()) return { live: false };

    const response = await fetch(`https://api.twitch.tv/helix/streams?user_id=${env.twitchBroadcasterId}`, {
      headers: {
        "Client-Id": env.twitchClientId,
        Authorization: `Bearer ${env.twitchAccessToken}`
      }
    });

    if (!response.ok) return { live: false };
    const json = (await response.json()) as { data?: Array<{ title?: string; game_name?: string }> };
    const first = json.data?.[0];
    return {
      live: Boolean(first),
      channelTitle: first?.title ?? null,
      gameName: first?.game_name ?? null
    };
  }
}

export const twitchService = new TwitchService();
