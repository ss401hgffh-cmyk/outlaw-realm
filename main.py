import telebot, sqlite3, random, datetime, threading, time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8882186957:AAGKs9WyX9lQWU1GMHjflHc11EF3xzuUeGc"
bot = telebot.TeleBot(TOKEN)

OWNER_IDS = [6047382490, 6652618822]
LOG_GROUP_ID = -1004297857148

conn = sqlite3.connect('outlaw_realm.db')
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS bot_admins (user_id INTEGER PRIMARY KEY)")
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, gold INTEGER DEFAULT 0, silver INTEGER DEFAULT 0, bronze INTEGER DEFAULT 0, kingdom_id INTEGER, bounty_points INTEGER DEFAULT 0, army_power INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS kingdoms (kingdom_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, owner_id INTEGER, treasury_gold INTEGER DEFAULT 0, treasury_silver INTEGER DEFAULT 0, treasury_bronze INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS territories (chat_id INTEGER PRIMARY KEY, kingdom_id INTEGER, territory_tier TEXT, territory_level INTEGER DEFAULT 1)")

try: cursor.execute("ALTER TABLE users ADD COLUMN army_power INTEGER DEFAULT 0")
except: pass
try: cursor.execute("ALTER TABLE users ADD COLUMN bounty_points INTEGER DEFAULT 0")
except: pass
try: cursor.execute("ALTER TABLE territories ADD COLUMN territory_level INTEGER DEFAULT 1")
except: pass

for oid in OWNER_IDS:
    cursor.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (oid,))
conn.commit()
conn.close()

def is_admin(user_id):
    if user_id in OWNER_IDS:
        return True
    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM bot_admins WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def auto_collect_job():
    while True:
        try:
            time.sleep(300)
            conn = sqlite3.connect('outlaw_realm.db')
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET bronze = bronze + (level * 100)")
            cursor.execute("SELECT kingdom_id FROM kingdoms")
            for (kid,) in cursor.fetchall():
                cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = ?", (kid,))
                t_count = cursor.fetchone()[0]
                cursor.execute("UPDATE kingdoms SET treasury_bronze = treasury_bronze + ?, treasury_silver = treasury_silver + ?, treasury_gold = treasury_gold + ? WHERE kingdom_id = ?", (500 + (t_count * 1000), 5 + (t_count * 10), 1 + t_count, kid))
            conn.commit()
            conn.close()
        except Exception as e:
            print("Auto collect error:", e)

threading.Thread(target=auto_collect_job, daemon=True).start()

