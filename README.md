# Fumimi Discord Bot (Python)

A modern Python rewrite of the official [danbooru/fumimi-discord](https://github.com/danbooru/fumimi-discord) bot, built with **discord.py 2.x**, **aiohttp**, and the Danbooru REST API.

Modularized with the standard Discord Cog architecture, feature-rich, and ready to deploy on any Python hosting service, VPS, or GitHub Codespaces.

---

## Slash Commands

### Posts (`cogs/posts.py`)
| Command | Description |
|---|---|
| `/posts [tags] [limit]` | Search posts by tags with autocomplete *(limit: 1–10, default: 3)* |
| `/post <post_id>` | View a Danbooru post by ID |
| `/random [tags]` | Fetch a random post matching optional tags |
| `/popular [scale] [date]` | Browse top posts by timeframe (`day`, `week`, `month`) |

### Tags & Wiki (`cogs/tags.py`)
| Command | Description |
|---|---|
| `/tag <name>` | Look up tag metadata, category, post count, and wiki summary |
| `/related_tags <tags> [category]` | Discover related tags with cosine similarity score |
| `/related <tags> [category]` | Shorthand alias for `/related_tags` |

### Reports & Stats (`cogs/reports.py`)
| Command | Description |
|---|---|
| `/top_uploaders [tags] [limit]` | Display ASCII box-drawing table of top 25 uploaders for a tag query |
| `/count [tags]` | Count total matching posts on Danbooru |

### Forum & Comments (`cogs/forum.py`)
| Command | Description |
|---|---|
| `/comment <post_id>` | Show the latest 5 comments on a specific post |
| `/forum [query]` | Search Danbooru forum topics |

### Utilities (`cogs/utility.py`)
| Command | Description |
|---|---|
| `/hi` | Greet the bot |
| `/calc <expression>` | Safely evaluate mathematical expressions (AST-based, no `eval`) |
| `/say <message>` | Echo a message through the bot *(requires Manage Messages permission)* |
| `!sync` *(Prefix Command)* | Clean up duplicate guild commands and resynchronize global slash commands *(Admin only)* |

---

## Project Structure

```text
fumimi-py/
├── cogs/
│   ├── posts.py          # /posts, /post, /random, /popular, and auto-embed listener
│   ├── tags.py           # /tag, /related_tags, /related
│   ├── reports.py        # /top_uploaders (ASCII box table), /count
│   ├── forum.py          # /comment, /forum
│   └── utility.py        # /hi, /calc, /say, !sync
├── bot.py                # Bot initialization & dynamic Cog loader
├── danbooru_client.py    # Async Danbooru REST API client
├── embeds.py             # Embed generation, button views & ASCII table renderer
├── settings.py           # Environment variable loader & URL configurations
├── requirements.txt      # Python dependencies
└── .env.example          # Environment configuration template
```

---

## Getting Started

### 1. Prerequisites
- Python 3.10+
- A Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))

### 2. Discord Application Configuration
1. Create a **New Application** at the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **Bot**, toggle **ON** the **Message Content Intent** (required for link auto-embedding and `!sync`).
3. Under **OAuth2 → URL Generator**, select scopes `bot` and `applications.commands`, grant permissions (Send Messages, Embed Links, Attach Files, Read Message History), and invite the bot to your server.

### 3. Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/somefoxne/fumimi-py.git
cd fumimi-py
pip install -r requirements.txt
```

### 4. Configuration

Copy the sample environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```dotenv
# Required
DISCORD_TOKEN=your_discord_bot_token_here

# Optional: Danbooru API credentials (increases rate limits)
DANBOORU_USERNAME=your_username
DANBOORU_API_KEY=your_api_key

# Optional: Testing with Testbooru
TEST_MODE=false
```

### 5. Running the Bot

```bash
python bot.py
```

---

## Maintenance & Troubleshooting

- **Duplicate Slash Commands:**
  Discord may cache commands registered at both guild and global scopes. Simply send `!sync` in any channel where the bot has access, or press `Ctrl + R` in Discord to refresh your client cache.
- **Explicit Content Filter (Error 20009):**
  In non-NSFW channels, Fumimi automatically replaces direct image attachments of Rating Q/E posts with a spoiler warning and a direct download button. Enable the **Age-Restricted Channel (18+)** toggle on your Discord channel settings for full inline image previews.

---

## License & Credits

- Original Ruby implementation: [danbooru/fumimi-discord](https://github.com/danbooru/fumimi-discord)
- Danbooru API Documentation: [danbooru.donmai.us/wiki_pages/help:api](https://danbooru.donmai.us/wiki_pages/help:api)
