"""
Embed builders cho Discord.
Tham khảo fumimi-discord: discord_embed.rb, has_discord_embed.rb, colors.rb
"""

import discord
from typing import Optional

# ── Màu theo loại tag (tag_category.rb của fumimi) ────────────────────────────
TAG_COLORS = {
    0: 0xB0C4DE,  # General   – light steel blue
    1: 0xFF0000,  # Artist    – red
    3: 0x9400D3,  # Copyright – purple
    4: 0x00AA00,  # Character – green
    5: 0xFF8C00,  # Meta      – dark orange
}

TAG_CATEGORY_NAMES = {
    0: "General",
    1: "Artist",
    3: "Copyright",
    4: "Character",
    5: "Meta",
}

RATING_LABELS = {"g": "General 🟢", "s": "Sensitive 🟡", "q": "Questionable 🟠", "e": "Explicit 🔴"}
RATING_COLORS = {"g": 0x00AA00,     "s": 0xFFD700,      "q": 0xFF8C00,         "e": 0xFF0000}

# Extensions media không hiển thị ảnh được
NON_IMAGE_EXT = {".swf", ".zip", ".mp4", ".webm", ".gif"}


def _image_url(post: dict) -> Optional[str]:
    """Lấy URL ảnh phù hợp nhất để hiển thị trong embed."""
    media = post.get("media_asset") or {}
    variants = media.get("variants") or []
    # Ưu tiên: 720x → sample → original
    for size in ("720x", "sample", "original"):
        for v in variants:
            if v.get("type") == size:
                url = v.get("url", "")
                if not any(url.endswith(ext) for ext in NON_IMAGE_EXT):
                    return url
    # Fallback
    for key in ("large_file_url", "file_url"):
        url = media.get(key) or post.get(key, "")
        if url and not any(url.endswith(ext) for ext in NON_IMAGE_EXT):
            return url
    return None


def post_embed(post: dict, booru_url: str = "https://danbooru.donmai.us") -> discord.Embed:
    """
    Build embed cho một Danbooru post.
    Tham khảo fumimi: has_discord_embed.rb, discord_embed.rb
    """
    post_id = post.get("id")
    rating  = post.get("rating", "g")
    color   = RATING_COLORS.get(rating, 0xB0C4DE)
    url     = f"{booru_url}/posts/{post_id}"

    embed = discord.Embed(title=f"Post #{post_id}", url=url, color=color)

    # Ảnh
    img = _image_url(post)
    if img:
        embed.set_image(url=img)

    # Fields cơ bản
    embed.add_field(name="Rating", value=RATING_LABELS.get(rating, rating.upper()), inline=True)
    embed.add_field(name="Score",  value=f"{post.get('score', 0):+}",               inline=True)
    embed.add_field(name="Favs",   value=f"{post.get('fav_count', 0):,}",            inline=True)

    # Uploader
    uploader = post.get("uploader") or {}
    if isinstance(uploader, dict):
        uname = uploader.get("name", "Unknown")
        uid   = uploader.get("id")
        ulink = f"[{uname}]({booru_url}/users/{uid})" if uid else uname
    else:
        ulink = str(uploader)
    embed.add_field(name="Uploader", value=ulink, inline=True)

    # Tags (hiển thị tối đa 25 tag)
    tags = post.get("tag_string", "")
    if tags:
        tag_list = tags.split()
        preview  = " ".join(tag_list[:25])
        if len(tag_list) > 25:
            preview += f" … (+{len(tag_list) - 25})"
        embed.add_field(name=f"Tags ({len(tag_list)})", value=f"`{preview}`", inline=False)

    # Source
    source = post.get("source", "")
    if source and len(source) < 200:
        embed.add_field(name="Source", value=source, inline=False)

    embed.set_footer(text=f"danbooru • Post #{post_id} • {RATING_LABELS.get(rating, rating)}")
    return embed


def tag_embed(
    tag: dict,
    wiki: dict = None,
    booru_url: str = "https://danbooru.donmai.us",
) -> discord.Embed:
    """
    Build embed cho một tag + wiki page.
    Tham khảo fumimi: tag_category.rb, colors.rb
    """
    name      = tag.get("name", "unknown")
    category  = tag.get("category", 0)
    color     = TAG_COLORS.get(category, 0xB0C4DE)
    post_count = tag.get("post_count", 0)
    cat_name  = TAG_CATEGORY_NAMES.get(category, "Unknown")

    target_url = f"{booru_url}/wiki_pages/{name}" if wiki else f"{booru_url}/posts?tags={name}"
    embed = discord.Embed(
        title=name.replace("_", " "),
        url=target_url,
        color=color,
    )

    embed.add_field(name="Posts",    value=f"[{post_count:,}]({booru_url}/posts?tags={name})", inline=True)
    embed.add_field(name="Category", value=cat_name, inline=True)

    # Deprecated / alias
    if tag.get("is_deprecated"):
        antecedent = (tag.get("antecedent_alias") or {}).get("antecedent_name", "")
        embed.add_field(
            name="⚠️ Deprecated",
            value=f"Dùng `{antecedent}` thay thế." if antecedent else "Tag này đã bị deprecated.",
            inline=False,
        )

    # Wiki body
    if wiki:
        body = wiki.get("body", "")
        if body:
            # Bỏ DText markup cơ bản
            import re
            body = re.sub(r"\[\[(.+?)(?:\|.+?)?\]\]", r"\1", body)
            body = re.sub(r"\[b\](.+?)\[/b\]", r"**\1**", body)
            body = re.sub(r"h\d\.\s*", "", body)
            preview = truncate(body.strip(), 800)
            embed.add_field(name="📖 Wiki", value=preview, inline=False)

    embed.set_footer(text=f"danbooru • {name}")
    return embed


def error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=f"❌ {title}", description=description, color=0xFF0000)


def info_embed(title: str, description: str, color: int = 0x5865F2) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


def popular_embed(posts: list[dict], scale: str, date: str, booru_url: str) -> list[discord.Embed]:
    """Build danh sách embed cho posts phổ biến."""
    return [post_embed(p, booru_url) for p in posts]


def truncate(text: str, max_len: int = 1024) -> str:
    """Cắt ngắn text để vừa Discord embed field."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