def get_or_create_user(user_id, username):
    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, username, level, xp, gold, silver, bronze, kingdom_id, bounty_points, army_power) VALUES (?, ?, 1, 0, 0, 0, 1000, NULL, 0, 0)", (user_id, username))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
    else:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()
    conn.close()
    return user

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/status', '/botstatus', '.status'])
def status_dashboard_cmd(message):
    if message.chat.id != LOG_GROUP_ID and not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Yeh status dashboard sirf designated Log Group ya Bot Admins ke liye restricted hai!")
        return

    conn = sqlite3.connect('outlaw_realm.db')
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (target_id,))
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()

    if from_c == 'silver' and to_c == 'bronze':
        if (u[5] or 0) < amt:
            conn.close()
            bot.reply_to(message, f"❌ Aapke paas `{amt}` Silver nahi hai!")
            return
        gained = amt * 100
        cursor.execute("UPDATE users SET silver = silver - ?, bronze = bronze + ? WHERE user_id = ?", (amt, gained, uid))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ `{amt}` Silver convert ho kar `{gained:,}` Bronze ban gaya!", parse_mode="Markdown")
    elif from_c == 'gold' and to_c == 'silver':
        if (u[4] or 0) < amt:
            conn.close()
            bot.reply_to(message, f"❌ Aapke paas `{amt}` Gold nahi hai!")
            return
        gained = amt * 100
        cursor.execute("UPDATE users SET gold = gold - ?, silver = silver + ? WHERE user_id = ?", (amt, gained, uid))
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()

    if p1_pwr >= p2_pwr:
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 200, xp = xp + 50 WHERE user_id = ?", (uid,))
        conn.commit()
        msg = f"⚔️ **DUEL VICTORY!** ⚔️\n\n🏆 @{uname} ne @{t_uname} ko duel me hara diya!\n➕ Bounty: `+200` | ➕ XP: `+50`"
    else:
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 200, xp = xp + 50 WHERE user_id = ?", (t_uid,))
        conn.commit()
        msg = f"⚔️ **DUEL DEFEAT!** ⚔️\n\n🏆 @{t_uname} ne @{uname} ki attack ko counter karke hara diya!\n➕ Bounty: `+200` | ➕ XP: `+50`"

    conn.close()
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/kingdom'])
def kingdom_cmd(message):
    parts = message.text.split()
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    u = get_or_create_user(uid, uname)

    if len(parts) >= 3 and parts[1].lower() == 'create':
        k_name = " ".join(parts[2:])
        if u[7]:
            bot.reply_to(message, "❌ Aap pehle se hi ek Kingdom ke member hain!")
            return

        conn = sqlite3.connect('outlaw_realm.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO kingdoms (name, owner_id) VALUES (?, ?)", (k_name, uid))
        kid = cursor.lastrowid
        cursor.execute("UPDATE users SET kingdom_id = ? WHERE user_id = ?", (kid, uid))
        conn.commit()
        conn.close()

        bot.reply_to(message, f"🏰 **KINGDOM CREATED!** 🏰\n\nName: `{k_name}`\nRuler: @{uname}", parse_mode="Markdown")
    else:
        bot.reply_to(message, "👑 **Kingdom Syntax:**\n`/kingdom create <Kingdom Name>`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/deposit'])
def deposit_cmd(message):
    parts = message.text.split()
    if len(parts) < 3 or not parts[1].isdigit():
        bot.reply_to(message, "🏛️ **Usage:** `/deposit <amount> <bronze|silver|gold>`", parse_mode="Markdown")
        return

    amt = int(parts[1])
    ctype = parts[2].lower()
    uid = message.from_user.id
    u = get_or_create_user(uid, message.from_user.username or message.from_user.first_name)
    kid = u[7]

    if not kid:
        bot.reply_to(message, "❌ Pehle kingdom banao ya join karo!")
        return

    c_map = {'gold': (4, 'treasury_gold'), 'silver': (5, 'treasury_silver'), 'bronze': (6, 'treasury_bronze')}
    if ctype not in c_map:
        bot.reply_to(message, "❌ Choose: `bronze`, `silver`, or `gold`")
        return

    idx, col = c_map[ctype]
    if (u[idx] or 0) < amt:
        bot.reply_to(message, f"❌ Insufficient `{ctype}` balance!")
        return

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {ctype} = {ctype} - ? WHERE user_id = ?", (amt, uid))
    cursor.execute(f"UPDATE kingdoms SET {col} = {col} + ? WHERE kingdom_id = ?", (amt, kid))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"🏛️ `{amt:,}` {ctype.capitalize()} deposited into Kingdom Treasury!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/rank', '/myrank'])
def rank_cmd(message):
    target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    uid, uname = target_user.id, target_user.username or target_user.first_name

    conn = sqlite3.connect('outlaw_realm.db')
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
            cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = ?", (kid,))
            k_res = cursor.fetchone()
            if k_res: k_name = k_res[0]

            cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = ?", (kid,))
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

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/territory', '/state'])
def territory_current_cmd(message):
    if message.chat.type in ['private']:
        bot.reply_to(message, "❌ Private chat me koi territory nahi hoti!")
        return

    chat_id = message.chat.id
    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()

    cursor.execute("SELECT kingdom_id, territory_tier, territory_level FROM territories WHERE chat_id = ?", (chat_id,))
    res = cursor.fetchone()

    if not res:
        conn.close()
        bot.reply_to(message, "🌐 **GROUP TERRITORY INTEL** 🌐\n━━━━━━━━━━━━━━━━━━━━━\n\nStatus: `Unclaimed Neutral Territory`\n\n💡 Capture karne ke liye `/claim` command run karein!", parse_mode="Markdown")
        return

    kid, tier, t_lvl = res[0], res[1] or "Standard Tier", res[2] or 1
    cursor.execute("SELECT name, owner_id FROM kingdoms WHERE kingdom_id = ?", (kid,))
    k_data = cursor.fetchone()
    k_name = k_data[0] if k_data else "Unknown Empire"
    boss_id = k_data[1] if k_data else None

    cursor.execute("SELECT username FROM users WHERE user_id = ?", (boss_id,))
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
    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute("SELECT k.name, COUNT(t.chat_id) FROM kingdoms k LEFT JOIN territories t ON k.kingdom_id = t.kingdom_id GROUP BY k.kingdom_id")
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()

    cursor.execute("SELECT kingdom_id FROM territories WHERE chat_id = ?", (chat_id,))
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

    cursor.execute("SELECT owner_id FROM kingdoms WHERE kingdom_id = ?", (def_kid,))
    def_boss_id = cursor.fetchone()[0]

    cursor.execute("SELECT user_id, army_power FROM users WHERE user_id = ?", (def_boss_id,))
    defender_data = cursor.fetchone()
    def_pwr = defender_data[1] if defender_data else 0
    att_pwr = attacker[9] or 0

    if att_pwr > def_pwr:
        cursor.execute("UPDATE territories SET kingdom_id = ? WHERE chat_id = ?", (att_kid, chat_id))
        cursor.execute("UPDATE users SET bounty_points = bounty_points + 500, xp = xp + 150 WHERE user_id = ?", (uid,))
        conn.commit()
        msg = (
            f"⚔️ **WAR DECLARED & INSTANT VICTORY!** ⚔️\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🥊 **Attacker PWR:** `{att_pwr:,}`\n"
            f"🛡️ **Defender Boss PWR:** `{def_pwr:,}`\n\n"
            f"🏆 **RESULT:** @{uname} ne enemy ko crush karke territory snatch kar li!\n"
            f"➕ **Bounty Points:** `+500` | ➕ **XP:** `+150`"
        )
    else:
        cursor.execute("UPDATE users SET army_power = MAX(0, army_power - 100) WHERE user_id = ?", (uid,))
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()

    cursor.execute("SELECT kingdom_id, territory_tier, territory_level FROM territories WHERE chat_id = ?", (chat_id,))
    existing = cursor.fetchone()

    if existing:
        owner_kid, tier, t_lvl = existing[0], existing[1] or "Standard Tier", existing[2] or 1
        cursor.execute("SELECT name, owner_id FROM kingdoms WHERE kingdom_id = ?", (owner_kid,))
        k_data = cursor.fetchone()
        k_name = k_data[0] if k_data else "Unknown"
        boss_id = k_data[1] if k_data else None

        cursor.execute("SELECT username FROM users WHERE user_id = ?", (boss_id,))
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

    cursor.execute("INSERT INTO territories (chat_id, kingdom_id, territory_tier, territory_level) VALUES (?, ?, ?, ?)", (chat_id, user_kid, assigned_tier, assigned_lvl))
    cursor.execute("UPDATE users SET bounty_points = bounty_points + 500, xp = xp + 100 WHERE user_id = ?", (uid,))
    cursor.execute("UPDATE kingdoms SET treasury_bronze = treasury_bronze + 1000, treasury_silver = treasury_silver + 10 WHERE kingdom_id = ?", (user_kid,))
    conn.commit()

    cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = ?", (user_kid,))
    my_k_data = cursor.fetchone()
    my_k_name = my_k_data[0] if my_k_data else "Your Kingdom"

    cursor.execute("SELECT bounty_points, xp FROM users WHERE user_id = ?", (uid,))
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {curr_type} = {curr_type} - ? WHERE user_id = ?", (amount, message.from_user.id))
    cursor.execute(f"UPDATE users SET {curr_type} = {curr_type} + ? WHERE user_id = ?", (amount, target_user.id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"💸 Transfer `{amount:,}` {curr_type.capitalize()} to @{target_user.username or target_user.first_name} Success!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/hire', '/recruitment'])
def hire_main_router(message):
    parts = message.text.split()
    if len(parts) == 1:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🌾 Farmer", callback_data="shop_farmer"),
            InlineKeyboardButton("⚒️ Blacksmith", callback_data="shop_blacksmith")
        )
        markup.add(
            InlineKeyboardButton("🏪 Shopkeeper", callback_data="shop_shopkeeper"),
            InlineKeyboardButton("⚔️ Knight", callback_data="shop_knight")
        )
        markup.add(
            InlineKeyboardButton("🎩 Noble", callback_data="shop_noble"),
            InlineKeyboardButton("👑 Royal", callback_data="shop_royal")
        )
        markup.add(
            InlineKeyboardButton("⚙️ Machinery", callback_data="shop_machinery")
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

    conn = sqlite3.connect('outlaw_realm.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET bronze = bronze - ?, army_power = army_power + ? WHERE user_id = ?", (total_cost, total_pwr, uid))
    conn.commit()

    cursor.execute("SELECT army_power, bronze FROM users WHERE user_id = ?", (uid,))
    updated = cursor.fetchone()
    conn.close()

    bot.reply_to(message, f"⚔️ Hired `{amount:,}x {unit_name}`!\nGained: `+{total_pwr:,}` PWR\nTotal PWR: `{updated[0]:,}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop_"))
def callback_shop_units(call):
    unit = call.data.replace("shop_", "").capitalize()
    costs = {"Farmer": "10 Bronze = +1 PWR", "Blacksmith": "30 Bronze = +3 PWR", "Shopkeeper": "60 Bronze = +7 PWR", "Knight": "150 Bronze = +20 PWR", "Noble": "350 Bronze = +50 PWR", "Royal": "800 Bronze = +150 PWR", "Machinery": "2,000 Bronze = +500 PWR"}
    info = costs.get(unit, "10 Bronze = +1 PWR")
    bot.answer_callback_query(call.id, f"{unit} Info: {info}\nUse command: /hire {unit} <amount>", show_alert=True)

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/army'])
def army_cmd(message):
    target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    uid, uname = target_user.id, target_user.username or target_user.first_name
    u = get_or_create_user(uid, uname)
    army_val = u[9] if (len(u) > 9 and u[9] is not None) else 0
    bot.reply_to(message, f"🪖 **OUTLAW MILITARY FORCE** 🪖\n\nUser: @{uname}\nTotal Army Power: `{army_val:,}` PWR", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/top', '/leaderboard'])
def top_cmd(message):
    conn = sqlite3.connect('outlaw_realm.db')
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
            cursor.execute("SELECT name FROM kingdoms WHERE kingdom_id = ?", (kid,))
            k_res = cursor.fetchone()
            if k_res: k_name = k_res[0]

            cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = ?", (kid,))
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
    bot.reply_to(message, msg)

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/profile', '/me'])
def profile_cmd(message):
    target_user = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    uid, uname = target_user.id, target_user.username or target_user.first_name
    u = get_or_create_user(uid, uname)
    kid = u[7]

    k_name = "None"
    t_count = 0
    g_gold, g_silver, g_bronze = 0, 0, 0

    if kid:
        conn = sqlite3.connect('outlaw_realm.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, treasury_gold, treasury_silver, treasury_bronze FROM kingdoms WHERE kingdom_id = ?", (kid,))
        k_data = cursor.fetchone()
        if k_data:
            k_name, g_gold, g_silver, g_bronze = k_data[0], k_data[1] or 0, k_data[2] or 0, k_data[3] or 0
        cursor.execute("SELECT COUNT(*) FROM territories WHERE kingdom_id = ?", (kid,))
        t_res = cursor.fetchone()
        if t_res: t_count = t_res[0]
        conn.close()

    bounty_val = u[8] if (len(u) > 8 and u[8] is not None) else 0
    army_val = u[9] if (len(u) > 9 and u[9] is not None) else 0

    msg = (
        f"🛡️ OUTLAW PROFILE: @{uname}\n"
        f"🎖️ Level: {u[2]} (XP: {u[3]})\n"
        f"💰 Personal Wealth:\n   🟡 Gold: {u[4]:,} | 🥈 Silver: {u[5]:,} | 🥉 Bronze: {u[6]:,}\n"
        f"⚔️ Army Power: {army_val:,} Troops\n"
        f"🏆 Bounty Points: {bounty_val:,}\n\n"
        f"🏰 Kingdom Details:\n"
        f"• Name: {k_name}\n"
        f"• Controlled Territories: {t_count}\n"
        f"• Treasury:\n   🟡 Gold: {g_gold:,} | 🥈 Silver: {g_silver:,} | 🥉 Bronze: {g_bronze:,}"
    )
    bot.reply_to(message, msg)

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/start'])
def start_cmd(message):
    uid, uname = message.from_user.id, message.from_user.username or message.from_user.first_name
    u = get_or_create_user(uid, uname)
    bot.reply_to(message, f"⚔️ WELCOME TO OUTLAW REALM ⚔️\n👤 Outlaw: @{uname}\n🎖️ Rank: Level {u[2]}\n🟡 Gold: {u[4]:,} | 🥈 Silver: {u[5]:,} | 🥉 Bronze: {u[6]:,}\n\n💡 Commands ke liye /help ya /story chalaein!")

@bot.message_handler(func=lambda m: m.text and m.text.split()[0].lower() in ['/help', '/guide'])
def help_cmd(message):
    bot.reply_to(message, "📜 OUTLAW REALM - FULL COMMAND LIST 📜\n\n• /status (Restricted to Log Group)\n• /addadmin (Admin Only)\n• /convert <amt> <from> <to>\n• /duel (Reply user)\n• /deposit <amt> <curr>\n• /kingdom create <Name>\n• /give <amt> <curr>\n• /claim\n• /war\n• /rank\n• /top\n• /profile")
    

@bot.message_handler(commands=['admin', 'owner'])
def admin_panel(message):
    uid = message.from_user.id
    if not is_admin(uid):
        bot.reply_to(message, "❌ Yeh command sirf Owner ya Admins ke liye restricted hai!")
        return
    
    bot.reply_to(message, 
        "👑 **OUTLAW REALM - SUPREME ADMIN PANEL** 👑\n\n"
        "Welcome Overlord! Aapke paas saari powers hain.\n\n"
        "🛠 **Available Admin Commands:**\n"
        "• `/addadmin <user_id>` - Kisi naye user ko Admin banayein\n"
        "• `/godmode` - Apne coins aur army ko infinite/max karein", 
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['addadmin'])
def add_admin_cmd(message):
    uid = message.from_user.id
    if uid not in OWNER_IDS:
        bot.reply_to(message, "❌ Sirf main Owner hi naye admins add kar sakta hai!")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Sahi tarika: `/addadmin <user_id>` likhein.", parse_mode="Markdown")
        return
    
    try:
        new_admin_id = int(parts[1])
        conn = sqlite3.connect('outlaw_realm.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Success! User ID `{new_admin_id}` ko successfully Admin bana diya gaya hai.", parse_Mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error aa gaya: {e}")

@bot.message_handler(commands=['godmode'])
def godmode_cmd(message):
    uid = message.from_user.id
    uname = message.from_user.username or message.from_user.first_name or "Outlord"
    
    if not is_admin(uid):
        bot.reply_to(message, "❌ Yeh command sirf Owner ke liye restricted hai!")
        return
    
    try:
        conn = sqlite3.connect('outlaw_realm.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,))
        user_exists = cursor.fetchone()
        
        if not user_exists:
            cursor.execute("INSERT INTO users (user_id, username, bronze) VALUES (?, ?, 1000)", (uid, uname))
        
        cursor.execute("""
            UPDATE users 
            SET gold = 999999999, 
                silver = 999999999, 
                bronze = 999999999, 
                army_power = 999999, 
                level = 99, 
                xp = 999999 
            WHERE user_id = ?
        """, (uid,))
        
        conn.commit()
        conn.close()
        
        bot.reply_to(
            message, 
            "⚡ **GODMODE ACTIVATED!** ⚡\n\n"
            "👑 Overlord, aapke sare coins, army power aur level ko infinite kar diya gaya hai!\n"
            "Ab `/profile` command chala kar check kar lo.", 
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error aa gaya: {e}")

bot.infinity_polling()
