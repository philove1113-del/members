import discord
from discord.ext import commands
from flask import Flask, request
import requests
from threading import Thread
import os
import time
from discord.ext import tasks
from datetime import datetime
import pytz
from urllib.parse import quote
from waitress import serve
import asyncio

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

REDIRECT_URI = "https://members-production-ea8f.up.railway.app/callback"

ENCODED_REDIRECT_URI = quote(
    REDIRECT_URI,
    safe=""
)

RESTOCK_CHANNEL_ID = 1502766892186861568

# =========================
# INTENTS
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="?",
    intents=intents
)

# =========================
# STORAGE
# =========================

# user_id : access_token
authorized_users = {}

# user_id : timestamps
join_history = {}

# Member lifetime usage
member_used = set()

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not restock_task.is_running():
        restock_task.start()

# =========================
# LOGIN COMMAND
# =========================

@bot.command()
async def login(ctx):

    oauth_url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={ENCODED_REDIRECT_URI}"
        "&response_type=code"
        "&scope=identify%20guilds.join"
    )

    embed = discord.Embed(
        title="Authorize",
        description=f"[Click Here]({oauth_url})",
        color=0x5865F2
    )

    await ctx.send(embed=embed)

# =========================
# BOT INVITE COMMAND
# =========================

@bot.command()
async def botinvite(ctx):

    perms = discord.Permissions(administrator=True)

    invite_url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&permissions={perms.value}"
        "&scope=bot"
    )

    embed = discord.Embed(
        title="Invite The Bot",
        description=f"[Click Here To Invite]({invite_url})",
        color=0x57F287
    )

    await ctx.send(embed=embed)

# =========================
# ROLE LIMITS
# =========================

def get_limit(member):

    role_names = [role.name for role in member.roles]

    if "Tier 3" in role_names:
        return "Tier 3", 5

    if "Tier 2" in role_names:
        return "Tier 2", 2

    if "Tier 1" in role_names:
        return "Tier 1", 1

    if "Member" in role_names:
        return "Member", 1

    return None, 0

# =========================
# JOIN COMMAND
# =========================

@bot.command()
async def idjoin(ctx, server_id: int):

    role_name, limit = get_limit(ctx.author)

    if limit == 0:
        await ctx.send("❌ You do not have a valid role.")
        return

    guild = bot.get_guild(server_id)

    if guild is None:
        await ctx.send("❌ Bot is not in that server.")
        return

    if not authorized_users:
        await ctx.send("❌ No authorized users available.")
        return

    # Use first authorized user
    user_id = next(iter(authorized_users))
    access_token = authorized_users[user_id]

    now = time.time()

    if user_id not in join_history:
        join_history[user_id] = []

    # Member role = one lifetime use
    if role_name == "Member":

        if ctx.author.id in member_used:
            await ctx.send(
                "❌ Member role can only use ?idjoin once ever."
            )
            return

    else:

        # Remove entries older than 24h
        join_history[user_id] = [
            t for t in join_history[user_id]
            if now - t < 86400
        ]

        if len(join_history[user_id]) >= limit:
            await ctx.send(
                f"❌ Daily limit reached ({limit}/{limit})"
            )
            return

    url = f"https://discord.com/api/v10/guilds/{server_id}/members/{user_id}"

    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "access_token": access_token
    }

    response = requests.put(
        url,
        headers=headers,
        json=data
    )

    if response.status_code in [201, 204]:

        if role_name == "Member":
            member_used.add(ctx.author.id)
        else:
            join_history[user_id].append(now)

        await ctx.send(
            "✅ Joined successfully using authorized account."
        )

    else:
        await ctx.send(
            f"❌ Failed\n```{response.text}```"
        )

# =========================
# STOCK COMMAND
# =========================

@bot.command()
async def stock(ctx):

    stock_count = len(authorized_users)

    embed = discord.Embed(
        title="Member Stock",
        description=f"📦 Authorized Members: **{stock_count}**",
        color=0x5865F2
    )

    embed.set_footer(
        text="Updates automatically when users authorize."
    )

    await ctx.send(embed=embed)

# =========================
# WEB SERVER
# =========================

web = Flask(__name__)

@web.route("/")
def home():
    return "Bot Running"

@web.route("/health")
def health():
    return "OK", 200

@web.route("/callback")
def callback():

    code = request.args.get("code")

    if not code:
        return "No code provided."

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify guilds.join"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    token_response = requests.post(
        "https://discord.com/api/oauth2/token",
        data=data,
        headers=headers
    )

    token_json = token_response.json()

    access_token = token_json.get("access_token")

    if not access_token:
        return f"Authorization failed.<br><br>{token_json}"

    user_response = requests.get(
        "https://discord.com/api/users/@me",
        headers={
            "Authorization": f"Bearer {access_token}"
        }
    )

    user_json = user_response.json()

    user_id = int(user_json["id"])

    authorized_users[user_id] = access_token

    return """
    <h1>Authorized Successfully</h1>
    You may now use ?idjoin SERVER_ID
    """

# =========================
# RESTOCK TASK
# =========================

@tasks.loop(minutes=1)
async def restock_task():

    timezone = pytz.timezone("America/Los_Angeles")
    now = datetime.now(timezone)

    # 7:30 AM PDT/PST
    if now.hour == 7 and now.minute == 30:

        channel = bot.get_channel(RESTOCK_CHANNEL_ID)

        if channel is None:
            return

        stock_count = len(authorized_users)

        embed = discord.Embed(
            title="Restock",
            description=(
                f"The bot has restocked.\n\n"
                f"**{stock_count}** authorized members are now available.\n\n"
                f"React to this message for more restocks."
            ),
            color=0x57F287
        )

        embed.set_footer(
            text="Automatic Daily Restock"
        )

        message = await channel.send(embed=embed)

        await message.add_reaction("✅")

        # Prevent duplicate sends
        await asyncio.sleep(60)

# =========================
# START WEB SERVER
# =========================

def run_web():

    PORT = int(os.environ.get("PORT", 8080))

    print(f"Web server starting on port {PORT}")

    serve(
        web,
        host="0.0.0.0",
        port=PORT
        threads=8
    )

# Start web server in background thread
web_thread = Thread(target=run_web)

web_thread.start()

# =========================
# START DISCORD BOT
# =========================

bot.run(BOT_TOKEN)
