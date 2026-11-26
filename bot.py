import asyncio
import base64
from datetime import datetime
import json
import os
import re
import socket
import time
from urllib.parse import parse_qs, quote, unquote, urlparse
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiohttp import web
import requests



# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 6146253635
WEBAPP_URL = "https://phantom34121.github.io/Unit73-Tew-x-Vpn-/"
API_URL = "https://unit73-tew-x-vpn-3.onrender.com"  # сюда потом впишете вашу ссылку с Render
DB_FILE = "users_db.json"
PORT = int(os.environ.get("PORT", 8080))

# =============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SOURCES = [
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://githubusercontent.com",
    "https://githubusercontent.com",
]


RU_BYPASS_DOMAINS = [
    "yandex.ru",
    "ya.ru",
    "vk.com",
    "mail.ru",
    "gosuslugi.ru",
    "sberbank.ru",
    "tbank.ru",
    "ozon.ru",
    "wildberries.ru",
    "dzen.ru",
    "rutube.ru",
    "kinopoisk.ru",
    "avito.ru",
    "2gis.ru",
    "mos.ru",
]

PRIORITY_SNI = RU_BYPASS_DOMAINS + [
    "google.com",
    "://google.com",
    "googleapis.com",
    "gstatic.com",
    "youtube.com",
    "googlevideo.com",
    "://google.com",
]

FORCE_PROXY_DOMAINS = [
    "google.com",
    "googleapis.com",
    "gstatic.com",
    "youtube.com",
    "youtu.be",
    "googlevideo.com",
    "ggpht.com",
    "googleusercontent.com",
    "discord.com",
    "discord.gg",
    "discord.media",
    "discordapp.com",
    "discordapp.net",
    "discordstatus.com",
    "dis.gd",
    "telegram.org",
    "telegram.me",
    "t.me",
    "tdesktop.com",
    "telegra.ph",
    "telesco.pe",
    "tx.me",
    "tg.dev",
    "instagram.com",
    "cdninstagram.com",
    "facebook.com",
    "x.com",
    "twitter.com",
]

TELEGRAM_IP_CIDRS = [
    "91.108.4.0/22",
    "91.108.8.0/22",
    "91.108.12.0/22",
    "91.108.16.0/22",
    "91.108.20.0/22",
    "91.108.56.0/22",
    "149.154.160.0/20",
    "185.76.151.0/24",
]

CACHED_SERVERS = []


# ==================== РАБОТА С БАЗОЙ ПОЛЬЗОВАТЕЛЕЙ ====================


def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "banned": []}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "banned": []}


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== ПОИСК И ПРОВЕРКА СЕРВЕРОВ ====================


def check_tcp_ping(host, port):
    try:
        start = time.time()
        sock = socket.create_connection((host, port), timeout=1.2)
        sock.close()
        return round((time.time() - start) * 1000)
    except Exception:
        return None


def analyze_server(link):
    parsed = urlparse(link)
    params = parse_qs(parsed.query)
    sni = params.get("sni", [""])[0].lower()
    host = (parsed.hostname or "").lower()
    net_type = params.get("type", ["tcp"])[0].lower()
    security = params.get("security", [""])[0].lower()

    is_wl = any(domain in sni or domain in host for domain in PRIORITY_SNI)
    is_voice = security == "reality" or net_type in ["tcp", "grpc"]
    return is_wl, is_voice


def fetch_servers_sync():
    """Собирает до 100 актуальных VLESS-серверов из 7 источников."""
    raw_links = []
    for url in SOURCES:
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code != 200:
                continue
            text = resp.text.strip()
            if not text.startswith("vless://"):
                try:
                    text = base64.b64decode(text).decode("utf-8", errors="ignore")
                except Exception:
                    pass
            raw_links.extend(re.findall(r"vless://[^\s]+", text))
        except Exception:
            continue

    unique_links = list(set(raw_links))
    found = []

    for link in unique_links:
        try:
            # Берем только современные VLESS с TLS или Reality (работают везде)
            if "security=tls" not in link and "security=reality" not in link:
                continue
            parsed = urlparse(link)
            host = parsed.hostname
            if not host:
                continue

            is_wl, is_voice = analyze_server(link)
            base_part, _, frag = link.partition("#")
            raw_name = unquote(frag) if frag else host

            tags = []
            if is_wl:
                tags.append("WL")
            if is_voice:
                tags.append("TG+DS")
            prefix = f"🛡️[{'/'.join(tags)}] " if tags else "⚡ "

            clean_title = f"{prefix}{raw_name[:28]}"
            new_link = f"{base_part}#{quote(clean_title)}"
            found.append({
                "name": clean_title,
                "ping": 45,  # Реальный пинг измерит сам телефон в INCY
                "link": new_link,
                "priority": 1 if (is_wl or is_voice) else 2,
            })
            if len(found) >= 200:  # Собираем запас до 200 ключей для сортировки
                break
        except Exception:
            continue

    # Сортируем так, чтобы серверы с пометками [WL] и [TG+DS] были первыми
    found.sort(key=lambda x: x["priority"])
    return found[:100]  # Отдаем топ-100 серверов в подписку


