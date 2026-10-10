"""
Embed builders và UI Views cho Discord.
Tham khảo fumimi-discord và các yêu cầu tùy chỉnh:
- Không hiển thị tags
- Có nút Tải về (Download)
- Hỗ trợ làm mờ (spoiler) ảnh rating Q & E ở kênh không giới hạn độ tuổi
"""

import io
import re
import aiohttp
import discord
from typing import Optional

# ── Màu theo loại tag ──────────────────────────────────────────────────────────
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

RATING_LABELS = {
    "g": "General 🟢",
    "s": "Sensitive 🟡",
    "q": "Questionable 🟠",
    "e": "Explicit 🔴",
}

RATING_COLORS = {
    "g": 0x00AA00,
    "s": 0xFFD700,
    "q": 0xFF8C00,
    "e": 0xFF0000,
}

# Extensions media không hiển thị ảnh tĩnh được
NON_IMAGE_EXT = {".swf", ".zip", ".mp4", ".webm"}


def is_nsfw_channel(channel) -> bool:
    """Kiểm tra xem kênh có được bật Giới hạn độ tuổi (NSFW / Kênh ẩn) không."""
    if channel is None:
        return False
    if hasattr(channel, "is_nsfw"):
        try:
            return bool(channel.is_nsfw())
        except TypeError:
            return bool(getattr(channel, "is_nsfw", False))
    return bool(getattr(channel, "nsfw", False))


def _image_url(post: dict) -> Optional[str]:
    """Lấy URL ảnh preview/sample phù hợp để hiển thị trong embed."""
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


def get_download_url(post: dict, booru_url: str = "https://danbooru.donmai.us") -> Optional[str]:
    """Lấy URL ảnh chất lượng cao nhất để tải về (ưu tiên file gốc original)."""
    media = post.get("media_asset") or {}
    variants = media.get("variants") or []
    for v in variants:
        if v.get("type") == "original":
            return v.get("url")
    for v in variants:
        if v.get("type") == "sample":
            return v.get("url")
    for key in ("file_url", "large_file_url"):
        url = media.get(key) or post.get(key)
        if url:
            return url
    return _image_url(post) or (f"{booru_url}/posts/{post.get('id')}" if post.get("id") else None)


def post_embed(
    post: dict,
    booru_url: str = "https://danbooru.donmai.us",
    spoiler_filename: Optional[str] = None,
) -> discord.Embed:
    """
    Build embed cho một Danbooru post.
    - Đã loại bỏ phần Tags theo yêu cầu.
    - Hỗ trợ làm mờ ảnh thông qua spoiler_filename (attachment://...).
    """
    post_id = post.get("id")
    rating  = str(post.get("rating", "g")).lower()
    color   = RATING_COLORS.get(rating, 0xB0C4DE)
    url     = f"{booru_url}/posts/{post_id}"

    embed = discord.Embed(title=f"Post #{post_id}", url=url, color=color)

    # Ảnh (spoiler hoặc link trực tiếp)
    if spoiler_filename:
        embed.set_image(url=f"attachment://{spoiler_filename}")
        embed.description = "⚠️ *Nội dung nhạy cảm (Rating Q/E) đã được làm mờ do kênh chưa bật Giới hạn độ tuổi. Bấm vào ảnh để xem.*"
    else:
        img = _image_url(post)
        if img:
            embed.set_image(url=img)

    # Fields thông tin
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

    # Source
    source = post.get("source", "")
    if source and len(source) < 200:
        embed.add_field(name="Source", value=source, inline=False)

    embed.set_footer(text=f"danbooru • Post #{post_id} • {RATING_LABELS.get(rating, rating)}")
    return embed


