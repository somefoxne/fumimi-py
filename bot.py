"""
Fumimi – Danbooru Discord Bot (Python)
======================================
Tham khảo:
  - https://github.com/danbooru/fumimi-discord
  - https://danbooru.donmai.us/wiki_pages/help:api

Slash commands:
  /hi         – chào bot
  /post       – xem post theo ID
  /posts      – tìm kiếm post theo tags
  /random     – post ngẫu nhiên
  /count      – đếm post theo tags
  /popular    – posts phổ biến hôm nay / tuần / tháng
  /tag        – xem thông tin tag + wiki
  /related    – tags liên quan
  /comment    – xem comment của post
  /forum      – tìm forum topic
  /calc       – tính toán biểu thức
  /say        – bot nói gì đó (cần quyền Manage Messages)

Bot cũng tự động embed link danbooru.donmai.us paste vào chat.
"""

import os
import re
import ast
import operator
import logging
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from danbooru_client import DanbooruClient, DanbooruError
from embeds import (
    post_embed, tag_embed,
    error_embed, info_embed, truncate,
    prepare_post_display, PostView, MultiPostView,
)

# ── Cấu hình ───────────────────────────────────────────────────────────────────
load_dotenv()

import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("fumimi")

DISCORD_TOKEN = settings.DISCORD_TOKEN
BOORU_URL     = settings.get_active_booru_url()
BOORU_DOMAINS = settings.BOORU_DOMAINS

# ── Bot ────────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # bắt buộc để đọc nội dung tin nhắn


class FumimiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.booru = DanbooruClient()

    async def setup_hook(self):
        # Sync slash commands lên Discord
        await self.tree.sync()
        log.info("Slash commands đã sync.")

    async def close(self):
        await self.booru.close()
        await super().close()


bot = FumimiBot()

# ── Regex nhận link danbooru ───────────────────────────────────────────────────
def _build_post_url_re() -> re.Pattern:
    domains = "|".join(re.escape(d) for d in BOORU_DOMAINS)
    return re.compile(
        rf"https?://(?:{domains})/posts/(\d+)",
        re.IGNORECASE,
    )

POST_URL_RE = _build_post_url_re()

