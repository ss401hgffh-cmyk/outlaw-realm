import telebot
import os
import sqlite3
import psycopg2
import time
import threading
from urllib.parse import urlparse
import random

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        url = urlparse(DATABASE_URL)
        return psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
    else:
        return sqlite3.connect('outlaw_realm.db')

TOKEN = "8882186957:AAGKs9WyX9lQWU1GMHjflHc11EF3xzuUeGc"
bot = telebot.TeleBot(TOKEN)

OWNER_IDS = [6047382490, 6652618822]
LOG_GROUP_ID = -1004297857148

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS bot_admins (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, gold INTEGER DEFAULT 0, silver INTEGER DEFAULT 0, bronze INTEGER DEFAULT 0, kingdom_id INTEGER, bounty_points INTEGER DEFAULT 0, army_power INTEGER DEFAULT 0, title TEXT DEFAULT 'Member')")
cursor.execute("CREATE TABLE IF NOT EXISTS kingdoms (kingdom_id SERIAL PRIMARY KEY, name TEXT, owner_id INTEGER, treasury_gold INTEGER DEFAULT 0, treasury_silver INTEGER DEFAULT 0, treasury_bronze INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS territories (chat_id INTEGER PRIMARY KEY, kingdom_id INTEGER, territory_tier TEXT, territory_level INTEGER DEFAULT 1)")

try: cursor.execute("ALTER TABLE users ADD COLUMN army_power INTEGER DEFAULT 0")
except: pass
try: cursor.execute("ALTER TABLE users ADD COLUMN bounty_points INTEGER DEFAULT 0")
except: pass
try: cursor.execute("ALTER TABLE territories ADD COLUMN territory_level INTEGER DEFAULT 1")
except: pass
try: cursor.execute("ALTER TABLE users ADD COLUMN title TEXT DEFAULT 'Member'")
except: pass

for oid in OWNER_IDS:
    cursor.execute("INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (oid,))
conn.commit()
conn.close()

def is_admin(user_id):
    if user_id in OWNER_IDS:
        return True
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM bot_admins WHERE user_id = %s", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def auto_collect_job():
    while True:
        try:
            time.sleep(300)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET bronze = bronze + (level * 100)")
            cursor.execute("SELECT kingdom_id FROM kingdoms")
            for (kid,) in cursor.fetchall():
                cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (kid,))
                t_count = cursor.fetchone()[0]
                cursor.execute("UPDATE kingdoms SET treasury_bronze = treasury_bronze + %s, treasury_silver = treasury_silver + %s, treasury_gold = treasury_gold + %s WHERE kingdom_id = %s", (500 + (t_count * 1000), 5 + (t_count * 10), 1 + t_count, kid))
            conn.commit()
            conn.close()
        except Exception as e:
            print("Auto collect error:", e)

threading.Thread(target=auto_collect_job, daemon=True).start()

def get_or_create_user(user_id, username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, username, level, xp, gold, silver, bronze, kingdom_id, bounty_points, army_power, title) VALUES (%s, %s, 1, 0, 0, 0, 1000, NULL, 0, 0, 'Member')", (user_id, username))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
    else:
        cursor.execute("UPDATE users SET username = %s WHERE user_id = %s", (username, user_id))
        conn.commit()
    conn.close()
    return user

def esc(text):
    if not text:
        return ""
    return str(text).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/status', '/botstatus', '.status'])
def status_dashboard_cmd(message):
    if message.chat.id != LOG_GROUP_ID and not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Yeh status dashboard sirf designated Log Group ya Bot Admins ke liye restricted hai!")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    u_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM kingdoms")
    k_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM territories")
    t_cnt = cursor.fetchone()[0]
    conn.close()
    bot.reply_to(message, f"📊 **BOT STATUS** 📊\nUsers: `{u_cnt}`\nKingdoms: `{k_cnt}`\nTerritories: `{t_cnt}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/addadmin'])
def add_admin_cmd(message):
    if not is_admin(message.from_user.id) or not message.reply_to_message:
        bot.reply_to(message, "❌ Access Denied ya reply nahi kiya gaya!")
        return
    target_id = message.reply_to_message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (target_id,))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"👑 Success! User ko Bot Admin bana diya gaya hai.")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/convert'])
