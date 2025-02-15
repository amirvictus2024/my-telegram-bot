import logging
import datetime
import random
import ipaddress
import pickle
import os
import time
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
)

# ------------------ تنظیمات لاگینگ ------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------ توابع Pickle (ذخیره/بازیابی) ------------------
def load_balance():
    global user_balance
    if os.path.exists("balance.pkl"):
        with open("balance.pkl", "rb") as f:
            user_balance = pickle.load(f)
    else:
        user_balance = {}

def save_balance():
    with open("balance.pkl", "wb") as f:
        pickle.dump(user_balance, f)

def load_history():
    global purchase_history
    if os.path.exists("history.pkl"):
        with open("history.pkl", "rb") as f:
            purchase_history = pickle.load(f)
    else:
        purchase_history = {}

def save_history():
    with open("history.pkl", "wb") as f:
        pickle.dump(purchase_history, f)

# ------------------ متغیرهای سراسری ------------------
admin_ids = {7240662021}
ADMIN_PASSWORD = "1"

user_balance = {}  # {user_id: amount}
purchase_history = {}  # { user_id: [ {type, plan, ip1, ip2, ipv6_1, ipv6_2, cost, discount, timestamp}, ... ] }
pending_receipts = {}  # { user_id: { ... } }
receipt_photos = {}
pending_balance_requests = {}  # { user_id: amount }
pending_balance_receipts = {}
admin_state = {}

# تنظیمات پلن‌های DNS اختصاصی
DNS_CONFIGS = {
    "امارات": {
        "name": "سرور امارات",
        "price": 40000,
        "cidr_ranges": [
            "184.25.205.0/24",
            "5.30.0.0/15",
            "5.32.0.0/17",
            "23.194.192.0/22",
            "46.19.77.0/24",
            "46.19.78.0/23",
            "80.227.0.0/16",
            "87.200.0.0/15",
            "91.72.0.0/14",
            "94.200.0.0/14",
            "94.204.0.0/15",
            "94.206.0.0/16",
            "94.207.0.0/19",
            "94.207.48.0/20",
            "94.207.64.0/18",
            "94.207.128.0/17",
            "104.109.251.0/24",
            "149.24.230.0/23",
            "160.83.52.0/23",
            "213.132.32.0/19",
        ],
        "flag": "🇦🇪",
        "ipv6_prefix": "2a02:2ae8"  # پیش‌فرض قابل تغییر
    },
    "آلمان1": {
        "name": "سرور آلمان 1",
        "price": 50000,
        "cidr_ranges": [
            "84.128.0.0/10",
            "87.128.0.0/10",
            "91.0.0.0/10",
            "79.192.0.0/10",
            "93.192.0.0/10",
            "217.224.0.0/11",
            "80.128.0.0/11",
            "91.32.0.0/11",
            "93.192.0.0/11",
            "217.80.0.0/12",
        ],
        "flag": "🇩🇪",
        "ipv6_prefix": "2a02:2ae8"  # طبق درخواست
    },
    "ترکیه": {
        "name": "سرور ترکیه",
        "price": 60000,
        "cidr_ranges": [
            "78.161.221.0/24",
            "78.163.24.0/24",
            "78.163.96.0/21",
            "78.163.105.0/24",
            "78.163.112.0/20",
            "78.163.128.0/22",
            "78.163.156.0/23",
            "78.163.164.0/22",
            "78.164.209.0/24",
            "78.165.64.0/20",
            "78.165.80.0/21",
            "78.165.88.0/24",
            "78.165.92.0/22",
            "78.165.96.0/19",
            "78.165.192.0/20",
            "78.165.208.0/24",
            "78.165.211.0/24",
            "78.165.212.0/23",
            "78.165.215.0/24",
            "78.165.216.0/24",
        ],
        "flag": "🇹🇷",
        "ipv6_prefix": "2a02:2ae8"
    },
}

awaiting_custom_balance = {}

discount_codes = {"OFF10": 10, "OFF20": 20, "OFF30": 30}
user_discount = {}
awaiting_discount_code = {}

blocked_users = set()
referral_points = {}  # { user_id: points }
referred_users = set()
all_users = set()
BOT_USERNAME = "amir_xknow_bot"
FORCE_JOIN_CHANNEL = None
FORCE_JOIN_ENABLED = False

ENABLE_DNS_BUTTON = True
ENABLE_ACCOUNT_BUTTON = True
ENABLE_BALANCE_BUTTON = True
ENABLE_REFERRAL_BUTTON = True
ENABLE_WIREGUARD_BUTTON = True
ENABLE_SITE_SUBSCRIPTION_BUTTON = True

SITE_SUBSCRIPTION_PLANS = {
    "1": {
        "name": "اشتراک 1 ماهه",
        "price": 450000,
        "username": "null",
        "password": "null",
        "identifier": "null",
    },
    "3": {
        "name": "اشتراک 3 ماهه",
        "price": 650000,
        "username": "null",
        "password": "null",
        "identifier": "null",
    },
    "6": {
        "name": "اشتراک 6 ماهه",
        "price": 850000,
        "username": "null",
        "password": "null",
        "identifier": "null",
    },
}

TERMS_TEXT = (
    "📜 قوانین و مقررات:\n\n"
    "1. استفاده از سرویس تنها برای اهداف قانونی می‌باشد.\n"
    "2. سرویس‌های ارائه شده توسط ما با تمام اینترنت‌ها سازگار و تست شده‌اند. اگر سرویس برای شما کار نکند، مشکل مربوط به اینترنت شماست و به سرویس ما مربوط نمی‌شود.\n"
    "3. در صورت بروز هرگونه مشکل، با پشتیبانی تماس بگیرید.\n\n"
    "📞 پشتیبانی: {support}\n\n"
    "برای بازگشت به منوی اصلی روی دکمه زیر کلیک کنید."
)

WIREGUARD_PRICE = 80000

# متغیر بروزرسانی
BOT_UPDATING = False

# آیدی پشتیبانی (قابل تغییر از پنل ادمین)
SUPPORT_ID = "@AMiRHELLBoY_Pv"

# ------------------ توابع کاربردی ------------------
def generate_dns_ip_pair(plan_id: str):
    if plan_id not in DNS_CONFIGS or "cidr_ranges" not in DNS_CONFIGS[plan_id]:
        return None, None
    config = DNS_CONFIGS[plan_id]
    cidr_range = random.choice(config["cidr_ranges"])
    network = ipaddress.ip_network(cidr_range)
    start = int(network.network_address) + 1
    end = int(network.broadcast_address)
    if end - start < 2:
        return None, None
    ip_ints = random.sample(range(start, end), 2)
    ip1 = str(ipaddress.IPv4Address(ip_ints[0]))
    ip2 = str(ipaddress.IPv4Address(ip_ints[1]))
    return ip1, ip2