# ── Safe math evaluator ────────────────────────────────────────────────────────
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def safe_eval(expr: str) -> float:
    """Tính toán biểu thức toán học an toàn (không dùng eval)."""
    tree = ast.parse(expr.strip(), mode="eval")
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)): return node.value
            raise ValueError("Không hỗ trợ kiểu dữ liệu này")
        if isinstance(node, ast.BinOp):
            op = _OPS.get(type(node.op))
            if op is None: raise ValueError(f"Toán tử không được hỗ trợ")
            return op(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _OPS.get(type(node.op))
            if op is None: raise ValueError(f"Toán tử không được hỗ trợ")
            return op(_eval(node.operand))
        raise ValueError(f"Biểu thức không hợp lệ")
    return _eval(tree)


# ═══════════════════════════════════════════════════════════════════════════════
# Slash Commands
# ═══════════════════════════════════════════════════════════════════════════════

# ── /hi ───────────────────────────────────────────────────────────────────────
@bot.tree.command(name="hi", description="Chào Fumimi!")
async def cmd_hi(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Chào {interaction.user.mention}! Mình là Fumimi, bot Danbooru của server này. 🌸\n"
        f"Dùng `/posts tags:...` để tìm ảnh nhé!"
    )


# ── /post ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="post", description="Xem một post Danbooru theo ID")
@app_commands.describe(post_id="ID của post cần xem")
async def cmd_post(interaction: discord.Interaction, post_id: int):
    await interaction.response.defer()
    try:
        post = await bot.booru.get_post(post_id)
        session = await bot.booru._get_session()
        embed, file = await prepare_post_display(post, interaction.channel, BOORU_URL, session)
        view = PostView(post, BOORU_URL)
        if file:
            await interaction.followup.send(embed=embed, file=file, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Không tìm thấy post", e.message))
    except Exception as e:
        log.exception("Lỗi khi lấy post %s", post_id)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /posts ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="posts", description="Tìm kiếm post Danbooru theo tags")
@app_commands.describe(
    tags="Tags tìm kiếm (cách nhau bằng dấu cách, VD: hatsune_miku solo)",
    limit="Số kết quả (1–4, mặc định 3)",
    page="Trang kết quả (mặc định 1)",
)
async def cmd_posts(
    interaction: discord.Interaction,
    tags: str = "",
    limit: app_commands.Range[int, 1, 4] = 3,
    page: app_commands.Range[int, 1, 1000] = 1,
):
    await interaction.response.defer()
    try:
        posts = await bot.booru.get_posts(tags=tags, limit=limit, page=page)
        if not posts:
            await interaction.followup.send(
                embed=error_embed("Không có kết quả", f"Không tìm thấy post nào cho `{tags or '(tất cả)'}`.")
            )
            return
        session = await bot.booru._get_session()
        embeds = []
        files = []
        for p in posts:
            emb, f = await prepare_post_display(p, interaction.channel, BOORU_URL, session)
            embeds.append(emb)
            if f:
                files.append(f)
        view = MultiPostView(posts, BOORU_URL) if len(posts) > 1 else PostView(posts[0], BOORU_URL)
        label = f"`{tags}`" if tags else "*(tất cả)*"
        send_kwargs = {
            "content": f"🔍 Tìm thấy {len(posts)} kết quả cho {label} (trang {page})",
            "embeds": embeds,
            "view": view,
        }
        if files:
            send_kwargs["files"] = files
        await interaction.followup.send(**send_kwargs)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /posts tags=%s", tags)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /random ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="random", description="Xem một post ngẫu nhiên từ Danbooru")
@app_commands.describe(tags="Tags lọc (không bắt buộc)")
async def cmd_random(interaction: discord.Interaction, tags: str = ""):
    await interaction.response.defer()
    try:
        post = await bot.booru.get_random_post(tags=tags)
        session = await bot.booru._get_session()
        embed, file = await prepare_post_display(post, interaction.channel, BOORU_URL, session)
        view = PostView(post, BOORU_URL)
        label = f" với tags `{tags}`" if tags else ""
        if file:
            await interaction.followup.send(
                content=f"🎲 Post ngẫu nhiên{label}:",
                embed=embed,
                file=file,
                view=view,
            )
        else:
            await interaction.followup.send(
                content=f"🎲 Post ngẫu nhiên{label}:",
                embed=embed,
                view=view,
            )
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi", e.message))
    except Exception as e:
        log.exception("Lỗi /random tags=%s", tags)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /count ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="count", description="Đếm số post theo tags")
@app_commands.describe(tags="Tags tìm kiếm (không bắt buộc)")
async def cmd_count(interaction: discord.Interaction, tags: str = ""):
    await interaction.response.defer()
    try:
        count = await bot.booru.get_post_count(tags=tags)
        label = f"`{tags}`" if tags else "tất cả posts"
        search_url = f"{BOORU_URL}/posts?tags={tags}" if tags else f"{BOORU_URL}/posts"
        embed = discord.Embed(
            title="📊 Số lượng post",
            description=f"**[{count:,} posts]({search_url})** khớp với {label}",
            color=0x5865F2,
        )
        embed.set_footer(text=f"danbooru • {BOORU_URL}")
        await interaction.followup.send(embed=embed)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /count tags=%s", tags)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /popular ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="popular", description="Xem posts phổ biến trên Danbooru")