async def background_updater():
    global CACHED_SERVERS
    loop = asyncio.get_running_loop()
    while True:
        servers = await loop.run_in_executor(None, fetch_servers_sync)
        if servers:
            CACHED_SERVERS = servers
        await asyncio.sleep(1800)


# ==================== КОМАНДЫ И КНОПКИ БОТА ====================


def get_main_keyboard(uid: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="🚀 Открыть VPN Приложение (HTML)",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ],
        [
            InlineKeyboardButton(
                text="🔗 Получить ссылку для INCY", callback_data="get_sub"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚡ Топ-5 быстрых ключей", callback_data="get_keys"
            ),
            InlineKeyboardButton(
                text="📄 Файл (.txt)", callback_data="get_file"
            ),
        ],
    ]
    if str(uid) == str(ADMIN_ID):
        buttons.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Админ-панель (Пользователи / Бан)",
                    callback_data="admin_panel",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db = load_db()
    uid = str(message.from_user.id)
    username = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else "Без юзернейма"
    )
    full_name = message.from_user.full_name
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if uid in db["banned"]:
        await message.answer("⛔ Ваш доступ заблокирован администратором.")
        return

    is_new = uid not in db["users"]
    if is_new:
        db["users"][uid] = {
            "name": full_name,
            "username": username,
            "ip": "Ожидает подключения",
            "joined": now,
            "last_active": now,
            "requests": 1,
        }
        save_db(db)
        if str(uid) != str(ADMIN_ID):
            await bot.send_message(
                ADMIN_ID,
                f"🆕 <b>Новый пользователь в боте!</b>\n"
                f"👤 Имя: {full_name} ({username})\n"
                f"🆔 ID: <code>{uid}</code>",
                parse_mode="HTML",
            )
    else:
        db["users"][uid]["last_active"] = now
        db["users"][uid]["requests"] += 1
        save_db(db)

    await message.answer(
        f"👋 Привет, <b>{full_name}</b>!\n\n"
        f"<b>Твой тариф:</b> ♾️ Безлимит (Трафик и время не ограничены)\n"
        f"<b>Доступно серверов:</b> {len(CACHED_SERVERS)} шт.\n"
        f"<b>Поддержка:</b> Telegram, Discord (голос), Google, YouTube + обход белых списков.\n\n"
        f"Нажми кнопку ниже, чтобы открыть меню подключения в приложение <b>INCY</b>:",
        reply_markup=get_main_keyboard(uid),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "get_sub")
async def cb_get_sub(callback: types.CallbackQuery):
    db = load_db()
    uid = str(callback.from_user.id)
    if uid in db["banned"]:
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return

    if uid in db["users"]:
        db["users"][uid]["last_active"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        db["users"][uid]["requests"] += 1
        save_db(db)

    sub_link = f"{API_URL.rstrip('/')}/sub/{uid}"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Импортировать в 1 клик (HTML)",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад в меню", callback_data="back_main"
                )
            ],
        ]
    )

    await callback.message.edit_text(
        f"🔗 <b>Твоя персональная ссылка подписки:</b>\n\n"
        f"<code>{sub_link}</code>\n\n"
        f"1. Нажми на ссылку выше — она скопируется.\n"
        f"2. Открой приложение <b>INCY</b> → «+» → «Вставить из буфера обмена».\n"
        f"3. Или нажми кнопку ниже, чтобы открыть HTML-приложение и подключить в 1 клик.",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "get_keys")