def convert_cmd(message):
    parts = message.text.split()
    if len(parts) < 4 or not parts[1].isdigit():
        bot.reply_to(message, "🔄 Usage: `/convert <amount> <from> <to>`", parse_mode="Markdown")
        return
    amt, from_c, to_c, uid = int(parts[1]), parts[2].lower(), parts[3].lower(), message.from_user.id
    u = get_or_create_user(uid, message.from_user.username or message.from_user.first_name)
    conn = get_db_connection()
    cursor = conn.cursor()
    if from_c == 'silver' and to_c == 'bronze':
        if (u[5] or 0) < amt:
            conn.close()
            bot.reply_to(message, "❌ Inefficient Silver!")
            return
        cursor.execute("UPDATE users SET silver = silver - %s, bronze = bronze + %s WHERE user_id = %s", (amt, amt * 100, uid))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Converted `{amt}` Silver to `{amt * 100}` Bronze!", parse_mode="Markdown")
    else:
        conn.close()
        bot.reply_to(message, "💡 Supported: `silver bronze`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/duel', '/fight'])
def duel_cmd(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚔️ Reply to a user to duel!")
        return
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    t_uid, t_uname = message.reply_to_message.from_user.id, message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name
    p1 = get_or_create_user(uid, uname)
    p2 = get_or_create_user(t_uid, t_uname)
    conn = get_db_connection()
    cursor = conn.cursor()
    if ((p1[9] or 0) + random.randint(10, 100)) >= ((p2[9] or 0) + random.randint(10, 100)):
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 200, xp = xp + 50 WHERE user_id = %s", (uid,))
        conn.commit()
        bot.reply_to(message, f"⚔️ @{uname} won the duel against @{t_uname}!")
    else:
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 200, xp = xp + 50 WHERE user_id = %s", (t_uid,))
        conn.commit()
        bot.reply_to(message, f"⚔️ @{t_uname} won the duel against @{uname}!")
    conn.close()

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/rank', '/myrank'])
def rank_cmd(message):
    target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    uid, uname = target_user.id, target_user.username or target_user.first_name
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, bounty_points, army_power, kingdom_id FROM users")
    users = cursor.fetchall()
    leaderboard_data = []
    for row in users:
        u_id, u_name, bounty_val, army_val, kid = row[0], row[1], row[2] or 0, row[3] or 0, row[4]
        if u_id in OWNER_IDS: continue
        t_count = 0
        if kid:
            cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (kid,))
            res = cursor.fetchone()
            if res: t_count = res[0]
        leaderboard_data.append({'uid': u_id, 'uname': u_name, 't_count': t_count, 'army': army_val, 'bounty': bounty_val})
    leaderboard_data.sort(key=lambda x: (x['t_count'], x['bounty'], x['army']), reverse=True)
    user_rank = next((i for i, p in enumerate(leaderboard_data, 1) if p['uid'] == uid), None)
    conn.close()
    if not user_rank:
        bot.reply_to(message, "❌ Not registered in rankings yet!")
        return
    bot.reply_to(message, f"🎖️ Rank: `#{user_rank}` for @{uname}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/army'])
def army_cmd(message):
    target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    u = get_or_create_user(target_user.id, target_user.username or target_user.first_name)
    bot.reply_to(message, f"🪖 Army Power: `{u[9] or 0:,}` PWR", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/top', '/leaderboard'])
def top_cmd(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, bounty_points, army_power, kingdom_id FROM users")
    users = cursor.fetchall()
    leaderboard_data = []
    for row in users:
        uid, uname, bounty_val, army_val, kid = row[0], row[1], row[2] or 0, row[3] or 0, row[4]
        if uid in OWNER_IDS: continue
        t_count = 0
        if kid:
            cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (kid,))
            res = cursor.fetchone()
            if res: t_count = res[0]
        leaderboard_data.append({'uname': uname, 't_count': t_count, 'army': army_val, 'bounty': bounty_val})
    leaderboard_data.sort(key=lambda x: (x['t_count'], x['bounty'], x['army']), reverse=True)
    msg = "🏆 TOP RANKINGS 🏆\n"
    for rank, p in enumerate(leaderboard_data[:5], 1):
        msg += f"{rank}. @{p['uname']} | States: {p['t_count']} | PWR: {p['army']:,}\n"
    conn.close()
    bot.reply_to(message, msg)
    @bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/territory', '/state'])
def territory_current_cmd(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "❌ Private chat me territory nahi hoti!")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kingdom_id, territory_tier, territory_level FROM territories WHERE chat_id = %s", (message.chat.id,))
    res = cursor.fetchone()
    if not res:
        conn.close()
        bot.reply_to(message, "🌐 Neutral Territory. Use `/claim` to capture!", parse_mode="Markdown")
        return
    kid, tier, t_lvl = res[0], res[1] or "Standard", res[2] or 1
    cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = %s", (kid,))
    k_data = cursor.fetchone()
    conn.close()
    bot.reply_to(message, f"🌐 Controlled by `{k_data[0] if k_data else 'Unknown'}` (Level {t_lvl})", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/war'])
def war_cmd(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "❌ War sirf groups me ho sakti hai!")
        return
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    attacker = get_or_create_user(uid, uname)
    if not attacker[7]:
        bot.reply_to(message, "❌ Kingdom hona zaroori hai!")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kingdom_id FROM territories WHERE chat_id = %s", (message.chat.id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        bot.reply_to(message, "💡 Unclaimed group! Use `/claim`.")
        return
    if existing[0] == attacker[7]:
        conn.close()
        bot.reply_to(message, "❌ Apne hi territory par war nahi kar sakte!")
        return
    cursor.execute("UPDATE territories SET kingdom_id = %s WHERE chat_id = %s", (attacker[7], message.chat.id))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"⚔️ War Won! Territory captured by @{uname}!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/claim', '/calim', '/clam', '/claimm'])
def claim_territory_cmd(message):
    if message.chat.type == 'private':
        bot.reply_to(message, "❌ Groups only!")
        return
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    u = get_or_create_user(uid, uname)
    if not u[7]:
        bot.reply_to(message, "❌ Pehle kingdom banao: `/kingdom create <Name>`", parse_mode="Markdown")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kingdom_id FROM territories WHERE chat_id = %s", (message.chat.id,))
    if cursor.fetchone():
        conn.close()
        bot.reply_to(message, "❌ Already claimed! Use `/war` to snatch.")
        return
    cursor.execute("INSERT INTO territories (chat_id, kingdom_id, territory_tier, territory_level) VALUES (%s, %s, 'Outpost', 1)", (message.chat.id, u[7]))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"🚩 Territory successfully captured by @{uname}!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/give', '/pay', '/transfer'])
def give_money_cmd(message):
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit() or not message.reply_to_message:
        bot.reply_to(message, "💰 Usage: Reply to user `/give <amount> <gold|silver|bronze>`", parse_mode="Markdown")
        return
    amount, curr_type = int(parts[1]), parts[2].lower()
    if curr_type not in ['gold', 'silver', 'bronze'] or amount <= 0:
        bot.reply_to(message, "❌ Invalid currency/amount!")
        return
    sender = get_or_create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    target = message.reply_to_message.from_user
    get_or_create_user(target.id, target.username or target.first_name)
    idx = {'gold': 4, 'silver': 5, 'bronze': 6}[curr_type]
    if (sender[idx] or 0) < amount:
        bot.reply_to(message, f"❌ Insufficient {curr_type}!")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {curr_type} = {curr_type} - %s WHERE user_id = %s", (amount, message.from_user.id))
    cursor.execute(f"UPDATE users SET {curr_type} = {curr_type} + %s WHERE user_id = %s", (amount, target.id))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"💸 Transferred `{amount:,}` {curr_type} successfully!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/hire', '/recruitment'])
def hire_main_router(message):
    parts = message.text.split()
    if len(parts) == 1:
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton("🌾 Farmer", callback_data="shop_farmer"),
            telebot.types.InlineKeyboardButton("⚒️ Blacksmith", callback_data="shop_blacksmith"),
            telebot.types.InlineKeyboardButton("⚔️ Knight", callback_data="shop_knight"),
            telebot.types.InlineKeyboardButton("👑 Royal", callback_data="shop_royal")
        )
        bot.reply_to(message, "🏰 **RECRUITMENT SHOP**", reply_markup=markup, parse_mode="Markdown")
        return
    if len(parts) < 3 or not parts[2].isdigit():
        bot.reply_to(message, "⚔️ Usage: `/hire <Unit> <Amount>`", parse_mode="Markdown")
        return
    unit_name, amount = parts[1].capitalize(), int(parts[2])
    u = get_or_create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    rates = {"Farmer": (10, 1), "Blacksmith": (30, 3), "Knight": (150, 20), "Royal": (800, 150)}
    if unit_name not in rates:
        bot.reply_to(message, "❌ Invalid unit!")
        return
    cost, pwr = rates[unit_name][0] * amount, rates[unit_name][1] * amount
    if (u[6] or 0) < cost:
        bot.reply_to(message, f"❌ Need `{cost:,}` Bronze!", parse_mode="Markdown")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET bronze = bronze - %s, army_power = army_power + %s WHERE user_id = %s", (cost, pwr, message.from_user.id))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"⚔️ Hired `{amount}x {unit_name}`! Gained `+{pwr}` PWR", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
def callback_shop_units(call):
    bot.answer_callback_query(call.id, f"Use command: /hire {call.data.replace('shop_', '').capitalize()} <amount>", show_alert=True)

@bot.message_handler(commands=['godmode'])
def godmode_cmd(message):
    uid = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM bot_admins WHERE user_id = %s", (uid,))
    if uid not in OWNER_IDS and not cursor.fetchone():
        conn.close()
        bot.reply_to(message, "❌ Access Denied!")
        return
    cursor.execute("UPDATE users SET gold = 999999999, silver = 999999999, bronze = 999999999, army_power = 999999 WHERE user_id = %s", (uid,))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO users (user_id, username, gold, silver, bronze, army_power, title) VALUES (%s, 'God', 999999999, 999999999, 999999999, 999999, 'King')", (uid,))
    conn.commit()
    conn.close()
    bot.reply_to(message, "👑 Godmode Activated!", parse_mode="Markdown")

@bot.message_handler(commands=['profile'])
def profile_cmd(message):
    u = get_or_create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    bot.reply_to(message, f"⚔️ **PROFILE**\nLevel: `{u[2]}`\nGold: `{u[4]:,}` | Silver: `{u[5]:,}` | Bronze: `{u[6]:,}`\nArmy: `{u[9]:,}` PWR", parse_mode="Markdown")

@bot.message_handler(commands=['help', 'guide'])
def help_cmd(message):
    bot.reply_to(message, "⚔️ Commands: `/profile`, `/kingdom`, `/claim`, `/war`, `/hire`, `/duel`, `/top`", parse_mode="Markdown")

@bot.message_handler(commands=['join'])
def join_kingdom_cmd(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Usage: `/join <Kingdom Name>`", parse_mode="Markdown")
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kingdom_id, name FROM kingdoms WHERE name ILIKE %s", (f"%{parts[1].strip()}%",))
    k = cursor.fetchone()
    if not k:
        conn.close()
        bot.reply_to(message, "❌ Kingdom not found!")
        return
    cursor.execute("UPDATE users SET kingdom_id = %s WHERE user_id = %s", (k[0], message.from_user.id))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ Joined **{k[1]}**!", parse_mode="Markdown")

@bot.message_handler(commands=['deposit'])
def deposit_cmd(message):
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "⚠️ Usage: `/deposit <amount> <gold|silver|bronze>`", parse_mode="Markdown")
        return
    amt, ctype = int(parts[1]), parts[2].lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kingdom_id, gold, silver, bronze FROM users WHERE user_id = %s", (message.from_user.id,))
    u = cursor.fetchone()
    if not u or not u[0]:
        conn.close()
        bot.reply_to(message, "❌ Not in a kingdom!")
        return
    bal = u[4] if ctype == 'gold' else (u[5] if ctype == 'silver' else u[6])
    if bal < amt:
        conn.close()
        bot.reply_to(message, f"❌ Insufficient {ctype}!")
        return
    cursor.execute(f"UPDATE users SET {ctype} = {ctype} - %s WHERE user_id = %s", (amt, message.from_user.id))
    cursor.execute(f"UPDATE kingdoms SET treasury_{ctype} = treasury_{ctype} + %s WHERE kingdom_id = %s", (amt, u[0]))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ Deposited `{amt:,}` {ctype} to treasury!", parse_mode="Markdown")

@bot.message_handler(commands=['kingdom'])
def kingdom_handler(message):
    parts = message.text.split(maxsplit=2)
    uid = message.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()
    if len(parts) >= 3 and parts[1].lower() == 'create':
        cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
        if cursor.fetchone() and cursor.fetchone()[0]:
            conn.close()
            bot.reply_to(message, "❌ Already in a kingdom!")
            return
        cursor.execute("INSERT INTO kingdoms (name, owner_id) VALUES (%s, %s) RETURNING kingdom_id", (parts[2].strip(), uid))
        kid = cursor.fetchone()[0]
        cursor.execute("UPDATE users SET kingdom_id = %s, title = 'King' WHERE user_id = %s", (kid, uid))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"🏰 Kingdom **{parts[2].strip()}** created!", parse_mode="Markdown")
        return
    cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
    res = cursor.fetchone()
    if not res or not res[0]:
        conn.close()
        bot.reply_to(message, "⚠️ Not in a kingdom! Use `/kingdom create <Name>` or `/join <Name>`", parse_mode="Markdown")
        return
    cursor.execute("SELECT name, treasury_gold, treasury_silver, treasury_bronze FROM kingdoms WHERE kingdom_id = %s", (res[0],))
    k = cursor.fetchone()
    conn.close()
    bot.reply_to(message, f"🏰 Kingdom: `{k[0]}`\nTreasury: 🟡 {k[1]:,} | 🥈 {k[2]:,} | 🥉 {k[3]:,}", parse_mode="Markdown")

@bot.message_handler(commands=['leave'])
def leave_kingdom_cmd(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET kingdom_id = NULL, title = 'Member' WHERE user_id = %s", (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.reply_to(message, "✅ You left your kingdom.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/start'])
def start_cmd(message):
    u = get_or_create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    bot.reply_to(message, f"⚔️ WELCOME TO OUTLAW REALM ⚔️\nLevel: {u[2]} | Bronze: {u[6]:,}\nUse `/help` for commands.")

bot.infinity_polling()
        
                   