@app_commands.describe(
    scale="Khoảng thời gian: day (ngày), week (tuần), month (tháng)",
    date="Ngày cụ thể (YYYY-MM-DD, mặc định hôm nay)",
)
@app_commands.choices(scale=[
    app_commands.Choice(name="Hôm nay", value="day"),
    app_commands.Choice(name="Tuần này", value="week"),
    app_commands.Choice(name="Tháng này", value="month"),
])
async def cmd_popular(
    interaction: discord.Interaction,
    scale: str = "day",
    date: str = None,
):
    await interaction.response.defer()
    try:
        posts = await bot.booru.get_popular_posts(date=date, scale=scale, limit=4)
        if not posts:
            await interaction.followup.send(
                embed=error_embed("Không có dữ liệu", "Không có posts phổ biến nào.")
            )
            return
        scale_label = {"day": "hôm nay", "week": "tuần này", "month": "tháng này"}.get(scale, scale)
        session = await bot.booru._get_session()
        embeds = []
        files = []
        for p in posts:
            emb, f = await prepare_post_display(p, interaction.channel, BOORU_URL, session)
            embeds.append(emb)
            if f:
                files.append(f)
        view = MultiPostView(posts, BOORU_URL) if len(posts) > 1 else PostView(posts[0], BOORU_URL)
        send_kwargs = {
            "content": f"🔥 **Posts phổ biến {scale_label}** ({date or 'hôm nay'}):",
            "embeds": embeds,
            "view": view,
        }
        if files:
            send_kwargs["files"] = files
        await interaction.followup.send(**send_kwargs)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /popular scale=%s", scale)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /tag ──────────────────────────────────────────────────────────────────────
