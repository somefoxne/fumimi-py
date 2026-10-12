"""
Cog quản lý các lệnh thống kê, báo cáo và đếm bài trên Danbooru.
Bao gồm:
  /top_uploaders – Bảng ASCII box-drawing top 25 người đăng bài nhiều nhất
  /count         – Đếm tổng số bài viết theo tags
"""

import logging
import urllib.parse
import discord
from discord import app_commands
from discord.ext import commands

import settings
from danbooru_client import DanbooruError
from embeds import error_embed, render_top_uploaders_table

log = logging.getLogger("fumimi.cogs.reports")


class ReportCommands(commands.Cog, name="Reports"):
    def __init__(self, bot):
        self.bot = bot
        self.booru_url = settings.get_active_booru_url()

    # ── Tag Autocomplete ───────────────────────────────────────────────────────
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

    # ── /count ────────────────────────────────────────────────────────────────
    @app_commands.command(name="count", description="Đếm số post theo tags")
    @app_commands.describe(tags="Tags tìm kiếm (không bắt buộc)")
    async def cmd_count(self, interaction: discord.Interaction, tags: str = ""):
        await interaction.response.defer()
        try:
            count = await self.bot.booru.get_post_count(tags=tags)
            label = f"`{tags}`" if tags else "tất cả posts"
            search_url = f"{self.booru_url}/posts?tags={tags}" if tags else f"{self.booru_url}/posts"

            if count is None:
                estimated = await self.bot.booru.estimate_post_count(tags=tags)
                if estimated is not None:
                    est_str = f"📊 **Ước tính xấp xỉ:** `~{estimated:,}` posts *(dựa trên mật độ ID)*\n\n"
                else:
                    est_str = ""

                embed = discord.Embed(
                    title="📊 Không thể đếm số lượng post chính xác",
                    description=(
                        f"⚠️ Danbooru bị timeout khi tính toán số lượng chính xác cho {label}.\n\n"
                        f"{est_str}"
                        f"**Nguyên nhân:** Các truy vấn phức tạp hoặc chứa thẻ phủ định (`-`), ký tự đại diện (`*`) "
                        f"quá tốn kém để cơ sở dữ liệu đếm chính xác.\n"
                        f"🔗 [Bấm vào đây để xem kết quả bài đăng trên Danbooru]({search_url})"
                    ),
                    color=0xFEE75C,
                )
                embed.set_footer(text=f"danbooru • {self.booru_url}")
                await interaction.followup.send(embed=embed)
                return

            embed = discord.Embed(
                title="📊 Số lượng post",
                description=f"**[{count:,} posts]({search_url})** khớp với {label}",
                color=0x5865F2,
            )
            embed.set_footer(text=f"danbooru • {self.booru_url}")
            await interaction.followup.send(embed=embed)
        except DanbooruError as e:
            await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
        except Exception as e:
            log.exception("Lỗi /count tags=%s", tags)
            await interaction.followup.send(embed=error_embed("Lỗi", str(e)))

    # ── /top_uploaders ────────────────────────────────────────────────────────
    @app_commands.command(name="top_uploaders", description="Show top uploaders for a tag search.")
    @app_commands.describe(
        tags="Tags to search for.",
        limit="Number of uploaders to show (default: 25).",
    )
    async def cmd_top_uploaders(
        self,
        interaction: discord.Interaction,
        tags: str = "",
        limit: app_commands.Range[int, 0, 25] = 25,
    ):
        await interaction.response.defer()
        try:
            clean_tags = tags.strip()
            api_limit = 25 if (limit == 0 or limit is None) else limit

            total_posts_raw = await self.bot.booru.get_post_count(tags=clean_tags)
            total_posts = total_posts_raw or 0
            report = await self.bot.booru.get_top_uploaders(tags=clean_tags, limit=api_limit)

            report_url = f"{self.booru_url}/reports/posts?search[group]=uploader&search[group_limit]=25"
            if clean_tags:
                report_url += f"&search[tags]={urllib.parse.quote(clean_tags)}"

            if not report:
                tag_desc = f"Report for tags: `{clean_tags}`.\n\n" if clean_tags else ""
                embed = discord.Embed(
                    title="Top Uploaders Report",
                    url=report_url,
                    description=f"{tag_desc}No posts under that search!",
                    color=0x206694,
                    timestamp=discord.utils.utcnow(),
                )
                await interaction.followup.send(embed=embed)
                return

            headers = ["Name", "Uploads", "%"]
            rows = []
            for row in report:
                uname = row.get("uploader", "Unknown")
                posts_cnt = row.get("posts", 0)
                pct_str = f"{(posts_cnt / total_posts * 100):.2f}" if total_posts > 0 else "N/A"
                rows.append([uname, f"{posts_cnt:,}", pct_str])

            table_str = render_top_uploaders_table(headers, rows)

            desc_parts = ["Results may be cached for 1 hour."]
            if clean_tags:
                desc_parts.append(f"Report for tags: `{clean_tags}`.")
            desc_parts.append(table_str)

            embed = discord.Embed(
                title="Top Uploaders Report",
                url=report_url,
                description="\n".join(desc_parts),
                color=0x206694,
                timestamp=discord.utils.utcnow(),
            )

            await interaction.followup.send(embed=embed)
        except DanbooruError as e:
            await interaction.followup.send(embed=error_embed("Lỗi API", e.message))
        except Exception as e:
            log.exception("Lỗi /top_uploaders tags=%s", tags)
            await interaction.followup.send(embed=error_embed("Lỗi", str(e)))

    # Đăng ký autocomplete
    @cmd_count.autocomplete("tags")
    @cmd_top_uploaders.autocomplete("tags")
    async def autocomplete_tags_delegate(self, interaction: discord.Interaction, current: str):
        return await self.tag_autocomplete(interaction, current)


async def setup(bot):
    await bot.add_cog(ReportCommands(bot))
