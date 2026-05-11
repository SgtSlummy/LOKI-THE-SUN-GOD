import { REST, Routes } from "discord.js";
import { commandPayloads } from "./commands.js";
import { env, requireEnv } from "./env.js";
import { logger } from "./logger.js";

async function main() {
  const token = requireEnv(env.discordBotToken, "DISCORD_BOT_TOKEN");
  const applicationId = requireEnv(env.discordApplicationId || env.discordClientId, "DISCORD_APPLICATION_ID or DISCORD_CLIENT_ID");

  const rest = new REST({ version: "10" }).setToken(token);

  if (env.discordDevGuildId) {
    logger.info("Registering guild commands", { guildId: env.discordDevGuildId });
    await rest.put(Routes.applicationGuildCommands(applicationId, env.discordDevGuildId), { body: commandPayloads });
  } else {
    logger.info("Registering global commands");
    await rest.put(Routes.applicationCommands(applicationId), { body: commandPayloads });
  }

  logger.info("Commands registered", { count: commandPayloads.length });
}

main().catch((error) => {
  logger.error("Command registration failed", { error: String(error) });
  process.exit(1);
});
