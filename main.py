import telebot
import os
import sqlite3
import psycopg2
import time
import threading
from urllib.parse import urlparse
import random

# Heroku Postgres URL check karega, agar nahi mila toh local SQLite file use karega
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        # Heroku Postgres connection
        url = urlparse(DATABASE_URL)
        return psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port
        )
    else:
        # Local SQLite connection (jab tum apne computer par test karo)
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

    msg = (
        "📊 **BOT STATUS DASHBOARD** 📊\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Status: Online 🟢\n"
        f"Total Registered Users: `{u_cnt}`\n"
        f"Total Kingdoms: `{k_cnt}`\n"
        f"Total Connected Territories: `{t_cnt}`"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/addadmin'])
def add_admin_cmd(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ ACCESS DENIED! Sirf Bot Admins hi naye admin add kar sakte hain.")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "👑 **Usage:** Kisi user ke message par reply karke `/addadmin` chalaein.")
        return

    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bot_admins (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING", (target_id,))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"👑 Success! User @{target_name} (`{target_id}`) ko Bot Admin bana diya gaya hai.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/convert'])
def convert_cmd(message):
    parts = message.text.split()
    if len(parts) < 4 or not parts[1].isdigit():
        bot.reply_to(message, "🔄 **Usage:** `/convert <amount> <from_curr> <to_curr>`\nExample: `/convert 15 silver bronze`", parse_mode="Markdown")
        return

    amt = int(parts[1])
    from_c = parts[2].lower()
    to_c = parts[3].lower()
    uid = message.from_user.id
    u = get_or_create_user(uid, message.from_user.username or message.from_user.first_name)

    if amt <= 0:
        bot.reply_to(message, "❌ Amount positive hona chahiye!")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    if from_c == 'silver' and to_c == 'bronze':
        if (u[5] or 0) < amt:
            conn.close()
            bot.reply_to(message, f"❌ Aapke paas `{amt}` Silver nahi hai!")
            return
        gained = amt * 100
        cursor.execute("UPDATE users SET silver = silver - %s, bronze = bronze + %s WHERE user_id = %s", (amt, gained, uid))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ `{amt}` Silver convert ho kar `{gained:,}` Bronze ban gaya!", parse_mode="Markdown")
    elif from_c == 'gold' and to_c == 'silver':
        if (u[4] or 0) < amt:
            conn.close()
            bot.reply_to(message, f"❌ Aapke paas `{amt}` Gold nahi hai!")
            return
        gained = amt * 100
        cursor.execute("UPDATE users SET gold = gold - %s, silver = silver + %s WHERE user_id = %s", (amt, gained, uid))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ `{amt}` Gold convert ho kar `{gained:,}` Silver ban gaya!", parse_mode="Markdown")
    else:
        conn.close()
        bot.reply_to(message, "💡 Supported conversions: `silver bronze` | `gold silver`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/duel', '/fight'])
def duel_cmd(message):
    if not message.reply_to_message:
        bot.reply_to(message, "⚔️ **Usage:** Kisi player ke message par reply karke `/duel` chalaein!", parse_mode="Markdown")
        return

    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    target_user = message.reply_to_message.from_user
    t_uid, t_uname = target_user.id, target_user.username or target_user.first_name

    if uid == t_uid:
        bot.reply_to(message, "❌ Apne aap se duel nahi kar sakte!")
        return

    p1 = get_or_create_user(uid, uname)
    p2 = get_or_create_user(t_uid, t_uname)

    p1_pwr = (p1[9] or 0) + random.randint(10, 100)
    p2_pwr = (p2[9] or 0) + random.randint(10, 100)

    conn = get_db_connection()
    cursor = conn.cursor()

    if p1_pwr >= p2_pwr:
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 200, xp = xp + 50 WHERE user_id = %s", (uid,))
        conn.commit()
        msg = f"⚔️ **DUEL VICTORY!** ⚔️\n\n🏆 @{uname} ne @{t_uname} ko duel me hara diya!\n➕ Bounty: `+200` | ➕ XP: `+50`"
    else:
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 200, xp = xp + 50 WHERE user_id = %s", (t_uid,))
        conn.commit()
        msg = f"⚔️ **DUEL DEFEAT!** ⚔️\n\n🏆 @{t_uname} ne @{uname} ki attack ko counter karke hara diya!\n➕ Bounty: `+200` | ➕ XP: `+50`"

    conn.close()
    bot.reply_to(message, msg, parse_mode="Markdown")

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
        u_id, u_name = row[0], row[1]
        bounty_val = row[2] if row[2] is not None else 0
        army_val = row[3] if row[3] is not None else 0
        kid = row[4]

        if u_id in OWNER_IDS:
            continue

        k_name = "Independent Clan"
        t_count = 0
        if kid:
            cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = %s", (kid,))
            k_res = cursor.fetchone()
            if k_res: k_name = k_res[0]

            cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (kid,))
            res = cursor.fetchone()
            if res: t_count = res[0]

        leaderboard_data.append({
            'uid': u_id, 'uname': u_name, 'k_name': k_name,
            't_count': t_count, 'army': army_val, 'bounty': bounty_val
        })

    leaderboard_data.sort(key=lambda x: (x['t_count'], x['bounty'], x['army']), reverse=True)

    user_rank = None
    user_stats = None
    for index, p in enumerate(leaderboard_data, 1):
        if p['uid'] == uid:
            user_rank = index
            user_stats = p
            break

    conn.close()

    if not user_stats:
        bot.reply_to(message, f"❌ @{uname} abhi rankings database me register nahi hain!")
        return

    msg = (
        f"🎖️ **OUTLAW REALM RANKING INTEL** 🎖️\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **User:** @{uname}\n"
        f"🏅 **Global Rank Position:** `#{user_rank}` (Out of {len(leaderboard_data)} Players)\n"
        f"🏰 **Kingdom:** `{user_stats['k_name']}`\n"
        f"🌐 **Controlled States:** `{user_stats['t_count']}`\n"
        f"⚔️ **Army Power:** `{user_stats['army']:,}` PWR\n"
        f"☠️ **Bounty Points:** `{user_stats['bounty']:,}`"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/army'])
def army_cmd(message):
    target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    uid, uname = target_user.id, target_user.username or target_user.first_name
    u = get_or_create_user(uid, uname)
    army_val = u[9] if (len(u) > 9 and u[9] is not None) else 0
    bot.reply_to(message, f"🪖 **OUTLAW MILITARY FORCE** 🪖\n\nUser: @{uname}\nTotal Army Power: `{army_val:,}` PWR", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/top', '/leaderboard'])
def top_cmd(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, bounty_points, army_power, kingdom_id FROM users")
    users = cursor.fetchall()

    leaderboard_data = []
    for row in users:
        uid, uname = row[0], row[1]
        bounty_val = row[2] if row[2] is not None else 0
        army_val = row[3] if row[3] is not None else 0
        kid = row[4]

        if uid in OWNER_IDS:
            continue

        k_name = "Independent Clan"
        t_count = 0
        if kid:
            cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = %s", (kid,))
            k_res = cursor.fetchone()
            if k_res: k_name = k_res[0]

            cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (kid,))
            res = cursor.fetchone()
            if res: t_count = res[0]

        leaderboard_data.append({
            'uid': uid, 'uname': uname, 'k_name': k_name,
            't_count': t_count, 'army': army_val, 'bounty': bounty_val
        })
    leaderboard_data.sort(key=lambda x: (x['t_count'], x['bounty'], x['army']), reverse=True)

    msg = "🏆 OUTLAW REALM TOP RANKINGS 🏆\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for rank, p in enumerate(leaderboard_data[:10], 1):
        name_str = f"@{p['uname']}" if p['uname'] else f"User_{p['uid']}"
        b_val = f"{p['bounty']:,}"
        a_val = f"{p['army']:,}"
        msg += f"{rank}. {name_str}\n🏰 Kingdom: {p['k_name']}\n🌐 States: {p['t_count']} | ⚔️ PWR: {a_val}\n☠️ Bounty: 🥉 {b_val}\n━━━━━━━━━━━━━━━━━━━━━\n"

    conn.close()
    bot.reply_to(message, msg)@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/territory', '/state'])
def territory_current_cmd(message):
    if message.chat.type in ['private']:
        bot.reply_to(message, "❌ Private chat me koi territory nahi hoti!")
        return

    chat_id = message.chat.id
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT kingdom_id, territory_tier, territory_level FROM territories WHERE chat_id = %s", (chat_id,))
    res = cursor.fetchone()

    if not res:
        conn.close()
        bot.reply_to(message, "🌐 **GROUP TERRITORY INTEL** 🌐\n━━━━━━━━━━━━━━━━━━━━━\n\nStatus: `Unclaimed Neutral Territory`\n\n💡 Capture karne ke liye `/claim` command run karein!", parse_mode="Markdown")
        return

    kid, tier, t_lvl = res[0], res[1] or "Standard Tier", res[2] or 1
    cursor.execute("SELECT name, owner_id FROM kingdoms WHERE kingdom_id = %s", (kid,))
    k_data = cursor.fetchone()
    k_name = k_data[0] if k_data else "Unknown Empire"
    boss_id = k_data[1] if k_data else None

    cursor.execute("SELECT username FROM users WHERE user_id = %s", (boss_id,))
    b_res = cursor.fetchone()
    boss_name = f"@{b_res[0]}" if b_res and b_res[0] else f"ID: {boss_id}"

    conn.close()

    msg = (
        f"🌐 **CURRENT GROUP TERRITORY INTEL** 🌐\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏰 **Controlled By:** `{k_name}`\n"
        f"👑 **Kingdom Boss:** {boss_name}\n"
        f"🎖️ **Territory Level:** `Level {t_lvl}`\n"
        f"🛡️ **Territory Tier:** `{tier}`\n\n"
        f"⚠️ Dushman Kingdom /war se isko snatch kar sakte hain!"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/territories', '/allterritories', '/states'])
def all_territories_cmd(message):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT k.name, COUNT(t.chat_id) FROM kingdoms k LEFT JOIN territories t ON k.kingdom_id = t.kingdom_id GROUP BY k.kingdom_id, k.name")
    rows = cursor.fetchall()
    conn.close()

    msg = "🌐 **REALM CONTROLLED TERRITORIES** 🌐\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    if not rows:
        msg += "Koi territories abhi controlled nahi hain!"
    else:
        for r in rows:
            msg += f"🏰 Kingdom: `{r[0]}`\n🌐 Controlled States: `{r[1]}`\n─────────────────────\n"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/war'])
def war_cmd(message):
    if message.chat.type in ['private']:
        bot.reply_to(message, "❌ War sirf groups me ho sakti hai!")
        return

    chat_id = message.chat.id
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    attacker = get_or_create_user(uid, uname)
    att_kid = attacker[7]

    if not att_kid:
        bot.reply_to(message, "❌ War chhedne ke liye Kingdom hona zaroori hai!")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT kingdom_id FROM territories WHERE chat_id = %s", (chat_id,))
    existing = cursor.fetchone()

    if not existing:
        conn.close()
        bot.reply_to(message, "💡 Yeh group unclaimed hai! Direct `/claim` se capture kar lo.")
        return

    def_kid = existing[0]

    if def_kid == att_kid:
        conn.close()
        bot.reply_to(message, "❌ Apne hi Kingdom ke territory par war nahi chhed sakte!")
        return

    cursor.execute("SELECT owner_id FROM kingdoms WHERE kingdom_id = %s", (def_kid,))
    def_boss_id = cursor.fetchone()[0]

    cursor.execute("SELECT user_id, army_power FROM users WHERE user_id = %s", (def_boss_id,))
    defender_data = cursor.fetchone()
    def_pwr = defender_data[1] if defender_data else 0
    att_pwr = attacker[9] or 0

    if att_pwr > def_pwr:
        cursor.execute("UPDATE territories SET kingdom_id = %s WHERE chat_id = %s", (att_kid, chat_id))
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 500, xp = xp + 150 WHERE user_id = %s", (uid,))
        conn.commit()
        msg = (
            f"⚔️ **WAR DECLARED & INSTANT VICTORY!** ⚔️\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🥊 **Attacker PWR:** `{att_pwr:,}`\n"
            f"🛡️ **Defender Boss PWR:** `{def_pwr:,}`\n\n"
            f"🏆 **RESULT:** @{uname} ne enemy ko crush karke territory snatch kar li!\n"
            f"➕ **Bounty Points:** `+500` | ➕ **XP:** `+150`"
        )
    else:
        cursor.execute("UPDATE users SET army_power = GREATEST(0, army_power - 100) WHERE user_id = %s", (uid,))
        conn.commit()
        msg = (
            f"⚔️ **WAR DECLARED & DEFEAT!** ⚔️\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🥊 **Attacker PWR:** `{att_pwr:,}`\n"
            f"🛡️ **Defender Boss PWR:** `{def_pwr:,}`\n\n"
            f"💀 **RESULT:** Defender ka PWR zyaada tha. Attacker war haar gaya!"
        )

    conn.close()
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/claim', '/calim', '/clam', '/claimm'])
def claim_territory_cmd(message):
    if message.chat.type in ['private']:
        bot.reply_to(message, "❌ Territory capture sirf Groups me hi ho sakta hai!")
        return

    chat_id = message.chat.id
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    u = get_or_create_user(uid, uname)
    user_kid = u[7]

    if not user_kid:
        bot.reply_to(message, "❌ Pehle kingdom banao ya join karo: `/kingdom create <Name>`", parse_mode="Markdown")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT kingdom_id, territory_tier, territory_level FROM territories WHERE chat_id = %s", (chat_id,))
    existing = cursor.fetchone()

    if existing:
        owner_kid, tier, t_lvl = existing[0], existing[1] or "Standard Tier", existing[2] or 1
        cursor.execute("SELECT name, owner_id FROM kingdoms WHERE kingdom_id = %s", (owner_kid,))
        k_data = cursor.fetchone()
        k_name = k_data[0] if k_data else "Unknown"
        boss_id = k_data[1] if k_data else None

        cursor.execute("SELECT username FROM users WHERE user_id = %s", (boss_id,))
        b_res = cursor.fetchone()
        boss_name = f"@{b_res[0]}" if b_res and b_res[0] else f"ID: {boss_id}"

        if owner_kid == user_kid:
            msg = (
                f"🏰 **TERRITORY ALREADY CONTROLLED** 🏰\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"• **Kingdom:** `{k_name}`\n"
                f"• **Kingdom Boss:** {boss_name}\n"
                f"• **Territory Level:** `Level {t_lvl}`\n"
                f"• **Territory Tier:** `{tier}`\n\n"
                f"✅ Yeh territory aapke hi kingdom ke control me hai!"
            )
        else:
            msg = (
                f"🛡️ **OCCUPIED ENEMY TERRITORY** 🛡️\n━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"• **Controlled By:** `{k_name}`\n"
                f"• **Kingdom Boss:** {boss_name}\n"
                f"• **Territory Level:** `Level {t_lvl}`\n"
                f"• **Territory Tier:** `{tier}`\n\n"
                f"⚠️ Is territory par kabza karne ke liye `/war` chalaein!"
            )
        conn.close()
        bot.reply_to(message, msg, parse_mode="Markdown")
        return

    possible_tiers = [("Outpost", 1), ("Borderland Fortress", 2), ("Frontier State", 3), ("Imperial Capital", 5)]
    assigned_tier, assigned_lvl = random.choice(possible_tiers)

    cursor.execute("INSERT INTO territories (chat_id, kingdom_id, territory_tier, territory_level) VALUES (%s, %s, %s, %s)", (chat_id, user_kid, assigned_tier, assigned_lvl))
    cursor.execute("UPDATE users SET bounty_points = bounty_points + 500, xp = xp + 100 WHERE user_id = %s", (uid,))
    cursor.execute("UPDATE kingdoms SET treasury_bronze = treasury_bronze + 1000, treasury_silver = treasury_silver + 10 WHERE kingdom_id = %s", (user_kid,))
    conn.commit()

    cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = %s", (user_kid,))
    my_k_data = cursor.fetchone()
    my_k_name = my_k_data[0] if my_k_data else "Your Kingdom"

    cursor.execute("SELECT bounty_points, xp FROM users WHERE user_id = %s", (uid,))
    new_stats = cursor.fetchone()
    conn.close()

    bot.reply_to(
        message, 
        f"🚩 **TERRITORY CAPTURED SUCCESSFULLY!** 🚩\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏰 **Kingdom:** `{my_k_name}`\n"
        f"👑 **Kingdom Boss:** @{uname}\n"
        f"🎖️ **Territory Level:** `Level {assigned_lvl}`\n"
        f"🛡️ **Territory Tier:** `{assigned_tier}`\n\n"
        f"➕ **Bounty Points:** `+500` (Total: `{new_stats[0]:,}`)\n"
        f"➕ **XP:** `+100` (Total: `{new_stats[1]:,}`)\n"
        f"🏛️ Kingdom Treasury Boosted!", 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/give', '/pay', '/transfer'])
def give_money_cmd(message):
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "💰 **Usage:** Reply to user: `/give <amount> <gold|silver|bronze>`", parse_mode="Markdown")
        return

    amount = int(parts[1])
    curr_type = parts[2].lower()

    if curr_type not in ['gold', 'silver', 'bronze'] or amount <= 0 or not message.reply_to_message:
        bot.reply_to(message, "❌ Invalid Command/Reply!")
        return

    sender = get_or_create_user(message.from_user.id, message.from_user.username or message.from_user.first_name)
    target_user = message.reply_to_message.from_user
    receiver = get_or_create_user(target_user.id, target_user.username or target_user.first_name)

    curr_idx = {'gold': 4, 'silver': 5, 'bronze': 6}[curr_type]
    sender_bal = sender[curr_idx] or 0

    if sender_bal < amount:
        bot.reply_to(message, f"❌ Inefficient Balance! Required: `{amount:,}` {curr_type.capitalize()}")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {curr_type} = {curr_type} - %s WHERE user_id = %s", (amount, message.from_user.id))
    cursor.execute(f"UPDATE users SET {curr_type} = {curr_type} + %s WHERE user_id = %s", (amount, target_user.id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"💸 Transfer `{amount:,}` {curr_type.capitalize()} to @{target_user.username or target_user.first_name} Success!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/hire', '/recruitment'])
def hire_main_router(message):
    parts = message.text.split()
    if len(parts) == 1:
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            telebot.types.InlineKeyboardButton("🌾 Farmer", callback_data="shop_farmer"),
            telebot.types.InlineKeyboardButton("⚒️ Blacksmith", callback_data="shop_blacksmith")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("🏪 Shopkeeper", callback_data="shop_shopkeeper"),
            telebot.types.InlineKeyboardButton("⚔️ Knight", callback_data="shop_knight")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("🎩 Noble", callback_data="shop_noble"),
            telebot.types.InlineKeyboardButton("👑 Royal", callback_data="shop_royal")
        )
        markup.add(
            telebot.types.InlineKeyboardButton("⚙️ Machinery", callback_data="shop_machinery")
        )
        bot.reply_to(message, "🏰 **RECRUITMENT SHOP** 🏰\n👇 Click unit for intel & hiring commands:", reply_markup=markup, parse_mode="Markdown")
        return

    if len(parts) < 3 or not parts[2].isdigit():
        bot.reply_to(message, "⚔️ Usage: `/hire <Unit_Name> <Amount>`", parse_mode="Markdown")
        return

    unit_name = parts[1].capitalize()
    amount = int(parts[2])
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    u = get_or_create_user(uid, uname)

    rates = {"Farmer": 10, "Blacksmith": 30, "Shopkeeper": 60, "Knight": 150, "Noble": 350, "Royal": 800, "Machinery": 2000}
    power_gain = {"Farmer": 1, "Blacksmith": 3, "Shopkeeper": 7, "Knight": 20, "Noble": 50, "Royal": 150, "Machinery": 500}

    if unit_name not in rates:
        bot.reply_to(message, "❌ Invalid Unit!")
        return

    total_cost = rates[unit_name] * amount
    total_pwr = power_gain[unit_name] * amount
    user_bronze = u[6] or 0

    if user_bronze < total_cost:
        bot.reply_to(message, f"❌ Insufficient Bronze! Need `{total_cost:,}`", parse_mode="Markdown")
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET bronze = bronze - %s, army_power = army_power + %s WHERE user_id = %s", (total_cost, total_pwr, uid))
    conn.commit()

    cursor.execute("SELECT army_power, bronze FROM users WHERE user_id = %s", (uid,))
    updated = cursor.fetchone()
    conn.close()

    bot.reply_to(message, f"⚔️ Hired `{amount:,}x {unit_name}`!\nGained: `+{total_pwr:,}` PWR\nTotal PWR: `{updated[0]:,}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
def callback_shop_units(call):
    unit = call.data.replace("shop_", "").capitalize()
    costs = {"Farmer": "10 Bronze = +1 PWR", "Blacksmith": "30 Bronze = +3 PWR", "Shopkeeper": "60 Bronze = +7 PWR", "Knight": "150 Bronze = +20 PWR", "Noble": "350 Bronze = +50 PWR", "Royal": "800 Bronze = +150 PWR", "Machinery": "2,000 Bronze = +500 PWR"}
    info = costs.get(unit, "10 Bronze = +1 PWR")
    bot.answer_callback_query(call.id, f"{unit} Info: {info}\nUse command: /hire {unit} <amount>", show_alert=True)

@bot.message_handler(commands=['godmode'])
def godmode_cmd(message):
    try:
        uid = message.from_user.id
        uname = message.from_user.username or message.from_user.first_name or "God"
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM bot_admins WHERE user_id = %s", (uid,))
        is_adm = cursor.fetchone()
        if uid not in OWNER_IDS and not is_adm:
            conn.close()
            bot.reply_to(message, "❌ **Access Denied:** Yeh sirf Owner ke liye hai.", parse_mode="Markdown")
            return
        cursor.execute("UPDATE users SET gold = 999999999, silver = 999999999, bronze = 999999999, army_power = 999999, level = 999, xp = 99999 WHERE user_id = %s", (uid,))
        if cursor.rowcount == 0:
            cursor.execute("INSERT INTO users (user_id, username, level, xp, gold, silver, bronze, army_power, title) VALUES (%s, %s, 999, 99999, 999999999, 999999999, 999999999, 999999, 'King')", (uid, uname))
        conn.commit()
        conn.close()
        bot.reply_to(message, "👑 **GODMODE ACTIVATED!** Wealth aur power unlimited ho chuki hai.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")
        @bot.message_handler(commands=['profile'])
def profile_cmd(message):
    try:
        target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
        uid, uname = target_user.id, target_user.username or target_user.first_name or "Outlaw"
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT level, xp, gold, silver, bronze, kingdom_id, bounty_points, army_power, title FROM users WHERE user_id = %s", (uid,))
        u_res = cursor.fetchone()
        if not u_res:
            cursor.execute("INSERT INTO users (user_id, username, bronze) VALUES (%s, %s, 1000)", (uid, uname))
            conn.commit()
            level, xp, gold, silver, bronze, k_id, bounty, army, title = 1, 0, 0, 0, 1000, None, 0, 0, 'Member'
        else:
            level, xp, gold, silver, bronze, k_id, bounty, army, title = u_res
            title = title or 'Member'
        k_name = "None"
        t_count = 0
        t_gold, t_silver, t_bronze = 0, 0, 0
        if k_id:
            cursor.execute("SELECT name, treasury_gold, treasury_silver, treasury_bronze FROM kingdoms WHERE kingdom_id = %s", (k_id,))
            k_data = cursor.fetchone()
            if k_data:
                k_name, t_gold, t_silver, t_bronze = k_data
                cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (k_id,))
                t_count = cursor.fetchone()[0]
        conn.close()
        msg = (
            f"⚔️ ── **O U T L A W   P R O F I L E** ── ⚔️\n"
            f"👤 **Outlaw:** @{esc(uname)}\n"
            f"🛡️ **Rank / Title:** `{esc(title)}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⭐ **Level:** `{level}` (XP: `{xp}`)\n"
            f"💰 **Personal Wealth:**\n"
            f"   • 🟡 Gold: `{gold:,}`\n"
            f"   • 🥈 Silver: `{silver:,}`\n"
            f"   • 🥉 Bronze: `{bronze:,}`\n"
            f"⚔️ **Army Power:** `{army:,}` Troops\n"
            f"🏆 **Bounty Points:** `{bounty:,}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏰 **Kingdom Status:**\n"
            f"   • 🏷️ Name: `{esc(k_name)}`\n"
            f"   • 🏴 Territories: `{t_count}`\n"
            f"   • 🏛️ Treasury: 🟡 `{t_gold:,}` | 🥈 `{t_silver:,}` | 🥉 `{t_bronze:,}`"
        )
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=['help', 'guide'])
def help_cmd(message):
    bot.reply_to(message, 
        "⚔️ **OUTLAW REALM - COMMAND DIRECTORY** ⚔️\n\n"
        "• `/start` - Start your outlaw journey\n"
        "• `/profile` - View your status & wealth\n"
        "• `/kingdom create <Name>` - Found your kingdom\n"
        "• `/join <Kingdom Name>` - Join a realm\n"
        "• `/kingdom` - Open Imperial Kingdom Dashboard\n"
        "• `/deposit <amount> gold/silver/bronze` - Add to Treasury\n"
        "• `/leave` - Abandon current kingdom (with warning)\n"
        "• `/promote <user_id> <Title>` - Grant noble rank (King Only)\n"
        "• `/transfer <user_id>` - Transfer crown (King Only)\n"
        "• `/duke`, `/marcus`, `/viscount`, `/baron` - Direct rank shortcuts", 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['join'])
def join_kingdom_cmd(message):
    try:
        uid = message.from_user.id
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Sahi tarika: `/join <Kingdom Name>`", parse_mode="Markdown")
            return
        kingdom_name = parts[1].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
        user_res = cursor.fetchone()
        if user_res and user_res[0]:
            conn.close()
            bot.reply_to(message, "❌ Aap pehle se hi ek Kingdom ke member hain!", parse_mode="Markdown")
            return
        cursor.execute("SELECT kingdom_id, name FROM kingdoms WHERE name ILIKE %s", (f"%{kingdom_name}%",))
        k_res = cursor.fetchone()
        if not k_res:
            conn.close()
            bot.reply_to(message, f"❌ '{esc(kingdom_name)}' naam ka Kingdom nahi mila!", parse_mode="Markdown")
            return
        k_id, k_actual_name = k_res
        cursor.execute("UPDATE users SET kingdom_id = %s, title = 'Member' WHERE user_id = %s", (k_id, uid))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ **SUCCESS:** Aapne **{esc(k_actual_name)}** join kar liya hai!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=['deposit'])
def deposit_cmd(message):
    try:
        uid = message.from_user.id
        parts = message.text.split()
        if len(parts) < 3 or not parts[1].isdigit():
            bot.reply_to(message, "⚠️ Sahi tarika: `/deposit <amount> gold/silver/bronze`", parse_mode="Markdown")
            return
        amt = int(parts[1])
        ctype = parts[2].lower()
        if amt <= 0 or ctype not in ['gold', 'silver', 'bronze']:
            bot.reply_to(message, "❌ Invalid amount ya currency!", parse_mode="Markdown")
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id, gold, silver, bronze FROM users WHERE user_id = %s", (uid,))
        u_res = cursor.fetchone()
        if not u_res or not u_res[0]:
            conn.close()
            bot.reply_to(message, "❌ Aap kisi Kingdom ke member nahi hain!", parse_mode="Markdown")
            return
        k_id, u_gold, u_silver, u_bronze = u_res
        curr_bal = u_gold if ctype == 'gold' else (u_silver if ctype == 'silver' else u_bronze)
        if curr_bal < amt:
            conn.close()
            bot.reply_to(message, f"❌ Aapke paas itna {ctype} nahi hai!", parse_mode="Markdown")
            return
        cursor.execute(f"UPDATE users SET {ctype} = {ctype} - %s WHERE user_id = %s", (amt, uid))
        cursor.execute(f"UPDATE kingdoms SET treasury_{ctype} = treasury_{ctype} + %s WHERE kingdom_id = %s", (amt, k_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ **DEPOSIT:** {amt:,} {ctype.capitalize()} khazane me jama ho gaya!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=['kingdom'])
def kingdom_handler(message):
    try:
        uid = message.from_user.id
        uname = message.from_user.username or message.from_user.first_name or "Outlord"
        parts = message.text.split(maxsplit=2)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id, title FROM users WHERE user_id = %s", (uid,))
        u_res = cursor.fetchone()
        if not u_res:
            cursor.execute("INSERT INTO users (user_id, username, bronze) VALUES (%s, %s, 1000)", (uid, uname))
            conn.commit()
            user_kingdom_id, user_title = None, "Member"
        else:
            user_kingdom_id, user_title = u_res[0], u_res[1] or "Member"
        if len(parts) >= 3 and parts[1].lower() == 'create':
            k_name = parts[2].strip()
            if user_kingdom_id:
                conn.close()
                bot.reply_to(message, "❌ Aap pehle se hi kisi Empire ke member hain!", parse_mode="Markdown")
                return
            cursor.execute("SELECT kingdom_id FROM kingdoms WHERE name ILIKE %s", (k_name,))
            if cursor.fetchone():
                conn.close()
                bot.reply_to(message, f"❌ '{esc(k_name)}' naam ka Kingdom pehle se mojood hai!", parse_mode="Markdown")
                return
            cursor.execute("INSERT INTO kingdoms (name, owner_id) VALUES (%s, %s) RETURNING kingdom_id", (k_name, uid))
            kid = cursor.fetchone()[0]
            cursor.execute("UPDATE users SET kingdom_id = %s, title = 'King' WHERE user_id = %s", (kid, uid))
            conn.commit()
            conn.close()
            bot.reply_to(message, f"🏰 **KINGDOM CREATED:** `{esc(k_name)}`", parse_mode="Markdown")
            return
        if not user_kingdom_id:
            conn.close()
            bot.reply_to(message, "⚠️ Aap kisi Kingdom ke member nahi hain!\n• `/kingdom create <Name>`\n• `/join <Name>`", parse_mode="Markdown")
            return
        k_id = user_kingdom_id
        cursor.execute("SELECT name, owner_id, treasury_gold, treasury_silver, treasury_bronze FROM kingdoms WHERE kingdom_id = %s", (k_id,))
        k_data = cursor.fetchone()
        if not k_data:
            conn.close()
            bot.reply_to(message, "❌ Kingdom ki details nahi mili!", parse_mode="Markdown")
            return
        k_name, owner_id, t_gold, t_silver, t_bronze = k_data
        cursor.execute("SELECT username FROM users WHERE user_id = %s", (owner_id,))
        owner_res = cursor.fetchone()
        owner_name = f"@{esc(owner_res[0])}" if owner_res and owner_res[0] else f"ID: {owner_id}"
        cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = %s", (k_id,))
        t_count = cursor.fetchone()[0]
        cursor.execute("SELECT user_id, username, title, army_power FROM users WHERE kingdom_id = %s", (k_id,))
        members = cursor.fetchall()
        conn.close()
        total_army = sum(m[3] or 0 for m in members)
        members_list = []
        for m in members:
            m_id, m_name, m_title, m_army = m
            d_name = f"@{esc(m_name)}" if m_name else f"ID: {m_id}"
            t_tag = m_title or "Member"
            badge = "👑" if t_tag == "King" else "⚜️" if t_tag == "Duke" else "⚔️" if t_tag in ["Marquess", "Marcus"] else "🗡️" if t_tag == "Viscount" else "🏰" if t_tag == "Baron" else "🛡️"
            members_list.append(f"  {badge} {d_name} ➔ **{t_tag}** (Army: `{m_army or 0}`)\n")
        msg = (
            f"⚔️ ── **IMPERIAL DOMAIN** ── ⚔️\n"
            f"🏰 **Name:** `{esc(k_name)}`\n"
            f"👑 **Ruler:** {owner_name}\n"
            f"⚔️ **Total Army:** `{total_army:,}` Troops\n"
            f"🏴 **Territories:** `{t_count}`\n\n"
            f"💰 **Treasury:**\n"
            f"  • 🟡 Gold: `{t_gold or 0:,}`\n"
            f"  • 🥈 Silver: `{t_silver or 0:,}`\n"
            f"  • 🥉 Bronze: `{t_bronze or 0:,}`\n\n"
            f"📜 **Noble Council:**\n" + "".join(members_list)
        )
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=['leave'])
def leave_kingdom_cmd(message):
    try:
        uid = message.from_user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
        user_res = cursor.fetchone()
        if not user_res or not user_res[0]:
            conn.close()
            bot.reply_to(message, "⚠️ Aap kisi Kingdom ke member nahi hain!")
            return
        k_id = user_res[0]
        cursor.execute("SELECT owner_id FROM kingdoms WHERE kingdom_id = %s", (k_id,))
        k_info = cursor.fetchone()
        if k_info and str(k_info[0]) == str(uid):
            conn.close()
            bot.reply_to(message, "❌ Aap King hain! Pehle crown transfer karein.")
            return
        conn.close()
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("✅ Haan, Chhodo", callback_data="confirm_leave"), telebot.types.InlineKeyboardButton("❌ Nahi", callback_data="cancel_leave"))
        bot.reply_to(message, "⚠️ Kya aap sach me Kingdom chhodna chahte hain?", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["confirm_leave", "cancel_leave"])
def leave_callback(call):
    try:
        uid = call.from_user.id
        if call.data == "cancel_leave":
            bot.answer_callback_query(call.id, "Cancelled!")
            bot.edit_message_text("❌ Radd kar diya gaya hai.", call.message.chat.id, call.message.message_id)
            return
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET kingdom_id = NULL, title = 'Member' WHERE user_id = %s", (uid,))
        conn.commit()
        conn.close()
        bot.answer_callback_query(call.id, "Left!")
        bot.edit_message_text("✅ Aapne Kingdom chhod diya hai.", call.message.chat.id, call.message.message_id)
    except Exception:
        pass

@bot.message_handler(commands=['transfer'])
def transfer_kingdom_cmd(message):
    try:
        uid = message.from_user.id
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Sahi tarika: `/transfer <user_id>`", parse_mode="Markdown")
            return
        target_id = int(parts[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
        u_res = cursor.fetchone()
        if not u_res or not u_res[0]:
            conn.close()
            bot.reply_to(message, "❌ Aap kisi Kingdom ke member nahi hain!")
            return
        k_id = u_res[0]
        cursor.execute("SELECT owner_id FROM kingdoms WHERE kingdom_id = %s", (k_id,))
        k_info = cursor.fetchone()
        if not k_info or str(k_info[0]) != str(uid):
            conn.close()
            bot.reply_to(message, "❌ Sirf King crown transfer kar sakta hai!")
            return
        cursor.execute("UPDATE kingdoms SET owner_id = %s WHERE kingdom_id = %s", (target_id, k_id))
        cursor.execute("UPDATE users SET title = 'Member' WHERE user_id = %s", (uid,))
        cursor.execute("UPDATE users SET title = 'King' WHERE user_id = %s", (target_id,))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"👑 Crown transfer ho gaya naye King ko (`{target_id}`)!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=['promote'])
def promote_cmd(message):
    try:
        uid = message.from_user.id
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(message, "⚠️ Sahi tarika: `/promote <user_id> <Title>`", parse_mode="Markdown")
            return
        target_id = int(parts[1])
        new_title = parts[2].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
        u_res = cursor.fetchone()
        if not u_res or not u_res[0]:
            conn.close()
            bot.reply_to(message, "❌ Aap kisi kingdom me nahi hain!")
            return
        k_id = u_res[0]
        cursor.execute("SELECT owner_id FROM kingdoms WHERE kingdom_id = %s", (k_id,))
        k_info = cursor.fetchone()
        if not k_info or str(k_info[0]) != str(uid):
            conn.close()
            bot.reply_to(message, "❌ Sirf King promote kar sakta hai!")
            return
        cursor.execute("UPDATE users SET title = %s WHERE user_id = %s AND kingdom_id = %s", (new_title, target_id, k_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ User `{target_id}` ko **{esc(new_title)}** bana diya gaya hai!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

def set_title_handler(message, title_name):
    try:
        uid = message.from_user.id
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, f"⚠️ Sahi tarika: `/{title_name.lower()} <user_id>`", parse_mode="Markdown")
            return
        target_id = int(parts[1])
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT kingdom_id FROM users WHERE user_id = %s", (uid,))
        u_res = cursor.fetchone()
        if not u_res or not u_res[0]:
            conn.close()
            bot.reply_to(message, "❌ Aap kisi kingdom me nahi hain!")
            return
        k_id = u_res[0]
        cursor.execute("SELECT owner_id FROM kingdoms WHERE kingdom_id = %s", (k_id,))
        k_info = cursor.fetchone()
        if not k_info or str(k_info[0]) != str(uid):
            conn.close()
            bot.reply_to(message, "❌ Sirf King title de sakta hai!")
            return
        cursor.execute("UPDATE users SET title = %s WHERE user_id = %s AND kingdom_id = %s", (title_name, target_id, k_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ User ID `{target_id}` ab **{title_name}** ban chuka hai!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: `{e}`", parse_mode="Markdown")

@bot.message_handler(commands=['duke'])
def duke_cmd(message):
    set_title_handler(message, 'Duke')

@bot.message_handler(commands=['viscount'])
def viscount_cmd(message):
    set_title_handler(message, 'Viscount')

@bot.message_handler(commands=['baron'])
def baron_cmd(message):
    set_title_handler(message, 'Baron')

@bot.message_handler(commands=['marcus'])
def marcus_cmd(message):
    set_title_handler(message, 'Marcus')

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/start'])
def start_cmd(message):
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    u = get_or_create_user(uid, uname)
    bot.reply_to(message, f"⚔️ WELCOME TO OUTLAW REALM ⚔️\n👤 Outlaw: @{uname}\n🎖️ Rank: Level {u[2]}\n🟡 Gold: {u[4]:,} | 🥈 Silver: {u[5]:,} | 🥉 Bronze: {u[6]:,}\n\n💡 Commands ke liye /help ya /story chalaein!")

bot.infinity_polling()
        
            
    