async def prepare_post_display(
    post: dict,
    channel,
    booru_url: str = "https://danbooru.donmai.us",
    session: Optional[aiohttp.ClientSession] = None,
) -> tuple[discord.Embed, Optional[discord.File]]:
    """
    Xử lý logic hiển thị post:
    - Nếu rating là Q hoặc E và kênh KHÔNG bật NSFW/Giới hạn độ tuổi:
      Tải ảnh về và gửi dưới dạng spoiler file (SPOILER_...) để Discord tự động làm mờ.
    - Nếu kênh là NSFW hoặc rating an toàn:
      Nhúng ảnh trực tiếp không cần tải.
    """
    post_id = post.get("id", 0)
    rating  = str(post.get("rating", "g")).lower()
    is_nsfw = is_nsfw_channel(channel)

    needs_spoiler = (rating in ("q", "e")) and (not is_nsfw)

    if needs_spoiler:
        img_url = _image_url(post)
        if img_url and session and not session.closed:
            try:
                async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        # Đuôi mở rộng
                        ext = "jpg"
                        if ".png" in img_url.lower():
                            ext = "png"
                        elif ".gif" in img_url.lower():
                            ext = "gif"

                        filename = f"SPOILER_post_{post_id}.{ext}"
                        file = discord.File(io.BytesIO(data), filename=filename)
                        embed = post_embed(post, booru_url, spoiler_filename=filename)
                        return embed, file
            except Exception:
                pass

        # Fallback nếu tải ảnh thất bại nhưng vẫn cần che
        embed = post_embed(post, booru_url)
        embed.set_image(url=None)
        embed.description = "⚠️ **Nội dung nhạy cảm (Rating Q/E)**\n*Ảnh được ẩn do kênh chưa bật Giới hạn độ tuổi. Nhấn nút Tải về bên dưới để xem.*"
        return embed, None

    # Bình thường
    return post_embed(post, booru_url), None


# ── Nút bấm (Buttons & Views) ──────────────────────────────────────────────────

class PostView(discord.ui.View):
    """View chứa nút Tải về cho một bài đăng."""
    def __init__(self, post: dict, booru_url: str = "https://danbooru.donmai.us"):
        super().__init__(timeout=None)
        download_url = get_download_url(post, booru_url)
        if download_url:
            self.add_item(
                discord.ui.Button(
                    label="Tải về",
                    style=discord.ButtonStyle.link,
                    url=download_url,
                    emoji="📥",
                )
            )
        post_id = post.get("id")
        if post_id:
            self.add_item(
                discord.ui.Button(
                    label=f"Post #{post_id}",
                    style=discord.ButtonStyle.link,
                    url=f"{booru_url}/posts/{post_id}",
                    emoji="🔗",
                )
            )


class MultiPostView(discord.ui.View):
    """View chứa các nút Tải về khi trả về nhiều bài đăng cùng lúc."""
    def __init__(self, posts: list[dict], booru_url: str = "https://danbooru.donmai.us"):
        super().__init__(timeout=None)
        for i, post in enumerate(posts[:5], start=1):
            download_url = get_download_url(post, booru_url)
            post_id = post.get("id", i)
            if download_url:
                self.add_item(
                    discord.ui.Button(
                        label=f"Tải #{post_id}",
                        style=discord.ButtonStyle.link,
                        url=download_url,
                        emoji="📥",
                    )
                )


def tag_embed(
    tag: dict,
    wiki: dict = None,
    booru_url: str = "https://danbooru.donmai.us",
) -> discord.Embed:
    """Build embed cho một tag + wiki page."""
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

    if tag.get("is_deprecated"):
        antecedent = (tag.get("antecedent_alias") or {}).get("antecedent_name", "")
        embed.add_field(
            name="⚠️ Deprecated",
            value=f"Dùng `{antecedent}` thay thế." if antecedent else "Tag này đã bị deprecated.",
            inline=False,
        )

    if wiki:
        body = wiki.get("body", "")
        if body:
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


def truncate(text: str, max_len: int = 1024) -> str:
    """Cắt ngắn text để vừa Discord embed field."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
