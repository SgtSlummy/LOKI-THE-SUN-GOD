from __future__ import annotations

from typing import Any, Iterable

PLACEHOLDER = "No description in source yet."


EXPLICIT_DESCRIPTIONS = {
    "8ball": "Ask the bot a Magic 8-Ball style question.",
    "addrank": "Add a self-assignable rank role.",
    "ar": "Manage autoresponder triggers and replies.",
    "ar add": "Create a new autoresponder trigger.",
    "ar clear": "Remove all autoresponders for this server.",
    "ar endswith": "Add an ends-with autoresponder.",
    "ar exact": "Add an exact-match autoresponder.",
    "ar list": "List saved autoresponder triggers.",
    "ar regex": "Add a regex-based autoresponder.",
    "ar remove": "Delete an autoresponder trigger.",
    "ar startswith": "Add a starts-with autoresponder.",
    "ar strict": "Add a strict-match autoresponder.",
    "ar test": "Check which autoresponder would fire for a sample message.",
    "autorole": "Manage roles assigned automatically to new members.",
    "autorole add": "Add a role to the autorole list.",
    "autorole remove": "Remove a role from the autorole list.",
    "automod": "Review this server's current moderation protection settings.",
    "automod badword": "Add a blocked word to this server's filter list.",
    "automod badwords": "List the blocked words configured for this server.",
    "automod capspercent": "Set the uppercase percentage that triggers caps filtering.",
    "automod mentions": "Set how many mentions are allowed before AutoMod removes a message.",
    "automod spamthreshold": "Set how many rapid messages count as spam.",
    "automod toggle": "Turn a specific AutoMod rule on or off.",
    "automod unbadword": "Remove a blocked word from this server's filter list.",
    "avatar": "Show a member's avatar.",
    "ban": "Ban a member from the server.",
    "cembed delete": "Delete a saved embed preset.",
    "cembed edit": "Update a saved embed preset.",
    "cembed list": "List saved embed presets.",
    "cembed save": "Save a custom embed preset for later use.",
    "cembed send": "Send a saved embed preset to a channel.",
    "cembed source": "Show the stored payload for a saved embed preset.",
    "censor": "Manage the server word-censor list.",
    "censor add": "Add a word to the censor list.",
    "censor clear": "Clear the full censor list.",
    "censor list": "Show the current censor list.",
    "censor remove": "Remove a word from the censor list.",
    "coinflip": "Flip a coin.",
    "config": "Review this server's saved core configuration.",
    "config logchannel": "Set the moderation log channel.",
    "config muterole": "Set the mute role used by moderation tools.",
    "config prefix": "Change the server command prefix.",
    "config starboard": "Configure starboard channel and threshold settings.",
    "event": "Manage scheduled events for this server.",
    "event cancel": "Cancel an existing event.",
    "event color": "Change the accent color used for an event.",
    "event create": "Create a new scheduled event entry.",
    "event edit": "Edit an existing event.",
    "event info": "Show details for a specific event.",
    "event list": "List saved events for this server.",
    "event remind": "Add or trigger reminders for an event.",
    "event unrepost": "Stop reposting an event announcement.",
    "form": "Manage application and intake forms.",
    "form addfield": "Add a field to a saved form.",
    "form create": "Create a new form shell.",
    "form delete": "Delete a saved form.",
    "form info": "Show details for one saved form.",
    "form list": "List forms configured for this server.",
    "form panel": "Post the public form button panel.",
    "form responses": "Review submissions for a saved form.",
    "form setlabel": "Set the public button label for a form.",
    "form settarget": "Set the destination channel for form submissions.",
    "highlight": "Manage highlight keywords for notifications.",
    "highlight add": "Add a highlight keyword.",
    "highlight clear": "Clear all of your saved highlight keywords in this server.",
    "highlight list": "List your saved highlight keywords.",
    "highlight remove": "Remove a highlight keyword.",
    "kick": "Kick a member from the server.",
    "leaderboard": "Show the server XP leaderboard.",
    "linkspam": "Manage link filtering rules for this server.",
    "linkspam allow": "Allow a domain in the link filter.",
    "linkspam block": "Block a domain in the link filter.",
    "linkspam list": "Show saved link filter rules.",
    "linkspam unallow": "Remove a domain from the allowlist.",
    "linkspam unblock": "Remove a domain from the blocklist.",
    "lock": "Lock a channel so members cannot send messages.",
    "mute": "Mute a member using the configured mute role.",
    "ping": "Check the bot's current latency.",
    "purge": "Bulk-delete recent messages from a channel.",
    "purgex bot": "Delete recent bot messages.",
    "purgex contains": "Delete messages containing specific text.",
    "purgex embeds": "Delete messages that contain embeds.",
    "purgex emoji": "Delete messages containing emoji.",
    "purgex files": "Delete messages with file uploads.",
    "purgex human": "Delete messages sent by human users.",
    "purgex links": "Delete messages that contain links.",
    "purgex mentions": "Delete messages that mention users or roles.",
    "purgex reactions": "Clear reactions from recent messages.",
    "rank": "Show a member's current XP rank.",
    "ranks": "List self-assignable rank roles.",
    "reminder": "Create a reminder for later.",
    "removerank": "Remove a self-assignable rank role.",
    "role": "Run role management actions.",
    "role add": "Add a role to a member.",
    "role all": "Add a role to every member.",
    "role bots": "Add a role to all bot accounts.",
    "role color": "Change the color of a role.",
    "role create": "Create a new server role.",
    "role in": "List members who currently have a role.",
    "role info": "Show details about a role.",
    "role rall": "Remove a role from every member who has it.",
    "role remove": "Remove a role from a member.",
    "roll": "Roll dice using standard dice notation.",
    "rr": "Manage reaction role messages.",
    "rr add": "Create a reaction role binding.",
    "rr binding": "Make a reaction role stay even when the reaction is removed.",
    "rr list": "List reaction role bindings.",
    "rr normal": "Set a reaction role message back to normal mode.",
    "rr remove": "Remove a reaction role binding.",
    "rr reversed": "Reverse a reaction role so adding a reaction removes the role.",
    "rr unique": "Allow only one reaction role from that message at a time.",
    "rr verify": "Only add a reaction role and never remove it automatically.",
    "serverinfo": "Show information about the current server.",
    "slowmode": "Change the channel slowmode delay.",
    "softban": "Ban and immediately unban to clear recent messages.",
    "sticky": "Manage sticky channel reminders.",
    "sticky list": "List sticky messages for this server.",
    "sticky remove": "Remove a sticky message from a channel.",
    "sticky show": "Preview the sticky message for the current channel.",
    "streams": "Manage live-stream alert subscriptions.",
    "streams list": "List tracked stream subscriptions.",
    "suggest": "Create a suggestion in the configured suggestion channel.",
    "suggestion": "Manage suggestion system settings.",
    "suggestion anon": "Toggle anonymous suggestions.",
    "suggestion channel": "Set the suggestion channel.",
    "suggestion server": "Review the current suggestion system configuration.",
    "suggestion submit": "Submit a suggestion through the suggestion command group.",
    "suggestion who": "Reveal the author of a saved suggestion.",
    "tag": "Recall a saved tag response.",
    "tag create": "Create a new saved tag.",
    "tag delete": "Delete a saved tag.",
    "tag edit": "Edit an existing tag.",
    "tag info": "Show information about a tag.",
    "tag list": "List saved tags.",
    "timeout": "Apply a temporary communication timeout to a member.",
    "unban": "Unban a previously banned user.",
    "unlock": "Unlock a channel again.",
    "unmute": "Remove a mute from a member.",
    "userinfo": "Show information about a member.",
    "warn": "Issue a moderation warning to a member.",
    "welcome": "Manage welcome and goodbye messaging.",
    "welcome bye": "Set the goodbye message content.",
    "welcome channel": "Set the welcome message channel.",
    "welcome message": "Set the welcome message content.",
    "welcome preview": "Preview the current welcome or goodbye template.",
    "welcome status": "Review the current welcome configuration.",
    "ticket status": "Review the current ticket configuration and open-ticket count.",
}