def generate_dns_ipv6_pair(plan_id: str):
    config = DNS_CONFIGS.get(plan_id, {})
    ipv6_prefix = config.get("ipv6_prefix", "2001:db8")
    seg2 = "".join(random.choices("0123456789abcdef", k=4))
    seg3 = "".join(random.choices("0123456789abcdef", k=4))
    ipv6_1 = f"{ipv6_prefix}:{seg2}:{seg3}::1"
    ipv6_2 = f"{ipv6_prefix}:{seg2}:{seg3}::0"
    return ipv6_1, ipv6_2

# ------------------ منوهای اصلی ------------------
def show_main_menu(update: Update, context: CallbackContext) -> None:
    text = "🏠 منوی اصلی:"
    user_id = update.effective_user.id
    is_admin = user_id in admin_ids
    rows = []
    if is_admin or ENABLE_DNS_BUTTON:
        rows.append([InlineKeyboardButton("🛒 خرید DNS اختصاصی", callback_data="dns_menu")])
    row = []
    if is_admin or ENABLE_ACCOUNT_BUTTON:
        row.append(InlineKeyboardButton("👤 حساب کاربری", callback_data="account_menu"))
    if is_admin or ENABLE_REFERRAL_BUTTON:
        row.append(InlineKeyboardButton("🔗 رفرال و امتیاز", callback_data="referral_menu"))
    if row:
        rows.append(row)
    row = []
    row.append(InlineKeyboardButton("📞 پشتیبانی", callback_data="support_menu"))
    if is_admin or ENABLE_WIREGUARD_BUTTON:
        row.append(InlineKeyboardButton("🔑 وایرگارد اختصاصی", callback_data="wireguard_menu"))
    if row:
        rows.append(row)
    row = []
    if is_admin or ENABLE_BALANCE_BUTTON:
        row.append(InlineKeyboardButton("💳 افزایش موجودی", callback_data="balance_increase"))
    if is_admin or ENABLE_SITE_SUBSCRIPTION_BUTTON:
        row.append(InlineKeyboardButton("💻 خرید یوزرپسورد سایت", callback_data="site_subscription_menu"))
    if row:
        rows.append(row)
    if is_admin:
        rows.append([InlineKeyboardButton("⚙️ پنل ادمین", callback_data="admin_panel_menu")])
    rows.append([InlineKeyboardButton("📜 قوانین و مقررات", callback_data="terms")])
    rows.append([InlineKeyboardButton("🌐 مینی اپ", web_app=WebAppInfo(url="https://amir-xknow.pages.dev/"))])
    keyboard_main = InlineKeyboardMarkup(rows)
    if update.callback_query:
        update.callback_query.edit_message_text(text, reply_markup=keyboard_main)
    else:
        update.message.reply_text(text, reply_markup=keyboard_main)