@bot.tree.command(name="tag", description="Xem thông tin tag và wiki Danbooru")
@app_commands.describe(name="Tên tag (dùng underscore, VD: hatsune_miku)")
async def cmd_tag(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    tag_name = name.lower().strip().replace(" ", "_")
    try:
        tag = await bot.booru.get_tag(tag_name)
        if not tag:
            await interaction.followup.send(
                embed=error_embed("Không tìm thấy tag", f"Tag `{tag_name}` không tồn tại.")
            )
            return
        wiki = await bot.booru.get_wiki(tag_name)
        embed = tag_embed(tag, wiki, BOORU_URL)
        await interaction.followup.send(embed=embed)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /tag name=%s", tag_name)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /related ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="related", description="Xem các tags liên quan")
@app_commands.describe(
    tags="Tag query cần tìm liên quan",
    category="Lọc theo loại tag (không bắt buộc)",
)
@app_commands.choices(category=[
    app_commands.Choice(name="General",   value="general"),
    app_commands.Choice(name="Artist",    value="artist"),
    app_commands.Choice(name="Copyright", value="copyright"),
    app_commands.Choice(name="Character", value="character"),
    app_commands.Choice(name="Meta",      value="meta"),
])
async def cmd_related(
    interaction: discord.Interaction,
    tags: str,
    category: str = None,
):
    await interaction.response.defer()
    try:
        data = await bot.booru.get_related_tags(tags, category)
        related = data.get("related_tags", [])[:15]
        if not related:
            await interaction.followup.send(
                embed=error_embed("Không có kết quả", f"Không tìm thấy tags liên quan cho `{tags}`.")
            )
            return

        CAT_LABELS = {0: "General", 1: "Artist", 3: "Copyright", 4: "Character", 5: "Meta"}
        CAT_COLORS = {0: 0xB0C4DE, 1: 0xFF0000, 3: 0x9400D3, 4: 0x00AA00, 5: 0xFF8C00}
        lines = []
        for rt in related:
            t = rt.get("tag", {})
            tname = t.get("name", "?")
            count = t.get("post_count", 0)
            cat   = t.get("category", 0)
            score = rt.get("cosine_similarity", 0)
            lines.append(f"`{tname}` — {count:,} posts | {CAT_LABELS.get(cat,'?')} | {score:.2f}")

        embed = discord.Embed(
            title=f"🔗 Tags liên quan: {tags}",
            url=f"{BOORU_URL}/related_tag?query={tags}",
            description="\n".join(lines),
            color=0x9400D3,
        )
        if category:
            embed.set_footer(text=f"Lọc theo: {category}")
        await interaction.followup.send(embed=embed)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /related tags=%s", tags)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /comment ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="comment", description="Xem các comment mới nhất của một post")
@app_commands.describe(post_id="ID của post cần xem comment")
async def cmd_comment(interaction: discord.Interaction, post_id: int):
    await interaction.response.defer()
    try:
        comments = await bot.booru.get_comments(post_id=post_id, limit=5)
        if not comments:
            await interaction.followup.send(
                embed=error_embed("Không có comment", f"Post #{post_id} chưa có comment nào.")
            )
            return
        embed = discord.Embed(
            title=f"💬 Comments – Post #{post_id}",
            url=f"{BOORU_URL}/posts/{post_id}",
            color=0x5865F2,
        )
        for c in comments:
            creator = c.get("creator", {})
            author = creator.get("name", "Anonymous") if isinstance(creator, dict) else str(creator)
            body = truncate(c.get("body", "*(trống)*"), 300)
            score = c.get("score", 0)
            score_str = f" ({'+'if score>=0 else ''}{score})" if score != 0 else ""
            embed.add_field(
                name=f"{author}{score_str}",
                value=body,
                inline=False,
            )
        embed.set_footer(text=f"danbooru • Post #{post_id}")
        await interaction.followup.send(embed=embed)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /comment post_id=%s", post_id)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /forum ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="forum", description="Tìm kiếm forum topic Danbooru")
@app_commands.describe(query="Từ khóa tìm kiếm (không bắt buộc)")
async def cmd_forum(interaction: discord.Interaction, query: str = ""):
    await interaction.response.defer()
    try:
        topics = await bot.booru.get_forum_topics(query=query, limit=5)
        if not topics:
            await interaction.followup.send(
                embed=error_embed("Không có kết quả", f"Không tìm thấy topic nào cho `{query}`.")
            )
            return
        embed = discord.Embed(
            title=f"📋 Forum Topics" + (f": {query}" if query else ""),
            url=f"{BOORU_URL}/forum_topics",
            color=0xFF8C00,
        )
        for t in topics:
            title    = t.get("title", "Không có tiêu đề")
            topic_id = t.get("id")
            response_count = t.get("response_count", 0)
            url = f"{BOORU_URL}/forum_topics/{topic_id}"
            embed.add_field(
                name=f"#{topic_id} – {truncate(title, 50)}",
                value=f"[Xem topic]({url}) • {response_count} replies",
                inline=False,
            )
        embed.set_footer(text=f"danbooru • {BOORU_URL}")
        await interaction.followup.send(embed=embed)
    except DanbooruError as e:
        await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
    except Exception as e:
        log.exception("Lỗi /forum query=%s", query)
        await interaction.followup.send(embed=error_embed("Lỗi", str(e)))


# ── /calc ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="calc", description="Tính toán biểu thức toán học")
@app_commands.describe(expression="Biểu thức toán học, VD: 2**10 + 5*3")
async def cmd_calc(interaction: discord.Interaction, expression: str):
    try:
        result = safe_eval(expression)
        if isinstance(result, float) and result.is_integer():
            result_str = f"{int(result):,}"
        else:
            result_str = f"{result:,.8g}"
        embed = discord.Embed(
            title="🔢 Máy tính",
            description=f"`{expression}` = **{result_str}**",
            color=0x00AA00,
        )
        await interaction.response.send_message(embed=embed)
    except ZeroDivisionError:
        await interaction.response.send_message(
            embed=error_embed("Lỗi", "Không thể chia cho 0."), ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            embed=error_embed("Biểu thức không hợp lệ", f"`{expression}`\n{e}"), ephemeral=True
        )


# ── /say ──────────────────────────────────────────────────────────────────────
@bot.tree.command(name="say", description="Cho Fumimi nói gì đó (cần quyền Manage Messages)")
@app_commands.describe(message="Nội dung cần nói")
@app_commands.default_permissions(manage_messages=True)
async def cmd_say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("✅ Đã gửi!", ephemeral=True)
    await interaction.channel.send(message)


# ═══════════════════════════════════════════════════════════════════════════════
# Autocomplete cho /posts và /tag
# ═══════════════════════════════════════════════════════════════════════════════

@cmd_posts.autocomplete("tags")
@cmd_random.autocomplete("tags")
async def autocomplete_tags(interaction: discord.Interaction, current: str):
    if not current or len(current) < 2:
        return []
    try:
        results = await bot.booru.autocomplete_tags(current, limit=10)
        return [
            app_commands.Choice(
                name=f"{r.get('value', '')} ({r.get('post_count', 0):,})",
                value=r.get("value", ""),
            )
            for r in results
        ][:25]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-embed: tự động nhận và embed link Danbooru post
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    matches = POST_URL_RE.findall(message.content)
    if matches:
        embeds = []
        files = []
        fetched_posts = []
        session = await bot.booru._get_session()
        for post_id_str in matches[:3]:  # tối đa 3 embed mỗi tin
            try:
                post = await bot.booru.get_post(int(post_id_str))
                emb, f = await prepare_post_display(post, message.channel, BOORU_URL, session)
                embeds.append(emb)
                if f:
                    files.append(f)
                fetched_posts.append(post)
            except DanbooruError as e:
                log.warning("Không embed được post %s: %s", post_id_str, e.message)
            except Exception as e:
                log.warning("Lỗi embed post %s: %s", post_id_str, e)
        if embeds:
            view = MultiPostView(fetched_posts, BOORU_URL) if len(fetched_posts) > 1 else PostView(fetched_posts[0], BOORU_URL)
            reply_kwargs = {
                "embeds": embeds,
                "view": view,
                "mention_author": False,
            }
            if files:
                reply_kwargs["files"] = files
            await message.reply(**reply_kwargs)

    await bot.process_commands(message)


# ═══════════════════════════════════════════════════════════════════════════════
# Bot events & Sync quản trị
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    log.info("✅ Đăng nhập thành công: %s (ID: %s)", bot.user, bot.user.id)
    log.info("📡 Đang kết nối với %d server(s).", len(bot.guilds))

    # Tự động đồng bộ vào từng server để xóa sạch command Ruby cũ và kích hoạt command mới tức thì
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            log.info("Đã đồng bộ %d lệnh mới cho server: %s (%d)", len(synced), guild.name, guild.id)
        except Exception as e:
            log.warning("Không thể sync cho server %s: %s", guild.name, e)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Danbooru 🌸",
        )
    )