CATEGORY_OBJECTS = {
    "automod": "AutoMod settings",
    "automod ext": "extended AutoMod settings",
    "autoresponders": "autoresponders",
    "cembed": "custom embeds",
    "config": "server configuration",
    "events": "events",
    "forms": "forms",
    "fun": "fun utilities",
    "highlights": "highlight keywords",
    "levels": "leveling data",
    "moderation": "moderation actions",
    "moderation ext": "advanced moderation actions",
    "purge ext": "message cleanup filters",
    "reaction roles": "reaction roles",
    "reminders": "reminders",
    "roles": "roles",
    "sticky": "sticky messages",
    "streams": "stream subscriptions",
    "suggestions": "suggestion settings",
    "tags": "tags",
    "tickets": "tickets",
    "utility": "utility information",
    "welcome": "welcome settings",
}


ACTION_TEMPLATES = {
    "add": "Add an item to {object_name}.",
    "remove": "Remove an item from {object_name}.",
    "delete": "Delete an item from {object_name}.",
    "list": "List {object_name}.",
    "info": "Show details from {object_name}.",
    "create": "Create a new entry in {object_name}.",
    "edit": "Edit an entry in {object_name}.",
    "panel": "Post or open the public panel for {object_name}.",
    "setup": "Configure {object_name}.",
    "toggle": "Toggle a setting in {object_name}.",
    "channel": "Set the channel used by {object_name}.",
    "message": "Update the message used by {object_name}.",
    "clear": "Clear entries from {object_name}.",
}


