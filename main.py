import discord
from discord.ext import commands, tasks
from flask import Flask, request
import requests
from threading import Thread
import os
import time
from datetime import datetime
import pytz
from urllib.parse import quote

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

REDIRECT_URI = "https://members-production-7b5d.up.railway.app"
ENCODED_REDIRECT_URI = quote(REDIRECT_URI, safe="")

RESTOCK_CHANNEL_ID = 1502766892186861568

# =========================
# DISCORD BOT
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="?", intents=intents)

# =========================
# STORAGE
# =========================

authorized_users = {}   # user_id -> access_token
join_history = {}        # user_id -> timestamps
member_used = set()

# =========================
# RESTOCK TASK
# =========================

@tasks.loop(minutes=1)
async def restock_task():
    now = datetime.now(pytz.timezone("America/Los_Angeles"))

    if now.hour == 7 and now.minute == 30:

        channel = bot.get_channel(RESTOCK_CHANNEL_ID)
        if not channel:
            return

        embed = discord.Embed(
            title="Restock",
            description=(
                f"The bot has restocked.\n\n"
                f"**{len(authorized_users)}** authorized members available.\n\n"
                f"React for updates."
            ),
            color=0x57F287
        )

        msg = await channel.send(embed=embed)
        await msg.add_reaction("✅")

# =========================
# READY EVENT
# =========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not restock_task.is_running():
        restock_task.start()

# =========================
# COMMANDS
# =========================

@bot.command()
async def login(ctx):
    url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={ENCODED_REDIRECT_URI}"
        "&response_type=code"
        "&scope=identify%20guilds.join"
    )

    embed = discord.Embed(
        title="Authorize",
        description=f"[Click Here]({url})",
        color=0x5865F2
    )

    await ctx.send(embed=embed)


@bot.command()
async def botinvite(ctx):
    perms = discord.Permissions(administrator=True)

    url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&permissions={perms.value}"
        "&scope=bot"
    )

    await ctx.send(embed=discord.Embed(
        title="Invite Bot",
        description=f"[Click Here]({url})",
        color=0x57F287
    ))


def get_limit(member):
    roles = [r.name for r in member.roles]

    if "Tier 3" in roles:
        return "Tier 3", 5
    if "Tier 2" in roles:
        return "Tier 2", 2
    if "Tier 1" in roles:
        return "Tier 1", 1
    if "Member" in roles:
        return "Member", 1

    return None, 0


@bot.command()
async def idjoin(ctx, server_id: int):

    role_name, limit = get_limit(ctx.author)

    if limit == 0:
        return await ctx.send("❌ No valid role.")

    if not authorized_users:
        return await ctx.send("❌ No authorized users.")

    user_id = next(iter(authorized_users))
    token = authorized_users[user_id]

    now = time.time()
    join_history.setdefault(user_id, [])

    if role_name == "Member":
        if ctx.author.id in member_used:
            return await ctx.send("❌ One-time use only.")
    else:
        join_history[user_id] = [t for t in join_history[user_id] if now - t < 86400]

        if len(join_history[user_id]) >= limit:
            return await ctx.send("❌ Daily limit reached.")

    url = f"https://discord.com/api/v10/guilds/{server_id}/members/{user_id}"

    res = requests.put(
        url,
        headers={
            "Authorization": f"Bot {BOT_TOKEN}",
            "Content-Type": "application/json"
        },
        json={"access_token": token}
    )

    if res.status_code in (201, 204):
        if role_name == "Member":
            member_used.add(ctx.author.id)
        else:
            join_history[user_id].append(now)

        await ctx.send("✅ Joined successfully")
    else:
        await ctx.send(f"❌ Failed\n```{res.text}```")


@bot.command()
async def stock(ctx):
    await ctx.send(embed=discord.Embed(
        title="Stock",
        description=f"📦 Authorized: **{len(authorized_users)}**",
        color=0x5865F2
    ))

# =========================
# FLASK APP (FIXED FOR RAILWAY)
# =========================

app = Flask(__name__)    

@app.route("/")
def home():
    return "Bot Running"

@app.route("/health")
def health():
    return "OK", 200


@app.route("/callback")
def callback():

    code = request.args.get("code")
    if not code:
        return "No code"

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token = requests.post(
        "https://discord.com/api/oauth2/token",
        data=data,
        headers=headers
    ).json()

    access_token = token.get("access_token")
    if not access_token:
        return "Auth failed"

    user = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    authorized_users[int(user["id"])] = access_token

    return "Authorized successfully"

# =========================
# STARTUP (FIXED ORDER)
# =========================

def run_bot():
    bot.run(BOT_TOKEN)


def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# Flask MUST start first on Railway
Thread(target=run_web, daemon=True).start()

# Then bot
run_bot()




