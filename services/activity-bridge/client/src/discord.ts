import { DiscordSDK } from "@discord/embedded-app-sdk";
import { createRoomId } from "@activity/shared";
import { clientEnv } from "./env";

export type ActivityContext = {
  sdk?: DiscordSDK;
  guildId?: string | null;
  channelId?: string | null;
  instanceId?: string | null;
  userId?: string | null;
  sessionToken?: string | null;
  roomId: string;
};

export async function initDiscordActivity(): Promise<ActivityContext> {
  if (!clientEnv.discordClientId) {
    const roomId = createRoomId(null, null, "local-dev");
    return { roomId, guildId: null, channelId: null, instanceId: "local-dev", userId: "local-user" };
  }

  const sdk = new DiscordSDK(clientEnv.discordClientId);
  await sdk.ready();

  let userId: string | null = null;
  let sessionToken: string | null = null;

  try {
    const { code } = await sdk.commands.authorize({
      client_id: clientEnv.discordClientId,
      response_type: "code",
      state: crypto.randomUUID(),
      prompt: "none",
      scope: ["identify", "guilds"]
    });

    const tokenResponse = await fetch(`${clientEnv.serverOrigin}/api/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code })
    });

    if (tokenResponse.ok) {
      const token = await tokenResponse.json();
      const auth = await sdk.commands.authenticate({ access_token: token.access_token });
      userId = auth.user?.id ?? null;
      sessionToken = token.activity_session_token ?? null;
    }
  } catch (error) {
    console.warn("Discord Activity authentication skipped", error);
  }

  const guildId = sdk.guildId ?? null;
  const channelId = sdk.channelId ?? null;
  const instanceId = sdk.instanceId ?? null;
  const roomId = createRoomId(guildId, channelId, instanceId);

  return { sdk, guildId, channelId, instanceId, userId, sessionToken, roomId };
}