OPTION_DESCRIPTION_OVERRIDES = {
    "8ball question": "Question you want the Magic 8-Ball to answer.",
    "addrank role": "Role members should be allowed to self-assign.",
    "ar reply": "Reply text the bot should send when the trigger matches.",
    "ar trigger": "Phrase or pattern that should trigger this autoresponder.",
    "ar add body": "Reply text the bot should send when the trigger matches.",
    "ar endswith body": "Reply text the bot should send when the trigger matches.",
    "ar exact body": "Reply text the bot should send when the trigger matches.",
    "ar regex body": "Reply text the bot should send when the trigger matches.",
    "ar startswith body": "Reply text the bot should send when the trigger matches.",
    "ar strict body": "Reply text the bot should send when the trigger matches.",
    "ar endswith trigger": "Ending text the message should end with.",
    "ar exact trigger": "Exact trigger phrase to match.",
    "ar regex trigger": "Regex pattern to test against each message.",
    "ar startswith trigger": "Opening text the message should start with.",
    "ar strict trigger": "Exact trigger phrase to watch for in chat.",
    "ban member": "Member to ban from the server.",
    "ban reason": "Reason shown in logs and the audit trail.",
    "automod toggle rule": "AutoMod rule name to enable or disable.",
    "cembed edit payload": "Embed payload or JSON you want to save.",
    "cembed save payload": "Embed payload or JSON you want to save.",
    "config logchannel channel": "Channel where moderation and audit events should be logged.",
    "config muterole role": "Role the bot should use for manual mute workflows.",
    "config prefix new_prefix": "New prefix members should use for message commands.",
    "config starboard channel": "Channel where starred messages should be reposted.",
    "config starboard threshold": "How many star reactions are required before reposting.",
    "delwarn warn_id": "Numeric warning ID to delete.",
    "event cancel name": "Saved event name to cancel.",
    "event color hex_color": "Hex color to use for that event card.",
    "event color name": "Saved event name to update.",
    "event create name": "Internal event key used to manage this event later.",
    "event create body": "Optional event details or announcement copy shown to members.",
    "event create start_iso": "Event start time in ISO format, for example 2026-05-01T19:00.",
    "event create title": "Public event title members will see.",
    "event edit field": "Saved event field that should be changed.",
    "event edit name": "Saved event name to edit.",
    "event edit value": "New value that should replace the current field content.",
    "event info name": "Saved event name to inspect.",
    "event remind offset": "Reminder timing relative to the event start.",
    "event remind minutes_before": "How many minutes before start the reminder should fire.",
    "event remind name": "Saved event name to remind members about.",
    "event repost interval": "How often the event should be reposted.",
    "event repost name": "Saved event name to repost.",
    "event unrepost name": "Saved event name to stop reposting.",
    "form addfield form_name": "Saved form that should receive the new field.",
    "form addfield label": "Field label shown to members in the modal.",
    "form addfield placeholder": "Helper text shown inside the input before typing.",
    "form addfield required": "Whether members must fill in this field before submitting.",
    "form addfield style": "Whether the field should be short or paragraph sized.",
    "form create name": "Internal form key used to manage the form later.",
    "form create title": "Public form title shown to members.",
    "form delete form_name": "Saved form to remove.",
    "form info form_name": "Saved form to inspect.",
    "form panel channel": "Optional channel where the button panel should be posted.",
    "form panel description": "Supporting text shown above the public form button.",
    "form panel form_name": "Saved form whose button panel should be posted.",
    "form responses count": "How many recent submissions should be shown.",
    "form responses form_name": "Saved form whose submissions you want to review.",
    "form setlabel form_name": "Saved form whose button label should change.",
    "form setlabel label": "Public button text members will click.",
    "form settarget channel": "Channel where submitted form responses should be delivered.",
    "form settarget form_name": "Saved form whose destination channel should change.",
    "help command": "Optional command name to inspect in detail.",
    "highlight add word": "Keyword that should trigger highlight notifications.",
    "highlight clear": "Clear all of your saved highlight keywords in this server.",
    "highlight remove word": "Saved keyword to remove from your highlight list.",
    "kick member": "Member to remove from the server.",
    "kick reason": "Reason shown in logs and the audit trail.",
    "linkspam allow domain": "Domain that should be allowed by the link filter.",
    "linkspam block domain": "Domain that should be blocked by the link filter.",
    "linkspam unallow domain": "Allowed domain that should be removed from the list.",
    "linkspam unblock domain": "Blocked domain that should be removed from the list.",
    "modrole role": "Role that should count as a moderator role.",
    "mute duration": "Timeout length, such as 1h or 30m.",
    "mute member": "Member to timeout.",
    "mute reason": "Reason shown in logs and the audit trail.",
    "purge amount": "How many recent messages should be removed.",
    "purge member": "Optional member filter so only their messages are removed.",
    "purgex contains text": "Text the cleanup filter should match.",
    "rank member": "Member whose level card you want to inspect.",
    "reminder text": "Reminder text the bot should send back later.",
    "reminder when": "When the reminder should trigger.",
    "role add member": "Member who should receive the role.",
    "role add role": "Role that should be added.",
    "role all role": "Role that should be added to every member.",
    "role bots role": "Role that should be added to all bot accounts.",
    "role color color": "New color value for the role.",
    "role color role": "Role whose color should change.",
    "role create color": "Optional color to apply when the role is created.",
    "role create name": "Name to use for the new server role.",
    "role in role": "Role whose current members should be listed.",
    "role info role": "Role to inspect.",
    "role rall role": "Role that should be removed from every current holder.",
    "role remove member": "Member who should lose the role.",
    "role remove role": "Role that should be removed.",
    "roll dice": "Dice notation to roll, such as 2d6+1.",
    "rr add emoji": "Emoji members should react with to receive the role.",
    "rr add message_ref": "Discord message link or current-channel message ID to bind.",
    "rr binding message_ref": "Discord message link or current-channel message ID to update.",
    "rr normal message_ref": "Discord message link or current-channel message ID to update.",
    "rr remove emoji": "Emoji binding that should be removed from the role message.",
    "rr remove message_ref": "Discord message link or current-channel message ID to edit.",
    "rr reversed message_ref": "Discord message link or current-channel message ID to update.",
    "rr unique message_ref": "Discord message link or current-channel message ID to update.",
    "rr verify message_ref": "Discord message link or current-channel message ID to update.",
    "serverinfo member": "Optional member to anchor the server info lookup to.",
    "slowmode seconds": "Number of seconds members must wait between messages.",
    "softban member": "Member to softban.",
    "softban reason": "Reason shown in logs and the audit trail.",
    "streams add name": "Streamer channel name or username on that platform.",
    "streams add ping": "Optional role to mention when the alert fires.",
    "streams add platform": "Streaming service to track for live alerts.",
    "streams add target": "Channel where live alerts should be posted.",
    "streams remove sub_id": "Tracked subscription ID to remove.",
    "streams test sub_id": "Tracked subscription ID to use for the test alert.",
    "suggest text": "Suggestion text to submit.",
    "ticket status": "Review current ticket settings and open ticket count.",
    "tag content": "Saved response content for the tag.",
    "tag create content": "Saved response content for the new tag.",
    "tag create name": "Tag name members will recall later.",
    "tag delete name": "Saved tag name to delete.",
    "tag edit content": "Updated response content for the tag.",
    "tag edit name": "Saved tag name to edit.",
    "tag info name": "Saved tag name to inspect.",
    "tag name": "Stored tag name to recall.",
    "welcome bye text": "Goodbye text sent when a member leaves.",
    "welcome message text": "Welcome text sent when a member joins.",
    "timeout duration": "Timeout length, such as 1h or 30m.",
    "timeout member": "Member to timeout.",
    "timeout reason": "Reason shown in logs and the audit trail.",
    "unban reason": "Reason shown in logs and the audit trail.",
    "unban user_id": "User ID of the ban entry to remove.",
    "unignore channel": "Ignored channel that should be restored.",
    "unmodrole role": "Moderator role that should be removed.",
    "warn member": "Member who should receive the warning.",
    "warn reason": "Reason that should be recorded with the warning.",
    "warnings member": "Member whose warning history should be shown.",
}


