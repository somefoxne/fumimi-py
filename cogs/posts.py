"""
Cog quản lý các lệnh tìm kiếm và hiển thị bài đăng (Posts) trên Danbooru.
Bao gồm:
  /post     – Xem post theo ID
  /posts    – Tìm kiếm posts theo tags
  /random   – Post ngẫu nhiên
  /popular  – Posts phổ biến theo ngày / tuần / tháng
  on_message – Tự động nhúng link Danbooru post khi paste vào chat
"""

import re
import logging
import discord
from discord import app_commands
from discord.ext import commands

import settings
from danbooru_client import DanbooruError
from embeds import (
    error_embed,
    prepare_post_display,
    PostView,
    MultiPostView,
)

log = logging.getLogger("fumimi.cogs.posts")


class PostCommands(commands.Cog, name="Posts"):
    def __init__(self, bot):
        self.bot = bot
        self.booru_url = settings.get_active_booru_url()
        self.post_url_re = self._build_post_url_re()

    def _build_post_url_re(self) -> re.Pattern:
        domains = "|".join(re.escape(d) for d in settings.BOORU_DOMAINS)
        return re.compile(
            rf"https?://(?:{domains})/posts/(\d+)",
            re.IGNORECASE,
        )

    # ── Autocomplete ───────────────────────────────────────────────────────────
    async def tag_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if not current or len(current) < 2:
            return []
        try:
            results = await self.bot.booru.autocomplete_tags(current, limit=10)
            return [
                app_commands.Choice(
                    name=f"{r.get('value', '')} ({r.get('post_count', 0):,})",
                    value=r.get("value", ""),
                )
                for r in results
            ][:25]
        except Exception:
            return []

    # ── /post ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="post", description="Xem một post Danbooru theo ID")
    @app_commands.describe(post_id="ID của post cần xem")
    async def cmd_post(self, interaction: discord.Interaction, post_id: int):
        await interaction.response.defer()
        try:
            post = await self.bot.booru.get_post(post_id)
            session = await self.bot.booru._get_session()
            embed, file = await prepare_post_display(post, interaction.channel, self.booru_url, session)
            view = PostView(post, self.booru_url)
            if file:
                await interaction.followup.send(embed=embed, file=file, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        except DanbooruError as e:
            await interaction.followup.send(embed=error_embed("Không tìm thấy post", e.message))
        except discord.errors.HTTPException as e:
            if e.code == 20009:
                await interaction.followup.send(
                    content="🔞 **Nội dung nhạy cảm:** Discord đã chặn gửi nội dung này tại kênh thông thường. Vui lòng bật **Giới hạn độ tuổi (18+)** cho kênh hoặc bấm nút Tải về bên dưới!",
                    view=view if "view" in locals() else discord.utils.MISSING,
                )
            else:
                await interaction.followup.send(embed=error_embed("Lỗi Discord", str(e)))
        except Exception as e:
            log.exception("Lỗi khi lấy post %s", post_id)
            await interaction.followup.send(embed=error_embed("Lỗi", str(e)))

    # ── /posts ────────────────────────────────────────────────────────────────
    @app_commands.command(name="posts", description="Tìm kiếm post Danbooru theo tags")
    @app_commands.describe(
        tags="Tags tìm kiếm (cách nhau bằng dấu cách, VD: hatsune_miku solo)",
        limit="Số kết quả (1–4, mặc định 3)",
        page="Trang kết quả (mặc định 1)",
    )
    async def cmd_posts(
        self,
        interaction: discord.Interaction,
        tags: str = "",
        limit: app_commands.Range[int, 1, 4] = 3,
        page: app_commands.Range[int, 1, 1000] = 1,
    ):
        await interaction.response.defer()
        try:
            posts = await self.bot.booru.get_posts(tags=tags, limit=limit, page=page)
            if not posts:
                await interaction.followup.send(
                    embed=error_embed("Không có kết quả", f"Không tìm thấy post nào cho `{tags or '(tất cả)'}`.")
                )
                return
            session = await self.bot.booru._get_session()
            embeds = []
            files = []
            for p in posts:
                emb, f = await prepare_post_display(p, interaction.channel, self.booru_url, session)
                embeds.append(emb)
                if f:
                    files.append(f)
            view = MultiPostView(posts, self.booru_url) if len(posts) > 1 else PostView(posts[0], self.booru_url)
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
        except discord.errors.HTTPException as e:
            if e.code == 20009:
                await interaction.followup.send(
                    content="🔞 **Nội dung nhạy cảm:** Discord đã chặn hiển thị ảnh này tại kênh thông thường vì nội dung giới hạn độ tuổi. Vui lòng sử dụng tại kênh 18+ hoặc bấm nút Tải về bên dưới!",
                    view=view if "view" in locals() else discord.utils.MISSING,
                )
            else:
                await interaction.followup.send(embed=error_embed("Lỗi Discord", str(e)))
        except Exception as e:
            log.exception("Lỗi /posts tags=%s", tags)
            await interaction.followup.send(embed=error_embed("Lỗi", str(e)))

    @cmd_posts.autocomplete("tags")
    async def autocomplete_posts_tags(self, interaction: discord.Interaction, current: str):
        return await self.tag_autocomplete(interaction, current)

    # ── /random ───────────────────────────────────────────────────────────────
    @app_commands.command(name="random", description="Xem một post ngẫu nhiên từ Danbooru")
    @app_commands.describe(tags="Tags lọc (không bắt buộc)")
    async def cmd_random(self, interaction: discord.Interaction, tags: str = ""):
        await interaction.response.defer()
        try:
            post = await self.bot.booru.get_random_post(tags=tags)
            session = await self.bot.booru._get_session()
            embed, file = await prepare_post_display(post, interaction.channel, self.booru_url, session)
            view = PostView(post, self.booru_url)
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
        except discord.errors.HTTPException as e:
            if e.code == 20009:
                await interaction.followup.send(
                    content="🔞 **Nội dung nhạy cảm:** Discord đã chặn gửi nội dung này tại kênh thông thường. Vui lòng bật **Giới hạn độ tuổi (18+)** cho kênh hoặc bấm nút Tải về bên dưới!",
                    view=view if "view" in locals() else discord.utils.MISSING,
                )
            else:
                await interaction.followup.send(embed=error_embed("Lỗi Discord", str(e)))
        except Exception as e:
            log.exception("Lỗi /random tags=%s", tags)
            await interaction.followup.send(embed=error_embed("Lỗi", str(e)))

    @cmd_random.autocomplete("tags")
    async def autocomplete_random_tags(self, interaction: discord.Interaction, current: str):
        return await self.tag_autocomplete(interaction, current)

    # ── /popular ──────────────────────────────────────────────────────────────
    @app_commands.command(name="popular", description="Xem posts phổ biến trên Danbooru")
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
        self,
        interaction: discord.Interaction,
        scale: str = "day",
        date: str = None,
    ):
        await interaction.response.defer()
        try:
            posts = await self.bot.booru.get_popular_posts(date=date, scale=scale, limit=4)
            if not posts:
                await interaction.followup.send(
                    embed=error_embed("Không có dữ liệu", "Không có posts phổ biến nào.")
                )
                return
            scale_label = {"day": "hôm nay", "week": "tuần này", "month": "tháng này"}.get(scale, scale)
            session = await self.bot.booru._get_session()
            embeds = []
            files = []
            for p in posts:
                emb, f = await prepare_post_display(p, interaction.channel, self.booru_url, session)
                embeds.append(emb)
                if f:
                    files.append(f)
            view = MultiPostView(posts, self.booru_url) if len(posts) > 1 else PostView(posts[0], self.booru_url)
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
        except discord.errors.HTTPException as e:
            if e.code == 20009:
                await interaction.followup.send(
                    content="🔞 **Nội dung nhạy cảm:** Discord đã chặn hiển thị ảnh này tại kênh thông thường vì nội dung giới hạn độ tuổi. Vui lòng sử dụng tại kênh 18+ hoặc bấm nút Tải về bên dưới!",
                    view=view if "view" in locals() else discord.utils.MISSING,
                )
            else:
                await interaction.followup.send(embed=error_embed("Lỗi Discord", str(e)))
        except Exception as e:
            log.exception("Lỗi /popular scale=%s", scale)
            await interaction.followup.send(embed=error_embed("Lỗi", str(e)))

    # ── Auto-embed link Danbooru trong chat ─────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        matches = self.post_url_re.findall(message.content)
        if matches:
            embeds = []
            files = []
            fetched_posts = []
            session = await self.bot.booru._get_session()
            for post_id_str in matches[:3]:  # tối đa 3 embed mỗi tin
                try:
                    post = await self.bot.booru.get_post(int(post_id_str))
                    emb, f = await prepare_post_display(post, message.channel, self.booru_url, session)
                    embeds.append(emb)
                    if f:
                        files.append(f)
                    fetched_posts.append(post)
                except DanbooruError as e:
                    log.warning("Không embed được post %s: %s", post_id_str, e.message)
                except Exception as e:
                    log.warning("Lỗi embed post %s: %s", post_id_str, e)
            if embeds:
                view = MultiPostView(fetched_posts, self.booru_url) if len(fetched_posts) > 1 else PostView(fetched_posts[0], self.booru_url)
                reply_kwargs = {
                    "embeds": embeds,
                    "view": view,
                    "mention_author": False,
                }
                try:
                    if files:
                        reply_kwargs["files"] = files
                    await message.reply(**reply_kwargs)
                except discord.errors.HTTPException as e:
                    if e.code == 20009:
                        await message.reply(
                            content="🔞 **Nội dung nhạy cảm:** Discord đã chặn hiển thị trực tiếp ảnh này tại kênh thông thường vì nội dung 18+. Vui lòng dùng tại kênh Giới hạn độ tuổi hoặc bấm nút Tải về!",
                            view=view,
                            mention_author=False,
                        )
                    else:
                        log.warning("Lỗi gửi reply embed: %s", e)


async def setup(bot):
    await bot.add_cog(PostCommands(bot))
