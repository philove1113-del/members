import discord
from discord.ext import commands
from flask import Flask, request
import requests
import asyncio
import threading
from threading import Thread

# =========================
# CONFIG
# =========================

BOT_TOKEN = "BOT_TOKEN"
CLIENT_ID = "CLIENT_ID"
CLIENT_SECRET = "CLIENT_SECRET"

REDIRECT_URI = "http://localhost:5000/callback"

# =========================
# INTENTS
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="?",
    intents=intents
)

# user_id : access_token
authorized_users = {}

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# =========================
# LOGIN COMMAND
# =========================

@bot.command()
async def login(ctx):

    oauth_url = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
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
# JOIN COMMAND
# =========================

@bot.command()
async def idjoin(ctx, server_id: int):

    user_id = ctx.author.id

    # Authorized?
    if user_id not in authorized_users:
        await ctx.send("❌ Authorize first using ?login")
        return

    # Bot in server?
    guild = bot.get_guild(server_id)

    if guild is None:
        await ctx.send("❌ Bot is not in that server.")
        return

    access_token = authorized_users[user_id]

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
        await ctx.send("✅ Joined successfully.")
    else:
        await ctx.send(
            f"❌ Failed\n```{response.text}```"
        )

# =========================
# FLASK
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Running"

@app.route("/callback")
def callback():

    code = request.args.get("code")

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
        return "Authorization failed."

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
# START FLASK
# =========================

def run_flask():
    app.run(
        host="0.0.0.0",
        port=5000
    )

threading.Thread(target=run_flask).start()

# =========================
# START BOT
# =========================

# Instead of: bot.run(BOT_TOKEN)

async def run_bot():
    await bot.start(BOT_TOKEN)

def start_bot_thread():
    asyncio.run(run_bot())

# Start bot in a background thread
bot_thread = Thread(target=start_bot_thread, daemon=True)
bot_thread.start()

# Then run Flask normally
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