OPTION_NAME_HINTS = {
    "amount": "How many items should be included.",
    "channel": "Channel to use for this command.",
    "color": "Color value to use for this command.",
    "command": "Command name this action should target.",
    "content": "Content to save for this command.",
    "count": "How many recent entries should be shown.",
    "days": "Number of days this action should affect.",
    "description": "Supporting description text to use.",
    "dice": "Dice notation to roll, such as 2d6+1.",
    "domain": "Domain value this command should use.",
    "duration": "How long this action should stay in effect.",
    "emoji": "Emoji this command should use.",
    "form_name": "Saved form name this action should target.",
    "field": "Field name this command should target.",
    "hex_color": "Hex color value to use.",
    "interval": "Interval value this command should use.",
    "label": "Label text to show to members.",
    "member": "Member this command should target.",
    "message": "Message text to use for this command.",
    "message_ref": "Discord message link or current-channel message ID to target.",
    "minutes_before": "How many minutes before start this should happen.",
    "name": "Name value this command should use.",
    "new_prefix": "New prefix members should type for message commands.",
    "offset": "Offset value this command should use.",
    "ping": "Optional role to mention when this runs.",
    "payload": "Payload content this command should store.",
    "placeholder": "Placeholder text shown before members type.",
    "platform": "Platform value this command should use.",
    "question": "Question text to use for this command.",
    "reason": "Reason recorded for this action.",
    "reply": "Reply text the bot should send.",
    "required": "Whether this field should be required.",
    "role": "Role this command should target.",
    "seconds": "Number of seconds to use.",
    "sid": "Suggestion ID this command should target.",
    "start_iso": "Date and time for this action in ISO format.",
    "style": "Display style this field should use.",
    "sub_id": "Tracked subscription ID to target.",
    "target": "Target channel this command should use.",
    "text": "Text value to use for this command.",
    "threshold": "Threshold value this command should use.",
    "title": "Title text to show to members.",
    "trigger": "Trigger text or pattern this command should watch for.",
    "user_id": "User ID this command should target.",
    "value": "New value this command should apply.",
    "warn_id": "Warning ID this action should target.",
    "when": "When this should happen.",
    "word": "Word or phrase this command should target.",
}


