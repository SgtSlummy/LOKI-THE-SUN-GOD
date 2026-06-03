from bot.services.sanitizer import extract_links, sanitize_message_text


def test_sanitizer_strips_urls_and_preserves_markdown_link_text():
    text = (
        "Read [launch notes](https://example.com/notes?x=1) and "
        "watch https://youtu.be/dQw4w9WgXcQ before sharing."
    )

    clean = sanitize_message_text(text)

    assert "launch notes" in clean
    assert "https://" not in clean
    assert "youtu.be" not in clean
    assert clean == "Read launch notes and watch before sharing."


def test_sanitizer_neutralizes_discord_mentions_to_plain_names():
    text = "Ping @everyone, @here, <@123>, <@!456>, <@&789>, and <#111>."

    clean = sanitize_message_text(
        text,
        user_mentions={"123": "Ian", "456": "Carmen"},
        role_mentions={"789": "Admins"},
        channel_mentions={"111": "announcements"},
    )

    assert "@everyone" not in clean
    assert "@here" not in clean
    assert "<@" not in clean
    assert "<#" not in clean
    assert "everyone" in clean
    assert "here" in clean
    assert "Ian" in clean
    assert "Carmen" in clean
    assert "Admins" in clean
    assert "#announcements" in clean


def test_extract_links_includes_markdown_and_raw_urls_once():
    text = "[Video](https://youtube.com/watch?v=abc123) https://youtube.com/watch?v=abc123"

    links = extract_links(text)

    assert links == ["https://youtube.com/watch?v=abc123"]