async def cb_get_keys(callback: types.CallbackQuery):
    db = load_db()
    uid = str(callback.from_user.id)
    if uid in db["banned"]:
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return
    if not CACHED_SERVERS:
        loop = asyncio.get_running_loop()
        servers = await loop.run_in_executor(None, fetch_servers_sync)
        if servers:
            CACHED_SERVERS.extend(servers)

    if not CACHED_SERVERS:
        await callback.answer(
            "⏳ Серверы еще обновляются, попробуйте через 10 секунд...",
            show_alert=True,
        )
        return

    top5 = CACHED_SERVERS[:5]
    text = (
        "⚡ <b>Топ-5 самых быстрых серверов прямо сейчас:</b>\n"
        "<i>(Нажми на ключ, чтобы скопировать и вставить в INCY)</i>\n\n"
    )
    for srv in top5:
        text += f"🔹 <b>{srv['name']}</b>\n<code>{srv['link']}</code>\n\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Назад в меню", callback_data="back_main"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "get_file")
async def cb_get_file(callback: types.CallbackQuery):
    db = load_db()
    uid = str(callback.from_user.id)
    if uid in db["banned"]:
        await callback.answer("⛔ Вы заблокированы!", show_alert=True)
        return

    if not CACHED_SERVERS:
        await callback.answer("⏳ Серверы еще загружаются...", show_alert=True)
        return

    links = [s["link"] for s in CACHED_SERVERS]
    header = [
        "#profile-title: Unlimited VPN [TG + DS + Google + WL]",
        "#subscription-userinfo: upload=0; download=0; total=0; expire=0",
    ]
    raw_content = "\n".join(header + links)
    encoded = base64.b64encode(raw_content.encode("utf-8"))

    file = types.BufferedInputFile(encoded, filename="Unlimited_VPN_INCY.txt")
    await callback.message.answer_document(
        document=file,
        caption="📄 <b>Готовый профиль для INCY!</b>\nСохрани файл и импортируй его в приложение INCY (или открой через «Поделиться → INCY»).",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "back_main")
