import { ChatInputCommandInteraction, GuildMember, PermissionFlagsBits, ButtonInteraction } from "discord.js";
import { RoomState } from "@activity/shared";

type SupportedInteraction = ChatInputCommandInteraction | ButtonInteraction;

export function canControlRoom(interaction: SupportedInteraction, room?: RoomState): boolean {
  if (!interaction.inGuild()) return true;

  if (room?.hostUserId && interaction.user.id === room.hostUserId) return true;

  const member = interaction.member;
  if (member instanceof GuildMember) {
    return member.permissions.has(PermissionFlagsBits.ManageGuild) || member.permissions.has(PermissionFlagsBits.ManageChannels);
  }

  const permissions = interaction.memberPermissions;
  return Boolean(
    permissions?.has(PermissionFlagsBits.ManageGuild) || permissions?.has(PermissionFlagsBits.ManageChannels)
  );
}
