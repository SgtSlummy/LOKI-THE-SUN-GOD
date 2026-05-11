import {
  ButtonInteraction,
  ChatInputCommandInteraction,
  Client,
  GatewayIntentBits,
  Interaction,
  Partials
} from "discord.js";
import { createRoomId } from "@activity/shared";
import { controlButtons } from "./commands.js";
import { env } from "./env.js";
import { formatRoomStatus } from "./format.js";
import { logger } from "./logger.js";
import { canControlRoom } from "./permissions.js";
import { RoomManager } from "./rooms.js";
import { obsService } from "./services/obs.js";
import { twitchService } from "./services/twitch.js";

function getRoomId(interaction: ChatInputCommandInteraction | ButtonInteraction) {
  return createRoomId(interaction.guildId, interaction.channelId, undefined);
}

async function replyCommand(interaction: ChatInputCommandInteraction | ButtonInteraction, message: string, ephemeral = false) {
  if (interaction.deferred || interaction.replied) {
    await interaction.followUp({ content: message, ephemeral });
  } else {
    await interaction.reply({ content: message, ephemeral });
  }
}

async function handleWatchCommand(interaction: ChatInputCommandInteraction, rooms: RoomManager) {
  const subcommand = interaction.options.getSubcommand();
  const roomId = getRoomId(interaction);
  const room = rooms.getOrCreate(roomId, { guildId: interaction.guildId, channelId: interaction.channelId });

  const controlRequired = !["status"].includes(subcommand);
  if (controlRequired && room.locked && !canControlRoom(interaction, room)) {
    await replyCommand(interaction, "This room is locked. Only the host or server moderators can control it.", true);
    return;
  }

  if (subcommand === "status") {
    const obsStatus = await obsService.getStatus().catch(() => null);
    if (obsStatus) rooms.setObsStatus(roomId, obsStatus);

    const twitchStatus = await twitchService.getStreamStatus().catch(() => null);
    if (twitchStatus) rooms.setTwitchStatus(roomId, twitchStatus);

    await interaction.reply({
      content: `\`\`\`text\n${formatRoomStatus(rooms.getOrCreate(roomId))}\n\`\`\``,
      components: [controlButtons()]
    });
    return;
  }

  if (subcommand === "set") {
    const url = interaction.options.getString("url", true);
    const title = interaction.options.getString("title", false);
    const result = rooms.setVideo(roomId, url, title);
    await interaction.reply({ content: result.message, components: result.ok ? [controlButtons()] : [] });
    return;
  }

  if (subcommand === "queue") {
    const url = interaction.options.getString("url", true);
    const title = interaction.options.getString("title", false);
    const result = rooms.queue(roomId, url, interaction.user.id, title);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "play") {
    const result = rooms.play(roomId);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "pause") {
    const result = rooms.pause(roomId);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "seek") {
    const seconds = interaction.options.getNumber("seconds", true);
    const result = rooms.seek(roomId, seconds);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "next") {
    const result = rooms.next(roomId);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "lock") {
    const enabled = interaction.options.getBoolean("enabled", true);
    const result = rooms.lock(roomId, enabled);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "host") {
    const user = interaction.options.getUser("user", true);
    const result = rooms.setHost(roomId, user.id);
    await replyCommand(interaction, result.message);
    return;
  }

  if (subcommand === "scene") {
    const sceneName = interaction.options.getString("name", true);
    await interaction.deferReply();
    const ok = await obsService.setScene(sceneName);
    const status = await obsService.getStatus().catch(() => null);
    if (status) rooms.setObsStatus(roomId, status, "obs-scene");
    await interaction.editReply(ok ? `OBS scene switched to ${sceneName}.` : "OBS is not connected; scene switch skipped.");
    return;
  }

  if (subcommand === "overlay") {
    const sceneName = interaction.options.getString("scene", true);
    const sourceName = interaction.options.getString("source", true);
    const visible = interaction.options.getBoolean("visible", true);
    await interaction.deferReply();
    const ok = await obsService.setInputEnabled(sceneName, sourceName, visible);
    const status = await obsService.getStatus().catch(() => null);
    if (status) rooms.setObsStatus(roomId, status, "obs-overlay");
    await interaction.editReply(ok ? `OBS source ${sourceName} visibility set to ${visible}.` : "OBS is not connected; overlay update skipped.");
    return;
  }

  if (subcommand === "title") {
    const text = interaction.options.getString("text", true);
    const obsSource = interaction.options.getString("obs_source", false);
    await interaction.deferReply();

    const [twitchOk, obsOk] = await Promise.all([
      twitchService.updateChannelMetadata({ title: text }).catch(() => false),
      obsSource ? obsService.setText(obsSource, text).catch(() => false) : Promise.resolve(false)
    ]);

    rooms.setTwitchStatus(roomId, { channelTitle: text }, "twitch-title");
    const status = await obsService.getStatus().catch(() => null);
    if (status) rooms.setObsStatus(roomId, status, "obs-title");

    await interaction.editReply(`Title command processed. Twitch=${twitchOk ? "updated" : "skipped"}, OBS=${obsSource ? (obsOk ? "updated" : "skipped") : "no source provided"}.`);
    return;
  }

  if (subcommand === "stream-start") {
    await interaction.deferReply();
    const ok = await obsService.startStreaming();
    const status = await obsService.getStatus().catch(() => null);
    if (status) rooms.setObsStatus(roomId, status, "obs-stream");
    await interaction.editReply(ok ? "OBS streaming started." : "Stream start skipped. Check OBS connection and ALLOW_STREAM_START_STOP.");
    return;
  }

  if (subcommand === "stream-stop") {
    await interaction.deferReply();
    const ok = await obsService.stopStreaming();
    const status = await obsService.getStatus().catch(() => null);
    if (status) rooms.setObsStatus(roomId, status, "obs-stream");
    await interaction.editReply(ok ? "OBS streaming stopped." : "Stream stop skipped. Check OBS connection and ALLOW_STREAM_START_STOP.");
    return;
  }

  if (subcommand === "end") {
    const result = rooms.end(roomId);
    await replyCommand(interaction, result.message);
  }
}