def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    if BOT_UPDATING:
        update.message.reply_text("⚠️ ربات در حال بروزرسانی می‌باشد. لطفاً بعداً تلاش کنید.")
        return
    if user_id in blocked_users:
        update.message.reply_text("❌ شما توسط مدیریت مسدود شده‌اید.")
        return
    all_users.add(user_id)
    if FORCE_JOIN_ENABLED and FORCE_JOIN_CHANNEL:
        try:
            member = context.bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
            if member.status not in ["member", "creator", "administrator"]:
                if FORCE_JOIN_CHANNEL.startswith("@"):
                    channel_url = f"https://t.me/{FORCE_JOIN_CHANNEL[1:]}"
                else:
                    channel_url = FORCE_JOIN_CHANNEL
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("عضویت", url=channel_url)]]
                )
                update.message.reply_text(
                    f"❌ لطفاً ابتدا در کانال {FORCE_JOIN_CHANNEL} عضو شوید.",
                    reply_markup=keyboard,
                )
                return
        except Exception as e:
            logger.error(f"خطا در بررسی عضویت کانال: {e}")
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and user_id not in referred_users:
                referral_points[referrer_id] = referral_points.get(referrer_id, 0) + 1
                referred_users.add(user_id)
        except ValueError:
            pass
    text = f"سلام {user.first_name}!\nبه ربات خدمات DNS اختصاصی خوش آمدید."
    keyboard = [[InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(text, reply_markup=reply_markup)

# ------------------ منوی DNS اختصاصی ------------------
def dns_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "لطفاً لوکیشن DNS اختصاصی را انتخاب کنید:",
        reply_markup=build_dns_selection_menu(),
    )

def build_dns_selection_menu():
    keyboard = []
    for plan_id, config in DNS_CONFIGS.items():
        keyboard.append(
            [InlineKeyboardButton(
                f"{config['flag']} {config['name']} - {config['price']:,} تومان",
                callback_data=f"buy_dnsplan_{plan_id}"
            )]
        )
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def buy_dns_plan(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 3:
        query.edit_message_text("❌ خطا در ثبت خرید DNS.")
        return
    plan_id = parts[2]
    user_id = query.from_user.id
    base_cost = DNS_CONFIGS[plan_id]["price"]
    if user_id in user_discount:
        code, discount_percent = user_discount[user_id]
        discount_value = int(base_cost * discount_percent / 100)
        final_cost = base_cost - discount_value
        discount_text = f"\n✅ کد تخفیف {code} اعمال شد: {discount_percent}% تخفیف (-{discount_value:,} تومان)"
        del user_discount[user_id]
    else:
        final_cost = base_cost
        discount_text = ""
    balance = user_balance.get(user_id, 0)
    if balance < final_cost:
        query.edit_message_text("❌ موجودی شما کافی نیست. لطفاً ابتدا موجودی خود را افزایش دهید.")
        return
    user_balance[user_id] = balance - final_cost
    save_balance()
    context.bot.send_message(chat_id=user_id, text="😊 موجودی شما کافی است!")
    query.edit_message_text("⏳ در حال پردازش، لطفاً کمی صبر کنید...")
    time.sleep(1)
    ip1, ip2 = generate_dns_ip_pair(plan_id)
    if not ip1 or not ip2:
        query.edit_message_text("❌ خطا در تولید آی‌پی‌ها. لطفاً دوباره تلاش کنید.")
        return
    ipv6_1, ipv6_2 = generate_dns_ipv6_pair(plan_id)
    dns_caption = (
        "⚠️ حتماً از دی‌ان‌اس‌های الکترو:\n"
        "<code>78.157.42.100\n78.157.42.101</code>\n"
        "یا رادار:\n"
        "<code>10.202.10.10\n10.202.10.11</code>\n\n"
    )
    final_text = (
        f"✅ خرید DNS اختصاصی انجام شد.\n\n"
        f"🌐 آی‌پی‌های اختصاصی شما:\n"
        f"IPv4:\n"
        f"IP 1: <code>{ip1}</code>\n"
        f"IP 2: <code>{ip2}</code>\n\n"
        f"IPv6:\n"
        f"IP 1: <code>{ipv6_1}</code>\n"
        f"IP 2: <code>{ipv6_2}</code>\n\n"
        f"💸 مبلغ کسر شده: {final_cost:,} تومان{discount_text}\n\n"
        f"{dns_caption}"
    )
    query.edit_message_text(final_text, parse_mode="HTML")
    record = {
        "type": "dns",
        "plan": plan_id,
        "ip1": ip1,
        "ip2": ip2,
        "ipv6_1": ipv6_1,
        "ipv6_2": ipv6_2,
        "cost": final_cost,
        "discount": discount_text.strip(),
        "timestamp": datetime.datetime.now(),
    }
    if user_id in purchase_history:
        purchase_history[user_id].append(record)
    else:
        purchase_history[user_id] = [record]
    save_history()

# ------------------ منوی وایرگارد اختصاصی ------------------
def wireguard_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    text = "برای خرید وایرگارد اختصاصی لطفاً با پشتیبانی تماس بگیرید:\n@SupportUsername"
    # توجه: قیمت حذف شده است
    keyboard = [[InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")]]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ------------------ منوی قوانین و مقررات ------------------
def terms_and_conditions(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    formatted_terms = TERMS_TEXT.format(support=SUPPORT_ID)
    keyboard = [[InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")]]
    query.edit_message_text(formatted_terms, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ------------------ منوی خرید یوزرپسورد سایت ------------------
def site_subscription_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    text = "💻 خرید یوزرپسورد سایت:\nلطفاً پلن مورد نظر را انتخاب کنید:"
    buttons = []
    for plan_key, plan_info in SITE_SUBSCRIPTION_PLANS.items():
        buttons.append(
            InlineKeyboardButton(
                f"{plan_info['name']} - {plan_info['price']:,} تومان",
                callback_data=f"buy_site_subscription_{plan_key}",
            )
        )
    keyboard = InlineKeyboardMarkup(InlineKeyboardMarkup(buttons).inline_keyboard)
    # استفاده از دکمه‌های تنظیم شده به صورت دستی:
    keyboard = InlineKeyboardMarkup(InlineKeyboardMarkup([[b] for b in buttons]).inline_keyboard)
    keyboard.inline_keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    query.edit_message_text(text, reply_markup=keyboard)

def buy_site_subscription(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 4:
        query.edit_message_text("❌ خطا در انتخاب پلن.")
        return
    plan_key = parts[3]
    if plan_key not in SITE_SUBSCRIPTION_PLANS:
        query.edit_message_text("❌ پلن نامعتبر.")
        return
    plan_info = SITE_SUBSCRIPTION_PLANS[plan_key]
    user_id = query.from_user.id
    cost = plan_info["price"]
    balance = user_balance.get(user_id, 0)
    if balance < cost:
        query.edit_message_text("❌ موجودی شما کافی نیست. لطفاً ابتدا موجودی خود را افزایش دهید.")
        return
    user_balance[user_id] = balance - cost
    save_balance()
    username = plan_info.get("username", "N/A")
    password = plan_info.get("password", "N/A")
    identifier = plan_info.get("identifier", "N/A")
    text = (
        f"✅ خرید {plan_info['name']} با موفقیت انجام شد.\n\n"
        f"💸 مبلغ کسر شده: {cost:,} تومان\n\n"
        "جزئیات اشتراک شما:\n"
        f"👤 یوزرنیم: {username}\n"
        f"🔑 پسورد: {password}\n"
        f"🔖 شناسه: {identifier}\n"
    )
    query.edit_message_text(text)
    record = {
        "type": "site_subscription",
        "plan": plan_key,
        "cost": cost,
        "timestamp": datetime.datetime.now(),
    }
    if user_id in purchase_history:
        purchase_history[user_id].append(record)
    else:
        purchase_history[user_id] = [record]
    save_history()

# ------------------ دریافت رسید پرداخت (عکس) ------------------
def receipt_photo_handler(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id in pending_balance_requests:
        pending_balance_receipts[user_id] = update.message.photo[-1].file_id
        keyboard = [[InlineKeyboardButton("💳 ارسال درخواست افزایش موجودی", callback_data="balance_request_confirm")]]
        update.message.reply_text("✅ عکس رسید دریافت شد. برای نهایی کردن درخواست افزایش موجودی روی دکمه مربوطه کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))
    elif user_id in pending_receipts:
        receipt_photos[user_id] = update.message.photo[-1].file_id
        keyboard = [[InlineKeyboardButton("قبول درخواست", callback_data="confirm_receipt")]]
        update.message.reply_text("✅ عکس رسید دریافت شد. برای نهایی کردن خرید روی دکمه 'قبول درخواست' کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))

def confirm_receipt(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id not in pending_receipts or user_id not in receipt_photos:
        query.edit_message_text("❌ رسید شما یافت نشد. لطفاً ابتدا عکس رسید را ارسال کنید.")
        return
    purchase_info = pending_receipts[user_id]
    photo_file_id = receipt_photos[user_id]
    if purchase_info["type"] == "dns":
        caption = (
            f"خرید DNS اختصاصی\n"
            f"لوکیشن: {DNS_CONFIGS[purchase_info['plan']]['name']}\n"
            f"IPv4: <code>{purchase_info['ip1']}</code> - <code>{purchase_info['ip2']}</code>\n"
            f"IPv6: <code>{purchase_info['ipv6_1']}</code> - <code>{purchase_info['ipv6_2']}</code>\n"
            f"مبلغ: {purchase_info['cost']:,} تومان"
        )
    else:
        caption = "نوع درخواست نامعتبر."
    for admin in admin_ids:
        try:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تایید خرید", callback_data=f"admin_approve_purchase_{user_id}"),
                                               InlineKeyboardButton("❌ رد خرید", callback_data=f"admin_reject_purchase_{user_id}")]])
            context.bot.send_photo(chat_id=admin, photo=photo_file_id,
                                     caption=f"رسید پرداخت از کاربر {user_id}:\n{caption}",
                                     parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"خطا در ارسال رسید به ادمین {admin}: {e}")
    query.edit_message_text("✅ رسید شما ارسال شد و در انتظار تایید ادمین می‌باشد.")

# ------------------ تایید/رد خرید توسط ادمین ------------------
def admin_approve_purchase(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 4:
        if query.message.photo:
            query.edit_message_caption(caption="❌ داده‌های نامعتبر.")
        else:
            query.edit_message_text("❌ داده‌های نامعتبر.")
        return
    try:
        user_id = int(parts[3])
    except ValueError:
        if query.message.photo:
            query.edit_message_caption(caption="❌ خطا در پردازش اطلاعات کاربر.")
        else:
            query.edit_message_text("❌ خطا در پردازش اطلاعات کاربر.")
        return
    if user_id not in pending_receipts:
        if query.message.photo:
            query.edit_message_caption(caption="❌ درخواست خرید یافت نشد.")
        else:
            query.edit_message_text("❌ درخواست خرید یافت نشد.")
        return
    del pending_receipts[user_id]
    if user_id in receipt_photos:
        del receipt_photos[user_id]
    try:
        context.bot.send_message(chat_id=user_id, text="✅ خرید شما تایید شد.")
    except Exception as e:
        logger.error(f"خطا در ارسال پیام به کاربر {user_id}: {e}")
    if query.message.photo:
        query.edit_message_caption(caption="✅ خرید تایید شد.")
    else:
        query.edit_message_text("✅ خرید تایید شد.")

def admin_reject_purchase(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 4:
        if query.message.photo:
            query.edit_message_caption(caption="❌ داده‌های نامعتبر.")
        else:
            query.edit_message_text("❌ داده‌های نامعتبر.")
        return
    try:
        user_id = int(parts[3])
    except ValueError:
        if query.message.photo:
            query.edit_message_caption(caption="❌ خطا در پردازش اطلاعات کاربر.")
        else:
            query.edit_message_text("❌ خطا در پردازش اطلاعات کاربر.")
        return
    if user_id not in pending_receipts:
        if query.message.photo:
            query.edit_message_caption(caption="❌ درخواست خرید یافت نشد.")
        else:
            query.edit_message_text("❌ درخواست خرید یافت نشد.")
        return
    purchase_info = pending_receipts[user_id]
    user_balance[user_id] = user_balance.get(user_id, 0) + purchase_info["cost"]
    save_balance()
    try:
        context.bot.send_message(chat_id=user_id,
                                 text="❌ خرید شما توسط ادمین رد شد. مبلغ کسر شده به حساب شما بازگردانده شد.")
    except Exception as e:
        logger.error(f"خطا در ارسال پیام به کاربر {user_id}: {e}")
    del pending_receipts[user_id]
    if user_id in receipt_photos:
        del receipt_photos[user_id]
    if query.message.photo:
        query.edit_message_caption(caption="✅ خرید رد شد. مبلغ به حساب کاربر بازگردانده شد.")
    else:
        query.edit_message_text("✅ خرید رد شد. مبلغ به حساب کاربر بازگردانده شد.")

# ------------------ افزایش موجودی ------------------
def balance_increase_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    text = "💳 مقدار افزایش موجودی را انتخاب کنید (به تومان):"
    amounts = [10000, 20000, 50000, 100000, 200000, 500000, 1000000]
    keyboard = []
    row = []
    for amt in amounts:
        row.append(InlineKeyboardButton(f"{amt:,}", callback_data=f"balance_increase_{amt}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ مبلغ دلخواه", callback_data="balance_increase_custom")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)

def ask_custom_balance(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    awaiting_custom_balance[query.from_user.id] = True
    query.edit_message_text("✏️ لطفاً مبلغ دلخواه (به تومان) را به صورت عددی ارسال کنید:")

def show_balance_payment_screen(query, context, amount):
    text = (
        f"برای افزایش موجودی به مبلغ {amount:,} تومان، مبلغ را به حساب بانکی واریز کنید.\n\n"
        "💳 شماره کارت: <code>6219 8619 4308 4037</code>\n"
        "به نام: امیرحسین سیاهبالایی\n\n"
        "سپس رسید پرداخت را به صورت عکس ارسال کنید و روی دکمه '💳 ارسال درخواست افزایش موجودی' کلیک کنید."
    )
    keyboard = [
        [InlineKeyboardButton("💳 ارسال درخواست افزایش موجودی", callback_data="balance_request_confirm")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

def handle_balance_increase_request(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    if data.startswith("balance_increase_"):
        parts = data.split("_")
        if len(parts) != 3:
            query.edit_message_text("❌ خطا در انتخاب مبلغ.")
            return
        try:
            amount = int(parts[2])
        except ValueError:
            query.edit_message_text("❌ مقدار نامعتبر.")
            return
        if amount < 10000 or amount > 1000000:
            query.edit_message_text("❌ مقدار انتخاب شده خارج از محدوده مجاز است.")
            return
        pending_balance_requests[query.from_user.id] = amount
        show_balance_payment_screen(query, context, amount)

def balance_request_confirm(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id not in pending_balance_requests or user_id not in pending_balance_receipts:
        query.edit_message_text("❌ لطفاً ابتدا عکس رسید پرداخت خود را ارسال کنید.")
        return
    amount = pending_balance_requests[user_id]
    photo_file_id = pending_balance_receipts[user_id]
    for admin in admin_ids:
        try:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تایید", callback_data=f"approve_balance_{user_id}_{amount}"),
                                               InlineKeyboardButton("❌ رد", callback_data=f"reject_balance_{user_id}_{amount}")]])
            context.bot.send_photo(chat_id=admin, photo=photo_file_id,
                                     caption=f"درخواست افزایش موجودی از کاربر {user_id}:\nمبلغ: {amount:,} تومان",
                                     parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"خطا در ارسال رسید افزایش موجودی به ادمین {admin}: {e}")
    query.edit_message_text("✅ درخواست افزایش موجودی شما ارسال شد و در انتظار تایید ادمین می‌باشد.")

def approve_balance(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 4:
        if query.message.photo:
            query.edit_message_caption(caption="❌ داده‌های نامعتبر.")
        else:
            query.edit_message_text("❌ داده‌های نامعتبر.")
        return
    try:
        user_id = int(parts[2])
        amount = int(parts[3])
    except Exception:
        if query.message.photo:
            query.edit_message_caption(caption="❌ خطا در پردازش اطلاعات.")
        else:
            query.edit_message_text("❌ خطا در پردازش اطلاعات.")
        return
    user_balance[user_id] = user_balance.get(user_id, 0) + amount
    save_balance()
    if user_id in pending_balance_requests:
        del pending_balance_requests[user_id]
    if user_id in pending_balance_receipts:
        del pending_balance_receipts[user_id]
    if query.message.photo:
        query.edit_message_caption(caption="✅ درخواست افزایش موجودی تایید شد. موجودی کاربر به حساب اضافه شد.")
    else:
        query.edit_message_text("✅ درخواست افزایش موجودی تایید شد. موجودی کاربر به حساب اضافه شد.")
    try:
        context.bot.send_message(chat_id=user_id, text="✅ درخواست افزایش موجودی شما تایید شد. موجودی به حساب شما اضافه شد.")
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")

def reject_balance(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 4:
        if query.message.photo:
            query.edit_message_caption(caption="❌ داده‌های نامعتبر.")
        else:
            query.edit_message_text("❌ داده‌های نامعتبر.")
        return
    try:
        user_id = int(parts[2])
        amount = int(parts[3])
    except Exception:
        if query.message.photo:
            query.edit_message_caption(caption="❌ خطا در پردازش اطلاعات.")
        else:
            query.edit_message_text("❌ خطا در پردازش اطلاعات.")
        return
    if user_id in pending_balance_requests:
        del pending_balance_requests[user_id]
    if user_id in pending_balance_receipts:
        del pending_balance_receipts[user_id]
    if query.message.photo:
        query.edit_message_caption(caption="✅ درخواست افزایش موجودی رد شد.")
    else:
        query.edit_message_text("✅ درخواست افزایش موجودی رد شد.")
    try:
        context.bot.send_message(chat_id=user_id, text="❌ درخواست افزایش موجودی شما رد شد.")
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")

# ------------------ بخش حساب کاربری ------------------
def account_menu(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    balance = user_balance.get(user_id, 0)
    points = referral_points.get(user_id, 0)
    text = (
        f"👤 حساب کاربری شما:\n\n"
        f"🆔 آیدی: {user_id}\n"
        f"💰 موجودی: {balance:,} تومان\n"
        f"⭐ امتیاز معرف: {points}\n\n"
    )
    history = purchase_history.get(user_id, [])
    if history:
        text += f"✅ تعداد خریدهای موفق: {len(history)}\n\nآخرین خریدها:\n"
        for rec in history[-3:]:
            if isinstance(rec.get("timestamp"), datetime.datetime):
                ts = rec["timestamp"].strftime("%Y-%m-%d %H:%M")
            else:
                ts = rec.get("timestamp", "N/A")
            plan_name = DNS_CONFIGS.get(rec.get("plan"), {}).get("name", rec.get("plan"))
            text += f"• {plan_name} - {rec.get('cost',0):,} تومان - {ts}\n"
            text += f"  IPv4: <code>{rec.get('ip1','N/A')}</code>, <code>{rec.get('ip2','N/A')}</code>\n"
            text += f"  IPv6: <code>{rec.get('ipv6_1','N/A')}</code>, <code>{rec.get('ipv6_2','N/A')}</code>\n"
            if rec.get("discount"):
                text += f"  تخفیف: {rec['discount']}\n"
            text += "\n"
    else:
        text += "❌ خریدی ثبت نشده است.\n"
    if user_id in user_discount:
        code, percent = user_discount[user_id]
        text += f"\n🎟 کد تخفیف موجود: {code} - {percent}% تخفیف\n"
    keyboard = [
        [InlineKeyboardButton("🎟 اعمال کد تخفیف", callback_data="apply_discount")],
        [InlineKeyboardButton("💰 تبدیل امتیاز به موجودی", callback_data="convert_referral")],
        [InlineKeyboardButton("🔗 رفرال و امتیاز", callback_data="referral_menu")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

# ------------------ منوی رفرال ------------------
def referral_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    points = referral_points.get(user_id, 0)
    referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    text = (
        f"🔗 اطلاعات رفرال:\n\n"
        f"⭐ امتیاز فعلی: {points}\n"
        f"🔗 لینک معرف: {referral_link}\n\n"
        "هر کاربر جدیدی که با استفاده از لینک معرف وارد ربات شود، به شما 1 امتیاز تعلق می‌گیرد.\n"
        "همچنین می‌توانید امتیازهای خود را با نرخ 1 امتیاز = 1000 تومان به موجودی تبدیل کنید."
    )
    keyboard = [
        [InlineKeyboardButton("💰 تبدیل امتیاز به موجودی", callback_data="convert_referral")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")],
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ------------------ منوی پشتیبانی ------------------
def support_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    text = (
        "📞 اطلاعات پشتیبانی:\n\n"
        "- شماره تماس: 09123456789\n"
        f"- تلگرام: {SUPPORT_ID}\n\n"
        "در صورت نیاز به راهنمایی و پشتیبانی با ما تماس بگیرید."
    )
    keyboard = [[InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")]]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ------------------ بخش اعمال کد تخفیف ------------------
def apply_discount_prompt(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    awaiting_discount_code[query.from_user.id] = True
    query.edit_message_text("✏️ لطفاً کد تخفیف خود را ارسال کنید:")

def handle_discount_code_text(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    if code in discount_codes:
        user_discount[user_id] = (code, discount_codes[code])
        update.message.reply_text(f"✅ کد تخفیف {code} با {discount_codes[code]}% تخفیف اعمال شد.")
    else:
        update.message.reply_text("❌ کد تخفیف نامعتبر است.")
    if user_id in awaiting_discount_code:
        del awaiting_discount_code[user_id]

# ------------------ پنل ادمین ------------------
def admin_panel_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    text = "⚙️ پنل ادمین:"
    keyboard = [
        [InlineKeyboardButton("💰 مدیریت افزایش موجودی", callback_data="admin_pending_balance"),
         InlineKeyboardButton("💸 تغییر موجودی کاربر", callback_data="admin_modify_balance")],
        [InlineKeyboardButton("🚫 مسدودسازی کاربر", callback_data="admin_block_user"),
         InlineKeyboardButton("✅ لغو مسدودسازی کاربر", callback_data="admin_unblock_user")],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_mass_message")],
        [InlineKeyboardButton("🔒 جویین اجباری کانال", callback_data="admin_toggle_force_join"),
         InlineKeyboardButton("📝 تنظیم کانال اجباری", callback_data="admin_set_force_channel")],
        [InlineKeyboardButton("⚙️ تنظیم دکمه‌ها", callback_data="admin_toggle_buttons_menu"),
         InlineKeyboardButton("📝 ویرایش قوانین", callback_data="admin_edit_terms")],
        [InlineKeyboardButton("💸 تغییر قیمت دکمه‌ها", callback_data="admin_change_button_prices")],
        [InlineKeyboardButton("📊 آمار و لیست کاربران", callback_data="admin_user_stats")],
        [InlineKeyboardButton("📝 تغییر آیدی پشتیبانی", callback_data="admin_change_support")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="toggle_update_mode")],
        [InlineKeyboardButton("🌟 دکمه جدید", callback_data="new_admin_button")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)

def toggle_update_mode(update: Update, context: CallbackContext) -> None:
    global BOT_UPDATING
    query = update.callback_query
    query.answer()
    BOT_UPDATING = not BOT_UPDATING
    status = "فعال" if BOT_UPDATING else "غیرفعال"
    query.edit_message_text(f"حالت بروزرسانی در ربات اکنون {status} است.")

def admin_pending_balance(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    if not pending_balance_requests:
        text = "هیچ درخواست افزایش موجودی در انتظار تایید وجود ندارد."
    else:
        text = "درخواست‌های افزایش موجودی در انتظار تایید:\n"
        for uid, amount in pending_balance_requests.items():
            text += f"کاربر {uid}: {amount:,} تومان\n"
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)

def admin_change_button_prices_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    text = "💸 تغییر قیمت دکمه‌ها:\nلطفاً یکی از موارد زیر را انتخاب کنید:"
    buttons = []
    for plan_id, config in DNS_CONFIGS.items():
        buttons.append(
            InlineKeyboardButton(
                f"DNS ({config['name']}) - {config['price']:,} تومان",
                callback_data=f"change_price_dns_{plan_id}",
            )
        )
    buttons.append(
        InlineKeyboardButton(
            f"وایرگارد - {WIREGUARD_PRICE:,} تومان",
            callback_data="change_price_wireguard_default",
        )
    )
    for plan_key, plan_info in SITE_SUBSCRIPTION_PLANS.items():
        buttons.append(
            InlineKeyboardButton(
                f"اشتراک {plan_info['name']} - {plan_info['price']:,} تومان",
                callback_data=f"change_price_site_{plan_key}",
            )
        )
    buttons.append(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_menu"))
    reply_markup = InlineKeyboardMarkup(InlineKeyboardMarkup([[b] for b in buttons]).inline_keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)

def admin_change_button_price_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 3:
        query.edit_message_text("❌ داده‌های نامعتبر.")
        return
    product_type = parts[2]
    product_key = parts[3] if len(parts) >= 4 else "default"
    admin_state[query.from_user.id] = {
        "operation": "change_button_price",
        "product_type": product_type,
        "product_key": product_key,
    }
    query.edit_message_text("✏️ لطفاً قیمت جدید (به تومان) را وارد کنید:")

def admin_user_stats(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    lines = []
    total_users = len(all_users)
    total_purchases = sum(len(purchase_history.get(uid, [])) for uid in all_users)
    lines.append(f"کل کاربران: {total_users} | کل خریدها: {total_purchases}")
    lines.append("------------------------------------------------")
    for uid in all_users:
        try:
            chat = context.bot.get_chat(uid)
            username = chat.username if chat.username else "-"
        except Exception:
            username = "-"
        ref_points = referral_points.get(uid, 0)
        purchase_count = len(purchase_history.get(uid, []))
        balance_val = user_balance.get(uid, 0)
        lines.append(f"آیدی: {uid} | یوزرنیم: {username} | امتیاز: {ref_points} | خرید: {purchase_count} | موجودی: {balance_val:,} تومان")
    file_data = "\n".join(lines)
    bio = io.BytesIO(file_data.encode("utf-8"))
    bio.name = "user_stats.txt"
    query.edit_message_text("در حال ارسال فایل آمار کاربران...")
    context.bot.send_document(chat_id=query.from_user.id, document=bio, filename="user_stats.txt", caption="آمار کاربران")

def admin_modify_balance_prompt(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "modify_balance", "step": "awaiting_user_id"}
    query.edit_message_text("✏️ لطفاً آیدی کاربر مورد نظر را (به صورت عددی) ارسال کنید.\nبرای انصراف، /cancel را بزنید.")

def admin_block_user(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "block_user"}
    query.edit_message_text("🚫 لطفاً آیدی کاربر مورد نظر برای مسدودسازی را ارسال کنید.")

def admin_unblock_user(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "unblock_user"}
    query.edit_message_text("✅ لطفاً آیدی کاربر مورد نظر برای لغو مسدودسازی را ارسال کنید.")

def admin_mass_message(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "mass_message"}
    query.edit_message_text("📢 لطفاً متن پیام همگانی را ارسال کنید.")

def admin_toggle_force_join(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    global FORCE_JOIN_ENABLED
    FORCE_JOIN_ENABLED = not FORCE_JOIN_ENABLED
    status = "فعال" if FORCE_JOIN_ENABLED else "غیرفعال"
    query.edit_message_text(f"🔒 وضعیت جویین اجباری کانال به {status} تغییر یافت.")

def admin_set_force_channel(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "set_force_channel"}
    query.edit_message_text("📝 لطفاً پیام فوروارد شده از کانال یا آیدی عمومی کانال (مثلاً @amir) را ارسال کنید:")

def admin_toggle_buttons_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    text = "⚙️ تنظیم دکمه‌های منوی اصلی:\n"
    text += f"🛒 خرید DNS اختصاصی: {'فعال' if ENABLE_DNS_BUTTON else 'غیرفعال'}\n"
    text += f"👤 حساب کاربری: {'فعال' if ENABLE_ACCOUNT_BUTTON else 'غیرفعال'}\n"
    text += f"💳 افزایش موجودی: {'فعال' if ENABLE_BALANCE_BUTTON else 'غیرفعال'}\n"
    text += f"🔗 رفرال و امتیاز: {'فعال' if ENABLE_REFERRAL_BUTTON else 'غیرفعال'}\n"
    text += f"🔑 وایرگارد اختصاصی: {'فعال' if ENABLE_WIREGUARD_BUTTON else 'غیرفعال'}\n"
    text += f"💻 خرید یوزرپسورد سایت: {'فعال' if ENABLE_SITE_SUBSCRIPTION_BUTTON else 'غیرفعال'}\n"
    keyboard = [
        [InlineKeyboardButton("🔄 تغییر وضعیت خرید DNS", callback_data="toggle_dns")],
        [InlineKeyboardButton("🔄 تغییر وضعیت حساب کاربری", callback_data="toggle_account")],
        [InlineKeyboardButton("🔄 تغییر وضعیت افزایش موجودی", callback_data="toggle_balance")],
        [InlineKeyboardButton("🔄 تغییر وضعیت رفرال", callback_data="toggle_referral")],
        [InlineKeyboardButton("🔄 تغییر وضعیت وایرگارد", callback_data="toggle_wireguard")],
        [InlineKeyboardButton("🔄 تغییر وضعیت خرید سایت", callback_data="toggle_site_subscription")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)

def toggle_dns(update: Update, context: CallbackContext) -> None:
    global ENABLE_DNS_BUTTON
    ENABLE_DNS_BUTTON = not ENABLE_DNS_BUTTON
    admin_toggle_buttons_menu(update, context)

def toggle_account(update: Update, context: CallbackContext) -> None:
    global ENABLE_ACCOUNT_BUTTON
    ENABLE_ACCOUNT_BUTTON = not ENABLE_ACCOUNT_BUTTON
    admin_toggle_buttons_menu(update, context)

def toggle_balance(update: Update, context: CallbackContext) -> None:
    global ENABLE_BALANCE_BUTTON
    ENABLE_BALANCE_BUTTON = not ENABLE_BALANCE_BUTTON
    admin_toggle_buttons_menu(update, context)

def toggle_referral(update: Update, context: CallbackContext) -> None:
    global ENABLE_REFERRAL_BUTTON
    ENABLE_REFERRAL_BUTTON = not ENABLE_REFERRAL_BUTTON
    admin_toggle_buttons_menu(update, context)

def toggle_wireguard(update: Update, context: CallbackContext) -> None:
    global ENABLE_WIREGUARD_BUTTON
    ENABLE_WIREGUARD_BUTTON = not ENABLE_WIREGUARD_BUTTON
    admin_toggle_buttons_menu(update, context)

def toggle_site_subscription(update: Update, context: CallbackContext) -> None:
    global ENABLE_SITE_SUBSCRIPTION_BUTTON
    ENABLE_SITE_SUBSCRIPTION_BUTTON = not ENABLE_SITE_SUBSCRIPTION_BUTTON
    admin_toggle_buttons_menu(update, context)

def admin_edit_terms(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "update_terms"}
    query.edit_message_text("✏️ لطفاً متن جدید قوانین و مقررات را ارسال کنید:")

def new_admin_button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    query.edit_message_text("این دکمه جدید از پنل ادمین است.")

def admin_change_support(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_state[query.from_user.id] = {"operation": "change_support"}
    query.edit_message_text("✏️ لطفاً آیدی پشتیبانی جدید (به عنوان مثال: @NewSupportID) را ارسال کنید:")

def admin_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        if context.args and context.args[0] == ADMIN_PASSWORD:
            admin_ids.add(user_id)
            update.message.reply_text("✅ شما به عنوان ادمین ثبت شدید.")
        else:
            update.message.reply_text("❌ دسترسی غیرمجاز. برای ورود رمز عبور را همراه /admin ارسال کنید. مثال: /admin 1")
            return
    keyboard = [[InlineKeyboardButton("⚙️ پنل ادمین", callback_data="admin_panel_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("به پنل ادمین خوش آمدید.", reply_markup=reply_markup)

def admin_cancel(update: Update, context: CallbackContext) -> None:
    admin_id = update.effective_user.id
    if admin_id in admin_state:
        del admin_state[admin_id]
        update.message.reply_text("❌ عملیات لغو شد.")

def convert_referral(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    points = referral_points.get(user_id, 0)
    if points > 0:
        credit = points * 1000
        user_balance[user_id] = user_balance.get(user_id, 0) + credit
        save_balance()
        referral_points[user_id] = 0
        query.edit_message_text(f"✅ {points} امتیاز به مبلغ {credit:,} تومان به موجودی شما اضافه شد.")
    else:
        query.edit_message_text("❌ امتیاز کافی برای تبدیل موجودی ندارید.")

# ------------------ هندلر پیام‌های متنی (text_message_handler) ------------------
def text_message_handler(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if user_id in awaiting_custom_balance:
        try:
            amount = int(text)
            if amount < 10000 or amount > 1000000:
                update.message.reply_text("❌ مقدار انتخاب شده خارج از محدوده مجاز است.")
                return
            pending_balance_requests[user_id] = amount
            del awaiting_custom_balance[user_id]
            payment_text = (
                f"برای افزایش موجودی به مبلغ {amount:,} تومان، مبلغ را به حساب بانکی واریز کنید.\n\n"
                "💳 شماره کارت: <code>6219 8619 4308 4037</code>\n"
                "به نام: امیرحسین سیاهبالایی\n\n"
                "سپس رسید پرداخت را به صورت عکس ارسال کنید و روی دکمه '💳 ارسال درخواست افزایش موجودی' کلیک کنید."
            )
            keyboard = [
                [InlineKeyboardButton("💳 ارسال درخواست افزایش موجودی", callback_data="balance_request_confirm")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(payment_text, reply_markup=reply_markup, parse_mode="HTML")
        except ValueError:
            update.message.reply_text("❌ مقدار وارد شده معتبر نیست.")
        return

    if user_id in admin_state:
        state = admin_state[user_id]
        operation = state.get("operation")
        if operation == "modify_balance":
            if state.get("step") == "awaiting_user_id":
                try:
                    target_user = int(text)
                    admin_state[user_id]["target_user"] = target_user
                    admin_state[user_id]["step"] = "awaiting_amount"
                    update.message.reply_text("✏️ لطفاً مبلغ تغییر موجودی (مثبت یا منفی) را وارد کنید:")
                except ValueError:
                    update.message.reply_text("❌ آیدی معتبر نیست. لطفاً عدد وارد کنید.")
            elif state.get("step") == "awaiting_amount":
                try:
                    amount = int(text)
                    target_user = admin_state[user_id].get("target_user")
                    if target_user is None:
                        update.message.reply_text("❌ خطا در دریافت آیدی کاربر.")
                        del admin_state[user_id]
                        return
                    user_balance[target_user] = user_balance.get(target_user, 0) + amount
                    save_balance()
                    update.message.reply_text(f"✅ موجودی کاربر {target_user} تغییر یافت. مبلغ تغییر: {amount:,} تومان")
                    del admin_state[user_id]
                except ValueError:
                    update.message.reply_text("❌ مقدار وارد شده معتبر نیست. لطفاً عدد وارد کنید.")
            return

        elif operation == "block_user":
            try:
                target_user = int(text)
                blocked_users.add(target_user)
                update.message.reply_text(f"🚫 کاربر {target_user} مسدود شد.")
                del admin_state[user_id]
            except ValueError:
                update.message.reply_text("❌ آیدی معتبر نیست.")
            return

        elif operation == "unblock_user":
            try:
                target_user = int(text)
                if target_user in blocked_users:
                    blocked_users.remove(target_user)
                    update.message.reply_text(f"✅ کاربر {target_user} از لیست مسدود شده‌ها حذف شد.")
                else:
                    update.message.reply_text("❌ این کاربر مسدود نیست.")
                del admin_state[user_id]
            except ValueError:
                update.message.reply_text("❌ آیدی معتبر نیست.")
            return

        elif operation == "mass_message":
            message_text = text
            count = 0
            for uid in all_users:
                try:
                    context.bot.send_message(chat_id=uid, text=message_text)
                    count += 1
                except Exception as e:
                    logger.error(f"Error sending mass message to {uid}: {e}")
            update.message.reply_text(f"✅ پیام همگانی ارسال شد به {count} کاربر.")
            del admin_state[user_id]
            return

        elif operation == "set_force_channel":
            global FORCE_JOIN_CHANNEL
            FORCE_JOIN_CHANNEL = text
            update.message.reply_text(f"✅ کانال اجباری تنظیم شد: {FORCE_JOIN_CHANNEL}")
            del admin_state[user_id]
            return

        elif operation == "update_terms":
            global TERMS_TEXT
            TERMS_TEXT = text
            update.message.reply_text("✅ قوانین و مقررات به‌روزرسانی شد.")
            del admin_state[user_id]
            return

        elif operation == "change_button_price":
            try:
                new_price = int(text)
                product_type = state.get("product_type")
                product_key = state.get("product_key")
                if product_type == "dns":
                    if product_key in DNS_CONFIGS:
                        DNS_CONFIGS[product_key]["price"] = new_price
                        update.message.reply_text(f"✅ قیمت DNS ({DNS_CONFIGS[product_key]['name']}) به {new_price:,} تومان تغییر یافت.")
                    else:
                        update.message.reply_text("❌ پلن DNS نامعتبر.")
                elif product_type == "wireguard":
                    global WIREGUARD_PRICE
                    WIREGUARD_PRICE = new_price
                    update.message.reply_text(f"✅ قیمت وایرگارد به {new_price:,} تومان تغییر یافت.")
                elif product_type == "site":
                    if product_key in SITE_SUBSCRIPTION_PLANS:
                        SITE_SUBSCRIPTION_PLANS[product_key]["price"] = new_price
                        update.message.reply_text(f"✅ قیمت اشتراک {SITE_SUBSCRIPTION_PLANS[product_key]['name']} به {new_price:,} تومان تغییر یافت.")
                    else:
                        update.message.reply_text("❌ پلن اشتراک نامعتبر.")
                else:
                    update.message.reply_text("❌ نوع محصول نامعتبر.")
                del admin_state[user_id]
            except ValueError:
                update.message.reply_text("❌ مقدار وارد شده معتبر نیست. لطفاً عدد وارد کنید.")
            return

        elif operation == "change_support":
            global SUPPORT_ID
            SUPPORT_ID = text.strip()
            update.message.reply_text(f"✅ آیدی پشتیبانی به {SUPPORT_ID} تغییر یافت.")
            del admin_state[user_id]
            return

    if user_id in awaiting_discount_code:
        handle_discount_code_text(update, context)
        return

    update.message.reply_text("❌ دستور نامعتبر یا موردی جهت پردازش یافت نشد.")

# ------------------ ثبت هندلرها ------------------
def main() -> None:
    TOKEN = "7487680597:AAG-D9C8jlqQ4se4yV9ozxIOx9Z1bVGDfBk"  # جایگزین کنید با توکن واقعی ربات شما
    load_balance()
    load_history()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("admin", admin_command))
    dp.add_handler(CommandHandler("cancel", admin_cancel))
    dp.add_handler(CommandHandler("account", account_menu))

    dp.add_handler(CallbackQueryHandler(show_main_menu, pattern="^main_menu$"))
    dp.add_handler(CallbackQueryHandler(dns_menu, pattern="^dns_menu$"))
    dp.add_handler(CallbackQueryHandler(buy_dns_plan, pattern="^buy_dnsplan_.*"))
    dp.add_handler(CallbackQueryHandler(account_menu, pattern="^account_menu$"))
    dp.add_handler(CallbackQueryHandler(balance_increase_menu, pattern="^balance_increase$"))
    dp.add_handler(CallbackQueryHandler(ask_custom_balance, pattern="^balance_increase_custom$"))
    dp.add_handler(CallbackQueryHandler(handle_balance_increase_request, pattern="^balance_increase_.*"))
    dp.add_handler(CallbackQueryHandler(balance_request_confirm, pattern="^balance_request_confirm$"))
    dp.add_handler(CallbackQueryHandler(confirm_receipt, pattern="^confirm_receipt$"))
    dp.add_handler(CallbackQueryHandler(admin_approve_purchase, pattern="^admin_approve_purchase_.*"))
    dp.add_handler(CallbackQueryHandler(admin_reject_purchase, pattern="^admin_reject_purchase_.*"))
    dp.add_handler(CallbackQueryHandler(approve_balance, pattern="^approve_balance_.*"))
    dp.add_handler(CallbackQueryHandler(reject_balance, pattern="^reject_balance_.*"))
    dp.add_handler(CallbackQueryHandler(admin_panel_menu, pattern="^admin_panel_menu$"))
    dp.add_handler(CallbackQueryHandler(admin_pending_balance, pattern="^admin_pending_balance$"))
    dp.add_handler(CallbackQueryHandler(apply_discount_prompt, pattern="^apply_discount$"))
    dp.add_handler(CallbackQueryHandler(admin_modify_balance_prompt, pattern="^admin_modify_balance$"))
    dp.add_handler(CallbackQueryHandler(convert_referral, pattern="^convert_referral$"))
    dp.add_handler(CallbackQueryHandler(admin_block_user, pattern="^admin_block_user$"))
    dp.add_handler(CallbackQueryHandler(admin_unblock_user, pattern="^admin_unblock_user$"))
    dp.add_handler(CallbackQueryHandler(admin_mass_message, pattern="^admin_mass_message$"))
    dp.add_handler(CallbackQueryHandler(admin_toggle_force_join, pattern="^admin_toggle_force_join$"))
    dp.add_handler(CallbackQueryHandler(admin_set_force_channel, pattern="^admin_set_force_channel$"))
    dp.add_handler(CallbackQueryHandler(referral_menu, pattern="^referral_menu$"))
    dp.add_handler(CallbackQueryHandler(wireguard_menu, pattern="^wireguard_menu$"))
    dp.add_handler(CallbackQueryHandler(admin_toggle_buttons_menu, pattern="^admin_toggle_buttons_menu$"))
    dp.add_handler(CallbackQueryHandler(toggle_dns, pattern="^toggle_dns$"))
    dp.add_handler(CallbackQueryHandler(toggle_account, pattern="^toggle_account$"))
    dp.add_handler(CallbackQueryHandler(toggle_balance, pattern="^toggle_balance$"))
    dp.add_handler(CallbackQueryHandler(toggle_referral, pattern="^toggle_referral$"))
    dp.add_handler(CallbackQueryHandler(toggle_wireguard, pattern="^toggle_wireguard$"))
    dp.add_handler(CallbackQueryHandler(toggle_site_subscription, pattern="^toggle_site_subscription$"))
    dp.add_handler(CallbackQueryHandler(admin_edit_terms, pattern="^admin_edit_terms$"))
    dp.add_handler(CallbackQueryHandler(new_admin_button_handler, pattern="^new_admin_button$"))
    dp.add_handler(CallbackQueryHandler(admin_change_button_prices_menu, pattern="^admin_change_button_prices$"))
    dp.add_handler(CallbackQueryHandler(admin_change_button_price_handler, pattern="^change_price_.*"))
    dp.add_handler(CallbackQueryHandler(admin_user_stats, pattern="^admin_user_stats$"))
    dp.add_handler(CallbackQueryHandler(support_menu, pattern="^support_menu$"))
    dp.add_handler(CallbackQueryHandler(terms_and_conditions, pattern="^terms$"))
    dp.add_handler(CallbackQueryHandler(site_subscription_menu, pattern="^site_subscription_menu$"))
    dp.add_handler(CallbackQueryHandler(buy_site_subscription, pattern="^buy_site_subscription_.*"))
    dp.add_handler(CallbackQueryHandler(toggle_update_mode, pattern="^toggle_update_mode$"))
    dp.add_handler(CallbackQueryHandler(admin_change_support, pattern="^admin_change_support$"))

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_message_handler))
    dp.add_handler(MessageHandler(Filters.photo, receipt_photo_handler))

    updater.start_polling()
    logger.info("✅ Bot has deployed successfully.")
    updater.idle()

if __name__ == "__main__":
    main()
