"""
Utility helpers for building Discord Embeds from Danbooru data.
"""

import discord
from typing import Optional

# Tag category colors (matching Danbooru's color scheme)
TAG_COLORS = {
    0: 0xB0C4DE,  # general  – light steel blue
    1: 0xFF0000,  # artist   – red
    3: 0x9400D3,  # copyright – purple
    4: 0x00AA00,  # character – green
    5: 0xFF8C00,  # meta     – dark orange
}

RATING_LABELS = {
    "g": "General",
    "s": "Sensitive",
    "q": "Questionable",
    "e": "Explicit",
}

RATING_COLORS = {
    "g": 0x00AA00,
    "s": 0xFFD700,
    "q": 0xFF8C00,
    "e": 0xFF0000,
}


def post_embed(post: dict, booru_url: str = "https://danbooru.donmai.us") -> discord.Embed:
    """Build an embed for a Danbooru post."""
    post_id = post.get("id")
    url = f"{booru_url}/posts/{post_id}"
    rating = post.get("rating", "g")
    color = RATING_COLORS.get(rating, 0xB0C4DE)

    embed = discord.Embed(
        title=f"Post #{post_id}",
        url=url,
        color=color,
    )

    # Image preview
    media = post.get("media_asset") or {}
    preview_url = media.get("variants", [{}])[0].get("url") if media.get("variants") else None
    file_url = media.get("file_url") or post.get("file_url")
    large_url = media.get("large_file_url") or post.get("large_file_url")

    image_url = large_url or file_url or preview_url
    if image_url and not image_url.endswith((".swf", ".zip", ".mp4", ".webm")):
        embed.set_image(url=image_url)

    # Fields
    embed.add_field(name="Rating", value=RATING_LABELS.get(rating, rating.upper()), inline=True)
    embed.add_field(name="Score", value=str(post.get("score", 0)), inline=True)
    embed.add_field(name="Favs", value=str(post.get("fav_count", 0)), inline=True)

    uploader = post.get("uploader", {})
    if isinstance(uploader, dict):
        uploader_name = uploader.get("name", "Unknown")
    else:
        uploader_name = str(uploader)
    embed.add_field(name="Uploader", value=uploader_name, inline=True)

    # Tags (truncated to fit)
    tags = post.get("tag_string", "")
    if tags:
        tag_preview = " ".join(tags.split()[:20])
        if len(tags.split()) > 20:
            tag_preview += " …"
        embed.add_field(name="Tags", value=f"`{tag_preview}`", inline=False)

    embed.set_footer(text=f"danbooru • Post #{post_id}")
    return embed


def tag_embed(tag: dict, wiki: dict = None, booru_url: str = "https://danbooru.donmai.us") -> discord.Embed:
    """Build an embed for a Danbooru tag."""
    name = tag.get("name", "unknown")
    category = tag.get("category", 0)
    color = TAG_COLORS.get(category, 0xB0C4DE)
    post_count = tag.get("post_count", 0)

    embed = discord.Embed(
        title=name.replace("_", " "),
        url=f"{booru_url}/tags?search[name]={name}",
        color=color,
    )
    embed.add_field(name="Posts", value=f"{post_count:,}", inline=True)

    category_names = {0: "General", 1: "Artist", 3: "Copyright", 4: "Character", 5: "Meta"}
    embed.add_field(name="Category", value=category_names.get(category, "Unknown"), inline=True)

    if wiki:
        body = wiki.get("body", "")
        if body:
            # Truncate wiki body for Discord embed
            preview = body[:400].replace("[[", "").replace("]]", "")
            if len(body) > 400:
                preview += "…"
            embed.add_field(name="Wiki", value=preview, inline=False)
        embed.url = f"{booru_url}/wiki_pages/{name}"

    embed.set_footer(text=f"danbooru • {name}")
    return embed


def error_embed(title: str, description: str) -> discord.Embed:
    """Build a simple error embed."""
    return discord.Embed(title=f"❌ {title}", description=description, color=0xFF0000)


def info_embed(title: str, description: str, color: int = 0x5865F2) -> discord.Embed:
    """Build a simple info embed."""
    return discord.Embed(title=title, description=description, color=color)


def truncate(text: str, max_len: int = 1024) -> str:
    """Truncate text to fit in Discord embed field."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "…"