def command_description_for(
    full_name: str,
    category: str,
    kind: str,
    existing_description: str | None = None,
) -> str:
    existing = normalize_existing_text(existing_description)
    if existing and existing != PLACEHOLDER:
        return truncate_description(existing)

    normalized = normalize_command_name(full_name)
    if normalized in EXPLICIT_DESCRIPTIONS:
        return truncate_description(EXPLICIT_DESCRIPTIONS[normalized])

    parts = normalized.split()
    if not parts:
        return PLACEHOLDER

    if len(parts) == 1:
        object_name = category_object_name(category)
        return truncate_description(f"Open or manage {object_name}.")

    action = parts[-1]
    object_name = category_object_name(category)
    template = ACTION_TEMPLATES.get(action)
    if template:
        return truncate_description(template.format(object_name=object_name))

    return truncate_description(f"Run the `{normalized}` command for {object_name}.")


def option_description_for(
    full_name: str,
    option_name: str,
    type_name: str = "",
    existing_description: str | None = None,
    choices: list[str] | None = None,
) -> str:
    existing = normalize_existing_text(existing_description)
    if existing and existing != PLACEHOLDER:
        return truncate_description(existing)

    normalized_command = normalize_command_name(full_name)
    normalized_option = normalize_command_name(option_name).replace("-", "_")
    override_key = f"{normalized_command} {normalized_option}".strip()
    if override_key in OPTION_DESCRIPTION_OVERRIDES:
        return truncate_description(OPTION_DESCRIPTION_OVERRIDES[override_key])

    if normalized_option in OPTION_NAME_HINTS:
        return truncate_description(OPTION_NAME_HINTS[normalized_option])

    if choices:
        return truncate_description(
            f"Choose the {humanize_identifier(normalized_option).lower()} to use for this command."
        )

    simple_type = (type_name or "").lower()
    if "channel" in simple_type:
        return truncate_description(f"Channel to use for {humanize_identifier(normalized_option).lower()}.")
    if "member" in simple_type or simple_type == "user":
        return truncate_description(f"Member to use for {humanize_identifier(normalized_option).lower()}.")
    if "role" in simple_type:
        return truncate_description(f"Role to use for {humanize_identifier(normalized_option).lower()}.")
    if simple_type in {"integer", "int", "number", "float"}:
        return truncate_description(f"Numeric value for {humanize_identifier(normalized_option).lower()}.")
    if simple_type in {"boolean", "bool"}:
        return truncate_description(f"Whether {humanize_identifier(normalized_option).lower()} should be enabled.")

    return truncate_description(f"Value to use for {humanize_identifier(normalized_option).lower()}.")


