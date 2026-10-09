# Fumimi Discord Bot (Python)

A Python rewrite of the [danbooru/fumimi-discord](https://github.com/danbooru/fumimi-discord) bot using **discord.py** and the Danbooru API.

## Slash Commands

| Command | Description |
|---|---|
| `/hi` | Say hi to Fumimi |
| `/post <id>` | Show a Danbooru post by ID |
| `/posts [tags] [limit]` | Search posts by tags |
| `/count [tags]` | Count posts matching tags |
| `/tag <name>` | Look up a tag and its wiki |
| `/related <tags>` | Show related tags |
| `/comment <post_id>` | Show recent comments on a post |
| `/forum [query]` | Search forum topics |
| `/calc <expression>` | Evaluate a math expression |
| `/say <message>` | Make Fumimi say something *(requires Manage Messages)* |

The bot also **auto-embeds** Danbooru post links posted in chat.

## Setup

### 1. Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** → give it a name
3. Go to **Bot** tab → click **Add Bot**
4. Under **Privileged Gateway Intents**, enable **Message Content Intent**
5. Copy your **Bot Token**
6. Go to **OAuth2 → URL Generator**, select `bot` + `applications.commands`, add permissions, copy the invite URL and add the bot to your server

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your DISCORD_TOKEN
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Bot

```bash
python bot.py
```

## Hosting on Render / Koyeb (Node.js/Python)

Since the service supports Python:

1. Push this project to GitHub (see below)
2. On Render: New → Web Service → connect your repo
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
3. Set environment variables in the Render dashboard

## Pushing to GitHub (First Time)

```bash
# 1. Install Git if not already installed
# 2. In the project folder, open a terminal and run:

git init
git add .
git commit -m "Initial commit: Fumimi Python bot"

# 3. Create a new repository on github.com (don't initialize with README)
# 4. Then run (replace YOUR_USERNAME and REPO_NAME):
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main
```
