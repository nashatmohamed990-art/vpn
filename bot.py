import asyncio
import aiohttp
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = "8637905953:AAEjrq8y5FReNXRL9-Ukz0MuL-DdgAgrjcI"

BASE_URL = "https://www.freevmess.com"

# قائمة السيرفرات لكل بروتوكول
PROTOCOLS = {
    "v2ray": {
        "name": "🔵 V2ray",
        "list_url": f"{BASE_URL}/server-v2ray",
        "server_pattern": "{country}-v2ray-server",
        "submit_url": f"{BASE_URL}/create-v2ray",
    },
    "vmesswebsockets": {
        "name": "🟣 Vmess WebSocket",
        "list_url": f"{BASE_URL}/server-vmesswebsockets",
        "server_pattern": "{country}-vmesswebsockets-server",
        "submit_url": f"{BASE_URL}/create-vmesswebsockets",
    },
    "vlesswebsockets": {
        "name": "🟢 Vless WebSocket",
        "list_url": f"{BASE_URL}/server-vlesswebsockets",
        "server_pattern": "{country}-vlesswebsockets-server",
        "submit_url": f"{BASE_URL}/create-vlesswebsockets",
    },
    "trojan": {
        "name": "🔴 Trojan",
        "list_url": f"{BASE_URL}/server-trojan",
        "server_pattern": "{country}-trojan-server",
        "submit_url": f"{BASE_URL}/create-trojan",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE_URL,
}


async def fetch_online_servers(session: aiohttp.ClientSession, list_url: str) -> list:
    """يجيب السيرفرات الأونلاين من صفحة البروتوكول"""
    servers = []
    try:
        async with session.get(list_url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            items = soup.find_all("li")
            current = {}
            for li in items:
                text = li.get_text(strip=True).lower()
                if "server online" in text:
                    if current.get("country"):
                        current["online"] = True
                        servers.append(dict(current))
                        current = {}
                elif "server offline" in text:
                    current = {}
                else:
                    # محاولة استخراج اسم البلد من الـ links
                    pass

            # طريقة تانية: نجيب الـ links مباشرة
            links = soup.find_all("a", href=True)
            for link in links:
                href = link["href"]
                if "-server" in href and BASE_URL in href:
                    country = href.replace(BASE_URL + "/", "").replace("-server", "").split("-")[0]
                    # نشوف لو السيرفر ده أونلاين
                    parent = link.find_parent()
                    if parent:
                        siblings_text = parent.get_text()
                        if "Online" in siblings_text:
                            servers.append({
                                "country": country,
                                "url": href,
                                "online": True
                            })
    except Exception as e:
        print(f"Error fetching servers: {e}")
    return servers


async def get_servers_from_page(session: aiohttp.ClientSession, list_url: str) -> list:
    """يجيب كل السيرفرات مع حالتها"""
    servers = []
    try:
        async with session.get(list_url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            # كل سيرفر في div أو section
            # نبحث عن pattern: اسم البلد + Server Online/Offline + رابط Create account
            create_links = soup.find_all("a", string=lambda t: t and "Create" in t)
            
            for link in create_links:
                href = link.get("href", "")
                if not href:
                    continue
                
                # استخراج اسم البلد من الـ URL
                # مثال: /unitedstates-v2ray-server
                path = href.replace(BASE_URL, "").strip("/")
                parts = path.split("-")
                country = parts[0] if parts else "unknown"
                
                # نبحث عن حالة السيرفر في العناصر القريبة
                parent = link.find_parent()
                container_text = ""
                for _ in range(5):  # نطلع 5 مستويات لفوق
                    if parent:
                        container_text = parent.get_text()
                        if "Online" in container_text or "Offline" in container_text:
                            break
                        parent = parent.find_parent()
                
                is_online = "Server Online" in container_text
                
                servers.append({
                    "country": country.capitalize(),
                    "url": href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/"),
                    "online": is_online
                })
    except Exception as e:
        print(f"Error: {e}")
    return servers


async def create_account_and_get_link(session: aiohttp.ClientSession, server_url: str) -> str | None:
    """يدخل على صفحة السيرفر ويعمل submit ويرجع الـ vmess link"""
    try:
        # أول نجيب الصفحة عشان نحصل على الـ form data والـ token لو فيه
        async with session.get(server_url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            
            # نبحث عن الـ form
            form = soup.find("form")
            if not form:
                # ممكن الـ vmess link موجود مباشرة في الصفحة
                return extract_vmess_from_html(html)
            
            form_action = form.get("action", server_url)
            if not form_action.startswith("http"):
                form_action = BASE_URL + "/" + form_action.lstrip("/")
            
            # نجمع كل الـ inputs
            form_data = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                value = inp.get("value", "")
                if name:
                    form_data[name] = value
            
            # نعمل POST
            submit_headers = {**HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
            async with session.post(form_action, data=form_data, headers=submit_headers, 
                                   timeout=aiohttp.ClientTimeout(total=20)) as post_resp:
                result_html = await post_resp.text()
                return extract_vmess_from_html(result_html)
                
    except Exception as e:
        print(f"Error creating account: {e}")
        return None


def extract_vmess_from_html(html: str) -> str | None:
    """يستخرج الـ vmess/vless/trojan link من الـ HTML"""
    import re
    
    patterns = [
        r'vmess://[A-Za-z0-9+/=]+',
        r'vless://[^\s"<>]+',
        r'trojan://[^\s"<>]+',
        r'ss://[^\s"<>]+',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(0)
    
    # نبحث في textarea أو code elements
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["textarea", "code", "pre", "p", "div"]):
        text = tag.get_text(strip=True)
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
    
    return None


# =================== TELEGRAM HANDLERS ===================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔵 V2ray", callback_data="proto_v2ray"),
         InlineKeyboardButton("🟣 Vmess WS", callback_data="proto_vmesswebsockets")],
        [InlineKeyboardButton("🟢 Vless WS", callback_data="proto_vlesswebsockets"),
         InlineKeyboardButton("🔴 Trojan", callback_data="proto_trojan")],
        [InlineKeyboardButton("⚡ جيبلي أفضل link تلقائي", callback_data="auto_best")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 أهلًا!\n\n"
        "اختار البروتوكول اللي عايزه أو اضغط *⚡ تلقائي* وأنا هجيبلك أحسن رابط شغال:\n",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "auto_best":
        await query.edit_message_text("⏳ بدور على أفضل سيرفر أونلاين... استنى ثواني")
        await handle_auto_best(query)
        return

    if data.startswith("proto_"):
        proto_key = data.replace("proto_", "")
        proto = PROTOCOLS.get(proto_key)
        if not proto:
            await query.edit_message_text("❌ بروتوكول مش معروف")
            return

        await query.edit_message_text(f"⏳ بجيب السيرفرات الأونلاين لـ {proto['name']}...")
        
        async with aiohttp.ClientSession() as session:
            servers = await get_servers_from_page(session, proto["list_url"])
        
        online = [s for s in servers if s["online"]]
        
        if not online:
            await query.edit_message_text(
                f"😕 مفيش سيرفرات أونلاين دلوقتي لـ {proto['name']}\n"
                "جرب بروتوكول تاني أو استنى شوية."
            )
            return
        
        # اعمل buttons للسيرفرات
        keyboard = []
        for s in online[:10]:  # أقصى 10
            flag = get_flag(s["country"])
            keyboard.append([InlineKeyboardButton(
                f"{flag} {s['country']}",
                callback_data=f"get_{s['url']}"
            )])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
        
        await query.edit_message_text(
            f"{proto['name']} — اختار السيرفر:\n"
            f"({len(online)} سيرفر أونلاين)",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("get_"):
        server_url = data.replace("get_", "")
        await query.edit_message_text("⏳ بعمل الأكاونت وبجيب الرابط...")
        
        async with aiohttp.ClientSession() as session:
            link = await create_account_and_get_link(session, server_url)
        
        if link:
            await query.edit_message_text(
                f"✅ *الرابط جاهز!*\n\n"
                f"`{link}`\n\n"
                f"📋 انسخ الرابط وحطه في V2rayTun",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ مش قادر أجيب رابط من السيرفر ده دلوقتي.\n"
                "ممكن السيرفر مش شغال صح. جرب سيرفر تاني."
            )

    elif data == "back":
        keyboard = [
            [InlineKeyboardButton("🔵 V2ray", callback_data="proto_v2ray"),
             InlineKeyboardButton("🟣 Vmess WS", callback_data="proto_vmesswebsockets")],
            [InlineKeyboardButton("🟢 Vless WS", callback_data="proto_vlesswebsockets"),
             InlineKeyboardButton("🔴 Trojan", callback_data="proto_trojan")],
            [InlineKeyboardButton("⚡ جيبلي أفضل link تلقائي", callback_data="auto_best")],
        ]
        await query.edit_message_text(
            "اختار البروتوكول:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def handle_auto_best(query):
    """يجيب أول سيرفر أونلاين من أي بروتوكول تلقائيًا"""
    async with aiohttp.ClientSession() as session:
        for proto_key, proto in PROTOCOLS.items():
            servers = await get_servers_from_page(session, proto["list_url"])
            online = [s for s in servers if s["online"]]
            
            if online:
                best = online[0]
                link = await create_account_and_get_link(session, best["url"])
                
                if link:
                    await query.edit_message_text(
                        f"✅ *رابط جاهز تلقائيًا!*\n\n"
                        f"🌍 السيرفر: {best['country']} ({proto['name']})\n\n"
                        f"`{link}`\n\n"
                        f"📋 انسخ الرابط وحطه في V2rayTun",
                        parse_mode="Markdown"
                    )
                    return
        
        await query.edit_message_text(
            "😕 مش لاقي سيرفرات أونلاين دلوقتي.\n"
            "استنى شوية وحاول تاني."
        )


def get_flag(country: str) -> str:
    flags = {
        "unitedstates": "🇺🇸", "us": "🇺🇸",
        "german": "🇩🇪", "germany": "🇩🇪",
        "netherlands": "🇳🇱",
        "unitedkingdom": "🇬🇧", "uk": "🇬🇧",
        "france": "🇫🇷",
        "singapore": "🇸🇬",
        "japan": "🇯🇵",
        "canada": "🇨🇦",
        "australia": "🇦🇺",
        "india": "🇮🇳",
        "turkey": "🇹🇷",
        "italy": "🇮🇹",
        "poland": "🇵🇱",
        "hongkong": "🇭🇰",
        "greece": "🇬🇷",
        "spain": "🇪🇸",
        "sweden": "🇸🇪",
    }
    return flags.get(country.lower(), "🌍")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ البوت شغال!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
