"""
Cog quản lý các tiện ích hệ thống và lệnh quản trị.
Bao gồm:
  /hi   – Chào bot
  /calc – Tính toán biểu thức toán học an toàn
  /say  – Bot nói thay lời nhắn (cần quyền Manage Messages)
  !sync – Lệnh tiền tố dọn dẹp lệnh trùng lặp và đồng bộ lại Slash Commands
"""

import ast
import operator
import logging
import discord
from discord import app_commands
from discord.ext import commands

from embeds import error_embed

log = logging.getLogger("fumimi.cogs.utility")

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
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Không hỗ trợ kiểu dữ liệu này")
        if isinstance(node, ast.BinOp):
            op = _OPS.get(type(node.op))
            if op is None:
                raise ValueError("Toán tử không được hỗ trợ")
            return op(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _OPS.get(type(node.op))
            if op is None:
                raise ValueError("Toán tử không được hỗ trợ")
            return op(_eval(node.operand))
        raise ValueError("Biểu thức không hợp lệ")

    return _eval(tree)


class UtilityCommands(commands.Cog, name="Utility"):
    def __init__(self, bot):
        self.bot = bot

    # ── /hi ───────────────────────────────────────────────────────────────────
    @app_commands.command(name="hi", description="Chào Fumimi!")
    async def cmd_hi(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Chào {interaction.user.mention}! Mình là Fumimi, bot Danbooru của server này. 🌸\n"
            f"Dùng `/posts tags:...` để tìm ảnh nhé!"
        )

    # ── /calc ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="calc", description="Tính toán biểu thức toán học")
    @app_commands.describe(expression="Biểu thức toán học, VD: 2**10 + 5*3")
    async def cmd_calc(self, interaction: discord.Interaction, expression: str):
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

    # ── /say ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="say", description="Cho Fumimi nói gì đó")
    @app_commands.describe(message="Nội dung cần nói")
    async def cmd_say(self, interaction: discord.Interaction, message: str):
        await interaction.response.send_message(message)

    # ── !sync ─────────────────────────────────────────────────────────────────
    @commands.command(name="sync")
    async def cmd_manual_sync(self, ctx: commands.Context):
        """
        Lệnh !sync: Dùng trong chat Discord để dọn sạch lệnh trùng lặp (dupe)
        và đồng bộ lại danh sách lệnh chuẩn.
        """
        if not ctx.author.guild_permissions.administrator and not await self.bot.is_owner(ctx.author):
            await ctx.send("❌ Bạn cần quyền Quản trị viên (Administrator) để dùng lệnh này.")
            return

        msg = await ctx.send("🔄 Đang dọn sạch lệnh trùng lặp và đồng bộ lại...")
        try:
            # Xóa toàn bộ lệnh riêng cấp server (guild commands) để không bị nhân đôi (dupe)
            if ctx.guild:
                self.bot.tree.clear_commands(guild=ctx.guild)
                await self.bot.tree.sync(guild=ctx.guild)

            # Đồng bộ bộ lệnh chuẩn cấp Global
            synced = await self.bot.tree.sync()

            await msg.edit(
                content=(
                    f"✅ **Thành công!** Đã xóa sạch lệnh bị trùng lặp (dupe)!\n"
                    f"Hiện tại chỉ còn duy nhất **{len(synced)}** lệnh chuẩn.\n"
                    f"*(Bấm **Ctrl + R** trên Discord để làm mới bộ nhớ đệm nếu chưa cập nhật ngay nhé)*"
                )
            )
        except Exception as e:
            log.exception("Lỗi khi sync commands: %s", e)
            await msg.edit(content=f"❌ Lỗi khi đồng bộ: {e}")


async def setup(bot):
    await bot.add_cog(UtilityCommands(bot))
