"""
Fumimi – Danbooru Discord Bot (Python rewrite)
================================================
Slash commands implemented:
  /hi            – greet the bot
  /post          – show a post by ID
  /posts         – search posts by tags
  /tag           – look up a tag + wiki
  /count         – count posts matching tags
  /related       – related tags for a query
  /comment       – show recent comments on a post
  /forum         – search forum topics
  /calc          – evaluate a simple math expression
  /say           – make the bot say something (admin)

The bot also auto-embeds danbooru.donmai.us links pasted in chat.
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

from danbooru_client import DanbooruClient
from embeds import post_embed, tag_embed, error_embed, info_embed, truncate

# ── Setup ──────────────────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("fumimi")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
BOORU_URL = os.getenv("BOORU_URL", "https://danbooru.donmai.us")
BOORU_DOMAINS = os.getenv("BOORU_DOMAINS", "").split() or [
    re.sub(r"https?://", "", BOORU_URL)
]

# ── Bot setup ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # required for link auto-embed


class FumimiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.booru = DanbooruClient()

    async def setup_hook(self):
        await self.tree.sync()
        log.info("Slash commands synced.")

    async def close(self):
        await self.booru.close()
        await super().close()


bot = FumimiBot()

# ── Helper to build post-link regex ───────────────────────────────────────────
def _post_url_pattern() -> re.Pattern:
    domains = "|".join(re.escape(d) for d in BOORU_DOMAINS)
    return re.compile(
        rf"https?://(?:{domains})/posts/(\d+)",
        re.IGNORECASE,
    )


POST_URL_RE = _post_url_pattern()

# ── Safe math evaluator ────────────────────────────────────────────────────────
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Unsupported literal")
        if isinstance(node, ast.BinOp):
            op = _SAFE_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported operator: {type(node.op)}")
            return op(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op = _SAFE_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op)}")
            return op(_eval(node.operand))
        raise ValueError(f"Unsupported node: {type(node)}")

    return _eval(tree)


# ═══════════════════════════════════════════════════════════════════════════════
# Slash Commands
# ═══════════════════════════════════════════════════════════════════════════════

@bot.tree.command(name="hi", description="Say hi to Fumimi")
async def cmd_hi(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Hi, {interaction.user.mention}! I'm Fumimi, your friendly Danbooru bot. 🌸"
    )


# ── /post ──────────────────────────────────────────────────────────────────────
@bot.tree.command(name="post", description="Show a Danbooru post by ID")
@app_commands.describe(post_id="The numeric post ID")
async def cmd_post(interaction: discord.Interaction, post_id: int):
    await interaction.response.defer()
    try:
        post = await bot.booru.get_post(post_id)
        embed = post_embed(post, BOORU_URL)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        log.error("Error fetching post %s: %s", post_id, e)
        await interaction.followup.send(
            embed=error_embed("Post not found", f"Could not load post #{post_id}.")
        )


# ── /posts ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="posts", description="Search Danbooru posts by tags")
@app_commands.describe(
    tags="Tag search query (space-separated)",
    limit="Number of results to show (1–6)",
)
async def cmd_posts(
    interaction: discord.Interaction,
    tags: str = "",
    limit: app_commands.Range[int, 1, 6] = 3,
):
    await interaction.response.defer()
    try:
        posts = await bot.booru.get_posts(tags=tags, limit=limit)
        if not posts:
            await interaction.followup.send(
                embed=error_embed("No results", f"No posts found for `{tags or '(all)'}`.")
            )
            return
        embeds = [post_embed(p, BOORU_URL) for p in posts]
        await interaction.followup.send(embeds=embeds)
    except Exception as e:
        log.error("Error searching posts '%s': %s", tags, e)
        await interaction.followup.send(
            embed=error_embed("Error", f"Failed to search for `{tags}`.")
        )


# ── /count ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="count", description="Count Danbooru posts matching tags")
@app_commands.describe(tags="Tag search query (space-separated)")
async def cmd_count(interaction: discord.Interaction, tags: str = ""):
    await interaction.response.defer()
    try:
        count = await bot.booru.get_post_count(tags=tags)
        label = f"`{tags}`" if tags else "all posts"
        embed = info_embed(
            "Post Count",
            f"**{count:,}** posts matching {label}",
            color=0x5865F2,
        )
        embed.set_footer(text=f"danbooru • {BOORU_URL}")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        log.error("Error counting posts '%s': %s", tags, e)
        await interaction.followup.send(
            embed=error_embed("Error", "Could not fetch post count.")
        )


# ── /tag ───────────────────────────────────────────────────────────────────────
@bot.tree.command(name="tag", description="Look up a Danbooru tag and its wiki")
@app_commands.describe(name="The tag name (use underscores)")
async def cmd_tag(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    tag_name = name.lower().replace(" ", "_")
    try:
        tag = await bot.booru.get_tag(tag_name)
        if not tag:
            await interaction.followup.send(
                embed=error_embed("Tag not found", f"No tag named `{tag_name}`.")
            )
            return
        wiki = await bot.booru.get_wiki(tag_name)
        embed = tag_embed(tag, wiki, BOORU_URL)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        log.error("Error fetching tag '%s': %s", tag_name, e)
        await interaction.followup.send(
            embed=error_embed("Error", f"Failed to look up `{tag_name}`.")
        )


# ── /related ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="related", description="Show tags related to a query")
@app_commands.describe(
    tags="Tag query",
    category="Filter by category (general/artist/copyright/character)",
)
async def cmd_related(
    interaction: discord.Interaction,
    tags: str,
    category: str = None,
):
    await interaction.response.defer()
    category_map = {
        "general": "general",
        "artist": "artist",
        "copyright": "copyright",
        "character": "character",
        "meta": "meta",
    }
    cat = category_map.get((category or "").lower())
    try:
        data = await bot.booru.get_related_tags(tags, cat)
        related = data.get("related_tags", [])[:15]
        if not related:
            await interaction.followup.send(
                embed=error_embed("No related tags", f"No related tags found for `{tags}`.")
            )
            return
        lines = [
            f"`{rt['tag']['name']}` — {rt['tag']['post_count']:,} posts"
            for rt in related
            if "tag" in rt
        ]
        embed = info_embed(
            f"Related tags for: {tags}",
            "\n".join(lines) or "None",
            color=0x9400D3,
        )
        embed.set_footer(text=f"danbooru • {BOORU_URL}")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        log.error("Error getting related tags '%s': %s", tags, e)
        await interaction.followup.send(
            embed=error_embed("Error", f"Failed to get related tags for `{tags}`.")
        )


# ── /comment ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="comment", description="Show recent comments on a post")
@app_commands.describe(post_id="Post ID to fetch comments for")
async def cmd_comment(interaction: discord.Interaction, post_id: int):
    await interaction.response.defer()
    try:
        comments = await bot.booru.get_comments(post_id=post_id, limit=5)
        if not comments:
            await interaction.followup.send(
                embed=error_embed("No comments", f"No comments found for post #{post_id}.")
            )
            return
        embed = discord.Embed(
            title=f"Comments on Post #{post_id}",
            url=f"{BOORU_URL}/posts/{post_id}",
            color=0x5865F2,
        )
        for c in comments:
            creator = c.get("creator", {})
            author = creator.get("name", "Anonymous") if isinstance(creator, dict) else str(creator)
            body = truncate(c.get("body", ""), 256)
            embed.add_field(name=author, value=body, inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        log.error("Error fetching comments for post %s: %s", post_id, e)
        await interaction.followup.send(
            embed=error_embed("Error", f"Failed to load comments for post #{post_id}.")
        )


# ── /forum ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="forum", description="Search Danbooru forum topics")
@app_commands.describe(query="Keyword to search for in forum topics")
async def cmd_forum(interaction: discord.Interaction, query: str = ""):
    await interaction.response.defer()
    try:
        topics = await bot.booru.get_forum_topics(query=query, limit=5)
        if not topics:
            await interaction.followup.send(
                embed=error_embed("No results", f"No forum topics found for `{query}`.")
            )
            return
        embed = discord.Embed(
            title=f"Forum Topics: {query or '(recent)'}",
            url=f"{BOORU_URL}/forum_topics",
            color=0xFF8C00,
        )
        for t in topics:
            title = t.get("title", "Untitled")
            topic_id = t.get("id")
            url = f"{BOORU_URL}/forum_topics/{topic_id}"
            embed.add_field(
                name=title,
                value=f"[#{topic_id}]({url})",
                inline=False,
            )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        log.error("Error searching forum '%s': %s", query, e)
        await interaction.followup.send(
            embed=error_embed("Error", "Failed to search forum topics.")
        )


# ── /calc ──────────────────────────────────────────────────────────────────────
@bot.tree.command(name="calc", description="Evaluate a math expression")
@app_commands.describe(expression="A math expression, e.g. 2 ** 10 + 5 * 3")
async def cmd_calc(interaction: discord.Interaction, expression: str):
    try:
        result = _safe_eval(expression)
        # Format nicely
        if isinstance(result, float) and result.is_integer():
            result_str = f"{int(result):,}"
        else:
            result_str = f"{result:,.6g}"
        embed = info_embed(
            "Calculator",
            f"`{expression}` = **{result_str}**",
            color=0x00AA00,
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(
            embed=error_embed("Invalid expression", f"`{expression}` could not be evaluated.\n{e}"),
            ephemeral=True,
        )


# ── /say ───────────────────────────────────────────────────────────────────────
@bot.tree.command(name="say", description="Make Fumimi say something (Manage Messages required)")
@app_commands.describe(message="What should Fumimi say?")
@app_commands.default_permissions(manage_messages=True)
async def cmd_say(interaction: discord.Interaction, message: str):
    await interaction.response.send_message("✅ Sent!", ephemeral=True)
    await interaction.channel.send(message)


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-embed: danbooru post links
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    matches = POST_URL_RE.findall(message.content)
    if matches:
        embeds = []
        for post_id_str in matches[:3]:  # max 3 embeds per message
            try:
                post = await bot.booru.get_post(int(post_id_str))
                embeds.append(post_embed(post, BOORU_URL))
            except Exception as e:
                log.warning("Could not embed post %s: %s", post_id_str, e)
        if embeds:
            await message.reply(embeds=embeds, mention_author=False)

    await bot.process_commands(message)


# ═══════════════════════════════════════════════════════════════════════════════
# Lifecycle events
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Connected to %d guild(s).", len(bot.guilds))
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Danbooru 🌸",
        )
    )


@bot.event
async def on_command_error(ctx, error):
    log.error("Command error: %s", error)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN, log_handler=None)
