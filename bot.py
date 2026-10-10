"""
Fumimi – Danbooru Discord Bot (Python)
======================================
Tham khảo:
  - https://github.com/danbooru/fumimi-discord
  - https://danbooru.donmai.us/wiki_pages/help:api

Kiến trúc mô-đun (Cogs):
  - cogs/posts.py   : /post, /posts, /random, /popular, auto-embed link Danbooru
  - cogs/tags.py    : /tag, /related_tags, /related
  - cogs/reports.py : /top_uploaders, /count
  - cogs/forum.py   : /comment, /forum
  - cogs/utility.py : /hi, /calc, /say, !sync
"""

import os
import sys
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv

import settings
from danbooru_client import DanbooruClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("fumimi")

DISCORD_TOKEN = settings.DISCORD_TOKEN

# ── Cấu hình Intents ───────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # Bắt buộc để đọc tin nhắn (auto-embed link danbooru & lệnh !sync)


class FumimiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.booru = DanbooruClient()

    async def setup_hook(self):
        # Nạp tất cả các Cog mô-đun trong thư mục cogs/
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    cog_name = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(cog_name)
                        log.info("✅ Đã nạp extension: %s", cog_name)
                    except Exception as e:
                        log.exception("❌ Lỗi khi nạp extension %s: %s", cog_name, e)

        # Đồng bộ Slash Commands lên Discord (Global)
        try:
            synced = await self.tree.sync()
            log.info("🚀 Slash commands đã đồng bộ thành công (%d lệnh).", len(synced))
        except Exception as e:
            log.exception("❌ Lỗi đồng bộ slash commands: %s", e)

    async def close(self):
        await self.booru.close()
        await super().close()


bot = FumimiBot()


@bot.event
async def on_ready():
    log.info("✅ Đăng nhập thành công: %s (ID: %s)", bot.user, bot.user.id)
    log.info("📡 Đang kết nối với %d server(s).", len(bot.guilds))

    # Dọn dẹp lệnh cấp guild để tránh bị trùng lặp (dupe) với lệnh global
    for guild in bot.guilds:
        try:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        except Exception as e:
            log.warning("Không thể dọn guild commands cho %s: %s", guild.name, e)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Danbooru 🌸",
        )
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    log.error("Lỗi command: %s", error)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        log.error("Thiếu DISCORD_TOKEN trong file .env hoặc biến môi trường!")
        sys.exit(1)
    bot.run(DISCORD_TOKEN, log_handler=None)