@bot.command(name="sync")
async def cmd_manual_sync(ctx: commands.Context):
    """
    Lệnh !sync: Dùng trong chat Discord để cưỡng chế dọn sạch command Ruby cũ
    và cập nhật toàn bộ slash command mới ngay lập tức.
    """
    if not ctx.author.guild_permissions.administrator and not await bot.is_owner(ctx.author):
        await ctx.send("❌ Bạn cần quyền Quản trị viên (Administrator) để dùng lệnh này.")
        return

    msg = await ctx.send("🔄 Đang dọn sạch lệnh cũ từ bot Ruby và cập nhật lệnh mới...")
    try:
        # Xóa sạch các lệnh cũ của server
        bot.tree.clear_commands(guild=ctx.guild)
        await bot.tree.sync(guild=ctx.guild)

        # Chép toàn bộ lệnh mới vào server này
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)

        # Đồng bộ global
        await bot.tree.sync()

        await msg.edit(
            content=(
                f"✅ **Thành công!** Đã xóa sạch lệnh cũ và kích hoạt **{len(synced)}** lệnh mới cho server!\n"
                f"*(Nếu chưa thấy đổi ngay, hãy bấm **Ctrl + R** trên Discord để làm mới bộ nhớ đệm nhé)*"
            )
        )
    except Exception as e:
        log.exception("Lỗi khi sync commands: %s", e)
        await msg.edit(content=f"❌ Lỗi khi đồng bộ: {e}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    log.error("Command error: %s", error)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN, log_handler=None)