def truncate_description(text: str, limit: int = 100) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def normalize_command_name(name: str) -> str:
    return " ".join((name or "").strip().split())


def category_object_name(category: str) -> str:
    return CATEGORY_OBJECTS.get((category or "").lower(), (category or "commands").lower())


def humanize_identifier(name: str) -> str:
    parts = [part for part in (name or "").replace("-", "_").split("_") if part]
    return " ".join(parts).title() if parts else "Value"


def normalize_existing_text(value: Any) -> str:
    if value is None:
        return ""
    message = getattr(value, "message", value)
    text = " ".join(str(message).strip().split())
    return "" if text in {"...", "…", "-", "--"} else text


def walk_app_commands(commands_list: Iterable):
    for command in commands_list:
        yield command
        children = getattr(command, "commands", None)
        if children:
            yield from walk_app_commands(children)


def option_type_name(param: Any) -> str:
    type_obj = getattr(param, "type", None)
    type_name = getattr(type_obj, "name", "") if type_obj is not None else ""
    return str(type_name or "").lower()


def option_choice_names(param: Any) -> list[str]:
    names = []
    for choice in getattr(param, "choices", None) or []:
        label = getattr(choice, "name", None)
        value = getattr(choice, "value", None)
        names.append(str(label or value or "").strip())
    return [name for name in names if name]


def apply_option_descriptions(app_command: Any, qualified_name: str) -> None:
    params = getattr(app_command, "_params", None)
    if isinstance(params, dict):
        items = params.items()
    else:
        items = [(getattr(param, "name", ""), param) for param in getattr(app_command, "parameters", [])]

    for option_name, param in items:
        if not option_name:
            continue
        updated = option_description_for(
            qualified_name,
            option_name,
            option_type_name(param),
            getattr(param, "description", None),
            option_choice_names(param),
        )
        try:
            param.description = updated
        except Exception:
            pass


def apply_descriptions_to_bot(bot) -> None:
    for command in bot.walk_commands():
        qualified = normalize_command_name(getattr(command, "qualified_name", getattr(command, "name", "")))
        category = command.cog_name or "Commands"
        updated = command_description_for(
            qualified, category, command.__class__.__name__, getattr(command, "help", None)
        )
        if hasattr(command, "help"):
            command.help = updated
        if hasattr(command, "brief"):
            command.brief = updated
        app_command = getattr(command, "app_command", None)
        if app_command is not None:
            try:
                app_command.description = updated
            except Exception:
                pass
            apply_option_descriptions(app_command, qualified)

    for app_command in walk_app_commands(bot.tree.get_commands()):
        qualified = normalize_command_name(getattr(app_command, "qualified_name", getattr(app_command, "name", "")))
        category = getattr(app_command, "module", "Commands").split(".")[-1].replace("_", " ").title()
        updated = command_description_for(qualified, category, "slash", getattr(app_command, "description", None))
        try:
            app_command.description = updated
        except Exception:
            pass
        apply_option_descriptions(app_command, qualified)
