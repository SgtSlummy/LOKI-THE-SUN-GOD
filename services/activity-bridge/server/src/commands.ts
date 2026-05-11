import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  SlashCommandBuilder
} from "discord.js";

export const watchCommand = new SlashCommandBuilder()
  .setName("watch")
  .setDescription("Control the Discord Activity watch/stream room.")
  .addSubcommand((sub) =>
    sub.setName("status").setDescription("Show the current room status.")
  )
  .addSubcommand((sub) =>
    sub
      .setName("set")
      .setDescription("Set the current video/source URL for the Activity room.")
      .addStringOption((option) =>
        option.setName("url").setDescription("HTTP(S) media/source URL.").setRequired(true)
      )
      .addStringOption((option) =>
        option.setName("title").setDescription("Optional display title.").setRequired(false)
      )
  )
  .addSubcommand((sub) => sub.setName("play").setDescription("Start synchronized playback."))
  .addSubcommand((sub) => sub.setName("pause").setDescription("Pause synchronized playback."))
  .addSubcommand((sub) =>
    sub
      .setName("seek")
      .setDescription("Seek synchronized playback.")
      .addNumberOption((option) =>
        option.setName("seconds").setDescription("Timestamp in seconds.").setRequired(true).setMinValue(0)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("queue")
      .setDescription("Queue a video/source URL.")
      .addStringOption((option) =>
        option.setName("url").setDescription("HTTP(S) media/source URL.").setRequired(true)
      )
      .addStringOption((option) =>
        option.setName("title").setDescription("Optional display title.").setRequired(false)
      )
  )
  .addSubcommand((sub) => sub.setName("next").setDescription("Load the next queued item."))
  .addSubcommand((sub) =>
    sub
      .setName("lock")
      .setDescription("Lock or unlock Activity controls.")
      .addBooleanOption((option) =>
        option.setName("enabled").setDescription("Whether the room is locked.").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("host")
      .setDescription("Assign the room host.")
      .addUserOption((option) =>
        option.setName("user").setDescription("New room host.").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("scene")
      .setDescription("Switch OBS scene.")
      .addStringOption((option) =>
        option.setName("name").setDescription("OBS scene name.").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("overlay")
      .setDescription("Show or hide an OBS scene source/overlay.")
      .addStringOption((option) =>
        option.setName("scene").setDescription("OBS scene name.").setRequired(true)
      )
      .addStringOption((option) =>
        option.setName("source").setDescription("OBS source name.").setRequired(true)
      )
      .addBooleanOption((option) =>
        option.setName("visible").setDescription("Whether the source should be visible.").setRequired(true)
      )
  )
  .addSubcommand((sub) =>
    sub
      .setName("title")
      .setDescription("Update Twitch title and/or an OBS text source.")
      .addStringOption((option) =>
        option.setName("text").setDescription("Title text.").setRequired(true)
      )
      .addStringOption((option) =>
        option.setName("obs_source").setDescription("Optional OBS text source name.").setRequired(false)
      )
  )
  .addSubcommand((sub) => sub.setName("stream-start").setDescription("Start OBS streaming if enabled on the backend."))
  .addSubcommand((sub) => sub.setName("stream-stop").setDescription("Stop OBS streaming if enabled on the backend."))
  .addSubcommand((sub) => sub.setName("end").setDescription("End and clear the current room."));

export const commandPayloads = [watchCommand.toJSON()];

export function controlButtons() {
  return new ActionRowBuilder<ButtonBuilder>().addComponents(
    new ButtonBuilder().setCustomId("watch:play").setLabel("Play").setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId("watch:pause").setLabel("Pause").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("watch:next").setLabel("Next").setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId("watch:status").setLabel("Status").setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId("watch:end").setLabel("End").setStyle(ButtonStyle.Danger)
  );
}