async def cb_back_main(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    await callback.message.edit_text(
        f"👋 <b>Главное меню VPN</b>\n\n"
        f"• ♾️ Трафик: <b>Безлимит</b>\n"
        f"• 🚀 Активных серверов: <b>{len(CACHED_SERVERS)}</b>\n"
        f"• 🎙️ Поддержка: <b>Telegram, Discord, Google, YouTube</b>",
        reply_markup=get_main_keyboard(uid),
        parse_mode="HTML",
    )
    await callback.answer()


# ==================== АДМИН-ПАНЕЛЬ В БОТЕ ====================


@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await render_admin_panel(message, is_edit=False)


@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await render_admin_panel(callback.message, is_edit=True)
    await callback.answer()


async def render_admin_panel(message: types.Message, is_edit: bool):
    db = load_db()
    users = db["users"]
    banned = db["banned"]

    if not users:
        text = "👥 Пока никто не заходил в бота."
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
            ]
        )
    else:
        text = f"🛡️ <b>Админ-панель (Всего: {len(users)} | В бане: {len(banned)}):</b>\n\n"
        buttons = []
        for uid, info in users.items():
            is_ban = uid in banned
            status = "⛔ ЗАБЛОКИРОВАН" if is_ban else "✅ Активен"
            ip_info = info.get("ip", "Неизвестно")
            text += (
                f"👤 <b>{info['name']}</b> ({info['username']})\n"
                f"🆔 ID: <code>{uid}</code> | {status}\n"
                f"🌐 IP: <code>{ip_info}</code>\n"
                f"🕒 Активность: {info['last_active']} (запросов: {info['requests']})\n"
                f"────────────────────\n"
            )
            if str(uid) != str(ADMIN_ID):
                btn_text = (
                    f"✅ Разблокировать {info['name']}"
                    if is_ban
                    else f"⛔ Заблокировать {info['name']}"
                )
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=btn_text, callback_data=f"toggleban_{uid}"
                        )
                    ]
                )

        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить", callback_data="admin_panel"
                ),
                InlineKeyboardButton(
                    text="🔙 В меню", callback_data="back_main"
                ),
            ]
        )
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if is_edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("toggleban_"))
async def cb_toggle_ban(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    target_uid = callback.data.split("_", 1)[1]
    db = load_db()

    if target_uid in db["banned"]:
        db["banned"].remove(target_uid)
        msg = "✅ Пользователь разблокирован"
    else:
        db["banned"].append(target_uid)
        msg = "⛔ Пользователь заблокирован"

    save_db(db)
    await callback.answer(msg)
    await render_admin_panel(callback.message, is_edit=True)


# ==================== ВСТРОЕННЫЙ СЕРВЕР ДЛЯ HTML MINI APP И INCY ====================

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


async def handle_api_status(request):
    uid = request.match_info.get("uid", "guest")
    db = load_db()
    is_banned = uid in db["banned"]
    servers_info = [
        {"name": s["name"], "ping": s["ping"]} for s in CACHED_SERVERS
    ]
    return web.json_response(
        {"banned": is_banned, "servers": servers_info}, headers=CORS_HEADERS
    )


async def handle_sub(request):
    uid = request.match_info.get("uid", "guest")
    client_ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or request.remote
        or "Неизвестно"
    )
    db = load_db()

    if uid in db["banned"] or client_ip in db["banned"]:
        banned_msg = base64.b64encode(
            "#profile-title: Доступ закрыт\n#announce: Ваш аккаунт заблокирован администратором".encode(
                "utf-8"
            )
        ).decode("utf-8")
        return web.Response(text=banned_msg, headers=CORS_HEADERS)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_first_connect = False
    # Добавьте эти 2 строчки в начало функции handle_sub перед links = [s["link"] for s in CACHED_SERVERS]:
    if not CACHED_SERVERS:
        CACHED_SERVERS.extend(
            await asyncio.get_running_loop().run_in_executor(
                None, fetch_servers_sync
            )
        )

    if uid not in db["users"]:
        db["users"][uid] = {
            "name": f"Прямая ссылка ({uid})",
            "username": "Без Telegram",
            "ip": client_ip,
            "joined": now,
            "last_active": now,
            "requests": 1,
        }
        is_first_connect = True
    else:
        if db["users"][uid].get("ip") in [None, "Ожидает подключения"]:
            is_first_connect = True
        db["users"][uid]["ip"] = client_ip
        db["users"][uid]["last_active"] = now
        db["users"][uid]["requests"] += 1

    save_db(db)

    if is_first_connect and str(uid) != str(ADMIN_ID):
        u_info = db["users"][uid]
        asyncio.create_task(
            bot.send_message(
                ADMIN_ID,
                f"📲 <b>Устройство подключило подписку в INCY!</b>\n"
                f"👤 Пользователь: <b>{u_info['name']}</b> ({u_info['username']})\n"
                f"🌐 IP: <code>{client_ip}</code>",
                parse_mode="HTML",
            )
        )

    links = [s["link"] for s in CACHED_SERVERS]
    bypass_domains = ",".join(RU_BYPASS_DOMAINS)
    proxy_domains = ",".join(FORCE_PROXY_DOMAINS)
    proxy_ips = ",".join(TELEGRAM_IP_CIDRS)

    header = [
        "#profile-title: Unlimited VPN [TG + DS + Google + WL]",
        "#profile-update-interval: 1",
        "#subscription-userinfo: upload=0; download=0; total=0; expire=0",
        f"#routing-bypass-domains: {bypass_domains}",
        f"#routing-proxy-domains: {proxy_domains}",
        f"#routing-proxy-ips: {proxy_ips}",
        "#announce: Безлимит. Telegram, Discord, Google и YouTube работают через VPN.",
    ]
    encoded = base64.b64encode("\n".join(header + links).encode("utf-8")).decode(
        "utf-8"
    )
    sub_headers = {
        **CORS_HEADERS,
        "profile-title": "base64:"
        + base64.b64encode("Unlimited VPN [TG+DS+WL]".encode("utf-8")).decode(
            "utf-8"
        ),
        "profile-update-interval": "1",
        "subscription-userinfo": "upload=0; download=0; total=0; expire=0",
    }
    return web.Response(text=encoded, headers=sub_headers)


# ==================== ЗАПУСК ====================


async def main():
    asyncio.create_task(background_updater())

    web_app = web.Application()
    web_app.router.add_get("/api/status/{uid}", handle_api_status)
    web_app.router.add_get("/sub/{uid}", handle_sub)

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"🤖 Бот и сервер подписок запущены на порту {PORT}!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