async function handleButton(interaction: ButtonInteraction, rooms: RoomManager) {
  const roomId = getRoomId(interaction);
  const room = rooms.getOrCreate(roomId, { guildId: interaction.guildId, channelId: interaction.channelId });

  if (room.locked && !canControlRoom(interaction, room)) {
    await replyCommand(interaction, "This room is locked. Only the host or server moderators can control it.", true);
    return;
  }

  if (interaction.customId === "watch:play") {
    const result = rooms.play(roomId);
    await replyCommand(interaction, result.message, true);
    return;
  }

  if (interaction.customId === "watch:pause") {
    const result = rooms.pause(roomId);
    await replyCommand(interaction, result.message, true);
    return;
  }

  if (interaction.customId === "watch:next") {
    const result = rooms.next(roomId);
    await replyCommand(interaction, result.message, true);
    return;
  }

  if (interaction.customId === "watch:status") {
    const status = formatRoomStatus(rooms.getOrCreate(roomId));
    await replyCommand(interaction, `\`\`\`text\n${status}\n\`\`\``, true);
    return;
  }

  if (interaction.customId === "watch:end") {
    const result = rooms.end(roomId);
    await replyCommand(interaction, result.message, true);
  }
}

async function routeInteraction(interaction: Interaction, rooms: RoomManager) {
  if (interaction.isChatInputCommand() && interaction.commandName === "watch") {
    await handleWatchCommand(interaction, rooms);
    return;
  }

  if (interaction.isButton() && interaction.customId.startsWith("watch:")) {
    await handleButton(interaction, rooms);
  }
}

export async function startBot(rooms: RoomManager) {
  if (!env.discordBotToken) {
    logger.warn("DISCORD_BOT_TOKEN not provided; bot will not start.");
    return null;
  }

  const client = new Client({
    intents: [GatewayIntentBits.Guilds],
    partials: [Partials.Channel]
  });

  client.once("ready", () => {
    logger.info("Discord bot ready", { user: client.user?.tag });
  });

  client.on("interactionCreate", async (interaction) => {
    try {
      await routeInteraction(interaction, rooms);
    } catch (error) {
      logger.error("Interaction handling failed", { error: String(error) });
      if (interaction.isRepliable()) {
        const content = "Command failed. Check server logs.";
        if (interaction.deferred || interaction.replied) await interaction.followUp({ content, ephemeral: true }).catch(() => undefined);
        else await interaction.reply({ content, ephemeral: true }).catch(() => undefined);
      }
    }
  });

  await client.login(env.discordBotToken);
  return client;
}
