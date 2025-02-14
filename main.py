import logging
import datetime
import random
import ipaddress
import pickle
import os
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
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

# اطلاعات ادمین ثابت
admin_ids = {7240662021}
ADMIN_PASSWORD = "1"

# موجودی کاربران (به تومان)
user_balance = {}  # ساختار: {user_id: amount}

# تاریخچه خریدهای تایید شده
purchase_history = (
    {}
)  # ساختار: { user_id: [ {type, plan, ip1, ip2, ipv6_1, ipv6_2, cost, discount, timestamp}, ... ] }

# خریدهایی که منتظر ارسال رسید هستند (برای خرید DNS)
pending_receipts = {}  # ساختار: { user_id: { ... } }

# ذخیره عکس رسید خرید DNS
receipt_photos = {}

# درخواست‌های افزایش موجودی (بدون کسر موجودی تا تایید ادمین)
pending_balance_requests = {}  # ساختار: { user_id: amount }

# ذخیره عکس رسید افزایش موجودی
pending_balance_receipts = {}

# دیکشنری برای پیگیری عملیات ادمین (مثلاً تغییر موجودی، مسدودسازی، پیام همگانی، تنظیم کانال)
admin_state = {}

# پلن‌های DNS اختصاصی (لوکیشن‌بندی شده)
DNS_CONFIGS = {
    "امارات": {
        "name": "DNS سرور امارات",
        "price": 30000,
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
    },
    "ترکیه": {
        "name": "DNS سرور ترکیه",
        "price": 40000,
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
    },
    "آلمان1": {
        "name": "DNS سرور آلمان 1",
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
    },
}

# برای دریافت مبلغ دلخواه افزایش موجودی
awaiting_custom_balance = {}

# ------------------ متغیرهای کد تخفیف ------------------
discount_codes = {"OFF10": 10, "OFF20": 20, "OFF30": 30}
user_discount = {}
awaiting_discount_code = {}

# ------------------ متغیرهای جدید برای سیستم زیرمجموعه، مسدودسازی، پیام همگانی و جویین اجباری ------------------
blocked_users = set()  # آی‌دی‌های مسدود شده
referral_points = {}  # ساختار: { user_id: points }
referred_users = set()  # کاربرانی که به عنوان زیرمجموعه ثبت شده‌اند
all_users = set()  # لیست همه کاربران
BOT_USERNAME = "amir_xknow_bot"  # نام ربات برای لینک رفرال
FORCE_JOIN_CHANNEL = None  # کانال جویین اجباری (به صورت @channel)
FORCE_JOIN_ENABLED = False  # وضعیت فعال بودن جویین اجباری

# ------------------ توابع کاربردی ------------------


def generate_dns_ip_pair(plan_id: str):
    """تولید جفت IP از رنج‌های CIDR پلن DNS اختصاصی"""
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


def generate_dns_ipv6_pair():
    """تولید جفت IPv6 به فرمت 0000:****:****::1 و 0000:****:****::0"""
    seg2 = "".join(random.choices("0123456789abcdef", k=4))
    seg3 = "".join(random.choices("0123456789abcdef", k=4))
    ipv6_1 = f"0000:{seg2}:{seg3}::1"
    ipv6_2 = f"0000:{seg2}:{seg3}::0"
    return ipv6_1, ipv6_2


# ------------------ منوهای اصلی ------------------


def show_main_menu(update: Update, context: CallbackContext) -> None:
    """نمایش منوی اصلی"""
    text = "🏠 منوی اصلی:"
    keyboard = [
        [InlineKeyboardButton("🛒 خرید DNS اختصاصی", callback_data="dns_menu")],
        [InlineKeyboardButton("👤 حساب کاربری", callback_data="account_menu")],
        [InlineKeyboardButton("💳 افزایش موجودی", callback_data="balance_increase")],
    ]
    user_id = update.effective_user.id
    if user_id in admin_ids:
        keyboard.append(
            [InlineKeyboardButton("⚙️ پنل ادمین", callback_data="admin_panel_menu")]
        )
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        update.message.reply_text(text, reply_markup=reply_markup)


def start(update: Update, context: CallbackContext) -> None:
    """دستور /start با بررسی جویین اجباری و زیرمجموعه گیری"""
    user = update.effective_user
    user_id = user.id

    if user_id in blocked_users:
        update.message.reply_text("❌ شما توسط مدیریت مسدود شده‌اید.")
        return

    all_users.add(user_id)

    if FORCE_JOIN_ENABLED and FORCE_JOIN_CHANNEL:
        try:
            member = context.bot.get_chat_member(FORCE_JOIN_CHANNEL, user_id)
            if member.status not in ["member", "creator", "administrator"]:
                update.message.reply_text(
                    f"❌ لطفاً ابتدا در کانال {FORCE_JOIN_CHANNEL} عضو شوید."
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
    """نمایش منوی خرید DNS اختصاصی بر اساس لوکیشن"""
    query = update.callback_query
    query.answer()
    query.edit_message_text(
        "لطفاً لوکیشن DNS اختصاصی را انتخاب کنید:",
        reply_markup=build_dns_selection_menu(),
    )


def build_dns_selection_menu():
    """ساخت منوی انتخاب پلن DNS اختصاصی (لوکیشن)"""
    keyboard = []
    for plan_id, config in DNS_CONFIGS.items():
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{config['flag']} {config['name']} - {config['price']:,} تومان",
                    callback_data=f"buy_dnsplan_{plan_id}",
                )
            ]
        )
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def buy_dns_plan(update: Update, context: CallbackContext) -> None:
    """
    پردازش خودکار خرید DNS اختصاصی از موجودی کاربر بدون نیاز به تایید ادمین.
    پس از بررسی موجودی و کسر آن، ابتدا پیام "⏳ در حال پردازش" ارسال شده و سپس
    مشخصات سرور (IPv4 و IPv6) به همراه پیام "😊 موجودی شما کافی است!" به کاربر ارسال می‌شود.
    """
    query = update.callback_query
    query.answer()
    data = query.data  # مانند: buy_dnsplan_ترکیه
    parts = data.split("_")
    if len(parts) < 3:
        query.edit_message_text("❌ خطا در ثبت خرید DNS.")
        return

    plan_id = parts[2]
    user_id = query.from_user.id
    base_cost = DNS_CONFIGS[plan_id]["price"]

    # اعمال تخفیف در صورت وجود
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
        query.edit_message_text(
            "❌ موجودی شما کافی نیست. لطفاً ابتدا موجودی خود را افزایش دهید."
        )
        return

    # کسر موجودی و ذخیره
    user_balance[user_id] = balance - final_cost
    save_balance()

    # ارسال پیام در حال پردازش
    query.edit_message_text("⏳ در حال پردازش، لطفاً کمی صبر کنید...")
    time.sleep(1)  # شبیه‌سازی تأخیر پردازش

    # تولید آی‌پی‌های اختصاصی
    ip1, ip2 = generate_dns_ip_pair(plan_id)
    if not ip1 or not ip2:
        query.edit_message_text("❌ خطا در تولید آی‌پی‌ها. لطفاً دوباره تلاش کنید.")
        return

    # تولید آی‌پی‌های IPv6
    ipv6_1, ipv6_2 = generate_dns_ipv6_pair()
    dns_caption = (
        "⚠️ حتماً از دی‌ان‌اس‌های الکترو:\n"
        "<code>78.157.42.100\n78.157.42.101</code>\n"
        "یا رادار:\n"
        "<code>10.202.10.10\n10.202.10.11</code>\n\n"
    )
    final_text = (
        f"😊 موجودی شما کافی است!\n\n"
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
    # ثبت خرید در تاریخچه (در صورت نیاز به ثبت در تاریخچه، می‌توانید آن را ذخیره کنید)
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


# ------------------ دریافت رسید پرداخت (عکس) ------------------


def receipt_photo_handler(update: Update, context: CallbackContext) -> None:
    """
    دریافت عکس رسید پرداخت.
    اگر کاربر درخواست افزایش موجودی داشته باشد، عکس به عنوان رسید افزایش موجودی ثبت می‌شود؛
    در غیر این صورت، اگر خرید DNS در انتظار باشد، عکس به عنوان رسید خرید ثبت می‌شود.
    """
    user_id = update.effective_user.id
    if user_id in pending_balance_requests:
        pending_balance_receipts[user_id] = update.message.photo[-1].file_id
        keyboard = [
            [
                InlineKeyboardButton(
                    "💳 ارسال درخواست افزایش موجودی",
                    callback_data="balance_request_confirm",
                )
            ]
        ]
        update.message.reply_text(
            "✅ عکس رسید دریافت شد. برای نهایی کردن درخواست افزایش موجودی روی دکمه مربوطه کلیک کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif user_id in pending_receipts:
        receipt_photos[user_id] = update.message.photo[-1].file_id
        keyboard = [
            [InlineKeyboardButton("قبول درخواست", callback_data="confirm_receipt")]
        ]
        update.message.reply_text(
            "✅ عکس رسید دریافت شد. برای نهایی کردن خرید روی دکمه 'قبول درخواست' کلیک کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def confirm_receipt(update: Update, context: CallbackContext) -> None:
    """
    پس از کلیک روی دکمه «قبول درخواست»، عکس رسید و اطلاعات خرید به ادمین ارسال می‌شود.
    """
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if user_id not in pending_receipts or user_id not in receipt_photos:
        query.edit_message_text(
            "❌ رسید شما یافت نشد. لطفاً ابتدا عکس رسید را ارسال کنید."
        )
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
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ تایید خرید",
                            callback_data=f"admin_approve_purchase_{user_id}",
                        ),
                        InlineKeyboardButton(
                            "❌ رد خرید",
                            callback_data=f"admin_reject_purchase_{user_id}",
                        ),
                    ]
                ]
            )
            context.bot.send_photo(
                chat_id=admin,
                photo=photo_file_id,
                caption=f"رسید پرداخت از کاربر {user_id}:\n{caption}",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"خطا در ارسال رسید به ادمین {admin}: {e}")
    query.edit_message_text("✅ رسید شما ارسال شد و در انتظار تایید ادمین می‌باشد.")


# ------------------ تایید/رد خرید توسط ادمین ------------------
# (در این نسخه اگرچه خرید به صورت خودکار انجام می‌شود، این توابع برای سایر موارد در سیستم باقی مانده‌اند)


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
        context.bot.send_message(
            chat_id=user_id,
            text="❌ خرید شما توسط ادمین رد شد. مبلغ کسر شده به حساب شما بازگردانده شد.",
        )
    except Exception as e:
        logger.error(f"خطا در ارسال پیام به کاربر {user_id}: {e}")
    del pending_receipts[user_id]
    if user_id in receipt_photos:
        del receipt_photos[user_id]
    if query.message.photo:
        query.edit_message_caption(
            caption="✅ خرید رد شد. مبلغ به حساب کاربر بازگردانده شد."
        )
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
        row.append(
            InlineKeyboardButton(f"{amt:,}", callback_data=f"balance_increase_{amt}")
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(
        [
            InlineKeyboardButton(
                "✏️ مبلغ دلخواه", callback_data="balance_increase_custom"
            )
        ]
    )
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)


def ask_custom_balance(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    awaiting_custom_balance[query.from_user.id] = True
    query.edit_message_text(
        "✏️ لطفاً مبلغ دلخواه (به تومان) را به صورت عددی ارسال کنید:"
    )


def show_balance_payment_screen(query, context, amount):
    text = (
        f"برای افزایش موجودی به مبلغ {amount:,} تومان، مبلغ را به حساب بانکی واریز کنید.\n\n"
        "💳 شماره کارت: <code>6219 8619 4308 4037</code>\n"
        "به نام: امیرحسین سیاهبالایی\n\n"
        "سپس رسید پرداخت را به صورت عکس ارسال کنید و روی دکمه '💳 ارسال درخواست افزایش موجودی' کلیک کنید."
    )
    keyboard = [
        [
            InlineKeyboardButton(
                "💳 ارسال درخواست افزایش موجودی", callback_data="balance_request_confirm"
            )
        ],
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
    if (
        user_id not in pending_balance_requests
        or user_id not in pending_balance_receipts
    ):
        query.edit_message_text("❌ لطفاً ابتدا عکس رسید پرداخت خود را ارسال کنید.")
        return
    amount = pending_balance_requests[user_id]
    photo_file_id = pending_balance_receipts[user_id]
    for admin in admin_ids:
        try:
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ تایید",
                            callback_data=f"approve_balance_{user_id}_{amount}",
                        ),
                        InlineKeyboardButton(
                            "❌ رد", callback_data=f"reject_balance_{user_id}_{amount}"
                        ),
                    ]
                ]
            )
            context.bot.send_photo(
                chat_id=admin,
                photo=photo_file_id,
                caption=f"درخواست افزایش موجودی از کاربر {user_id}:\nمبلغ: {amount:,} تومان",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"خطا در ارسال رسید افزایش موجودی به ادمین {admin}: {e}")
    query.edit_message_text(
        "✅ درخواست افزایش موجودی شما ارسال شد و در انتظار تایید ادمین می‌باشد."
    )


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
        query.edit_message_caption(
            caption="✅ درخواست افزایش موجودی تایید شد. موجودی کاربر به حساب اضافه شد."
        )
    else:
        query.edit_message_text(
            "✅ درخواست افزایش موجودی تایید شد. موجودی کاربر به حساب اضافه شد."
        )
    try:
        context.bot.send_message(
            chat_id=user_id,
            text="✅ درخواست افزایش موجودی شما تایید شد. موجودی به حساب شما اضافه شد.",
        )
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
        context.bot.send_message(
            chat_id=user_id, text="❌ درخواست افزایش موجودی شما رد شد."
        )
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")


# ------------------ بخش حساب کاربری ------------------


def account_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
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
            timestamp = rec["timestamp"].strftime("%Y-%m-%d %H:%M")
            plan_name = DNS_CONFIGS.get(rec["plan"], {}).get("name", rec["plan"])
            text += f"• {plan_name} - {rec['cost']:,} تومان - {timestamp}\n"
            text += f"  IPv4: <code>{rec['ip1']}</code>, <code>{rec['ip2']}</code>\n"
            text += f"  IPv6: <code>{rec.get('ipv6_1', 'N/A')}</code>, <code>{rec.get('ipv6_2', 'N/A')}</code>\n"
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
        [
            InlineKeyboardButton(
                "💰 تبدیل امتیاز به موجودی", callback_data="convert_referral"
            )
        ],
        [InlineKeyboardButton("🔗 رفرال و امتیاز", callback_data="referral_menu")],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")],
    ]
    query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


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
        [
            InlineKeyboardButton(
                "💰 تبدیل امتیاز به موجودی", callback_data="convert_referral"
            )
        ],
        [InlineKeyboardButton("🏠 منوی اصلی", callback_data="main_menu")],
    ]
    query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )


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
        update.message.reply_text(
            f"✅ کد تخفیف {code} با {discount_codes[code]}% تخفیف اعمال شد."
        )
    else:
        update.message.reply_text("❌ کد تخفیف نامعتبر است.")
    if user_id in awaiting_discount_code:
        del awaiting_discount_code[user_id]


# ------------------ هندلر پیام‌های متنی ------------------


def text_message_handler(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id in blocked_users:
        update.message.reply_text("❌ شما توسط مدیریت مسدود شده‌اید.")
        return

    if user_id in admin_state:
        op = admin_state[user_id]["operation"]
        if op == "modify_balance":
            admin_data = admin_state[user_id]
            if admin_data["step"] == "awaiting_user_id":
                try:
                    target_user_id = int(update.message.text.strip())
                except ValueError:
                    update.message.reply_text(
                        "❌ آیدی وارد شده معتبر نیست. لطفاً یک عدد وارد کنید."
                    )
                    return
                admin_data["target_user_id"] = target_user_id
                admin_data["step"] = "awaiting_amount"
                update.message.reply_text(
                    "لطفاً مقدار تغییر موجودی را وارد کنید (مثبت برای افزایش، منفی برای کاهش):"
                )
                return
            elif admin_data["step"] == "awaiting_amount":
                try:
                    delta = int(update.message.text.strip().replace(",", ""))
                except ValueError:
                    update.message.reply_text(
                        "❌ مقدار وارد شده معتبر نیست. لطفاً یک عدد وارد کنید."
                    )
                    return
                target_user_id = admin_data["target_user_id"]
                old_balance = user_balance.get(target_user_id, 0)
                new_balance = old_balance + delta
                user_balance[target_user_id] = new_balance
                save_balance()
                update.message.reply_text(
                    f"✅ موجودی کاربر {target_user_id} از {old_balance:,} به {new_balance:,} تومان تغییر کرد."
                )
                try:
                    context.bot.send_message(
                        chat_id=target_user_id,
                        text=f"💡 موجودی حساب شما توسط ادمین تغییر یافت. موجودی فعلی: {new_balance:,} تومان",
                    )
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به کاربر {target_user_id}: {e}")
                del admin_state[user_id]
                return
        elif op == "block_user":
            try:
                target_user_id = int(update.message.text.strip())
            except ValueError:
                update.message.reply_text(
                    "❌ آیدی وارد شده معتبر نیست. لطفاً یک عدد وارد کنید."
                )
                return
            blocked_users.add(target_user_id)
            update.message.reply_text(f"🚫 کاربر {target_user_id} مسدود شد.")
            del admin_state[user_id]
            return
        elif op == "unblock_user":
            try:
                target_user_id = int(update.message.text.strip())
            except ValueError:
                update.message.reply_text(
                    "❌ آیدی وارد شده معتبر نیست. لطفاً یک عدد وارد کنید."
                )
                return
            if target_user_id in blocked_users:
                blocked_users.remove(target_user_id)
                update.message.reply_text(f"✅ مسدودسازی کاربر {target_user_id} لغو شد.")
            else:
                update.message.reply_text(
                    "❌ این کاربر در لیست مسدود شده‌ها وجود ندارد."
                )
            del admin_state[user_id]
            return
        elif op == "mass_message":
            text_to_broadcast = update.message.text
            count = 0
            for uid in all_users:
                try:
                    context.bot.send_message(chat_id=uid, text=text_to_broadcast)
                    count += 1
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به کاربر {uid}: {e}")
            update.message.reply_text(f"✅ پیام همگانی به {count} کاربر ارسال شد.")
            del admin_state[user_id]
            return
        elif op == "set_force_channel":
            new_channel = None
            if update.message.forward_from_chat:
                chat = update.message.forward_from_chat
                if chat.type != "channel":
                    update.message.reply_text("❌ پیام فوروارد شده از یک کانال نیست.")
                    return
                if chat.username:
                    new_channel = "@" + chat.username
                else:
                    update.message.reply_text(
                        "❌ کانال فوروارد شده دارای آیدی عمومی نمی‌باشد."
                    )
                    return
            elif update.message.text and update.message.text.strip().startswith("@"):
                new_channel = update.message.text.strip()
            else:
                update.message.reply_text(
                    "❌ لطفاً پیام فوروارد شده از کانال یا آیدی کانال به صورت صحیح ارسال کنید."
                )
                return
            try:
                bot = context.bot.get_me()
                member = context.bot.get_chat_member(new_channel, bot.id)
                if member.status not in ["administrator", "creator"]:
                    update.message.reply_text(
                        "❌ بات در این کانال ادمین نیست. لطفاً ابتدا بات را ادمین کنید."
                    )
                    del admin_state[user_id]
                    return
            except Exception as e:
                update.message.reply_text(
                    "❌ خطا در بررسی کانال. لطفاً مطمئن شوید کانال صحیح است."
                )
                del admin_state[user_id]
                return
            global FORCE_JOIN_CHANNEL
            FORCE_JOIN_CHANNEL = new_channel
            global FORCE_JOIN_ENABLED
            FORCE_JOIN_ENABLED = True
            update.message.reply_text(
                f"✅ کانال جویین اجباری به {new_channel} تنظیم شد و فعال می‌باشد."
            )
            del admin_state[user_id]
            return

    if user_id in awaiting_custom_balance and awaiting_custom_balance[user_id]:
        try:
            amount = int(update.message.text.replace(",", ""))
        except ValueError:
            update.message.reply_text(
                "❌ مقدار وارد شده معتبر نیست. لطفاً یک عدد به تومان وارد کنید."
            )
            return
        if amount < 10000 or amount > 1000000:
            update.message.reply_text(
                "❌ مقدار وارد شده خارج از محدوده مجاز است (10,000 تا 1,000,000 تومان)."
            )
            return
        pending_balance_requests[user_id] = amount
        if user_id in awaiting_custom_balance:
            del awaiting_custom_balance[user_id]
        keyboard = [
            [
                InlineKeyboardButton(
                    "💳 ارسال درخواست افزایش موجودی",
                    callback_data="balance_request_confirm",
                )
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
        ]
        text = (
            f"برای افزایش موجودی به مبلغ {amount:,} تومان، مبلغ را به حساب بانکی واریز کنید.\n\n"
            "💳 شماره کارت: <code>6219 8619 4308 4037</code>\n"
            "به نام: امیرحسین سیاهبالایی\n\n"
            "سپس رسید پرداخت را به صورت عکس ارسال کنید و روی دکمه '💳 ارسال درخواست افزایش موجودی' کلیک کنید."
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    elif user_id in awaiting_discount_code and awaiting_discount_code[user_id]:
        handle_discount_code_text(update, context)
    else:
        update.message.reply_text("❌ دستور یا اطلاعات ناشناخته.")


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
        [
            InlineKeyboardButton(
                "💰 مدیریت افزایش موجودی", callback_data="admin_pending_balance"
            ),
            InlineKeyboardButton(
                "💸 تغییر موجودی کاربر", callback_data="admin_modify_balance"
            ),
        ],
        [
            InlineKeyboardButton("🚫 مسدودسازی کاربر", callback_data="admin_block_user"),
            InlineKeyboardButton(
                "✅ لغو مسدودسازی کاربر", callback_data="admin_unblock_user"
            ),
        ],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_mass_message")],
        [
            InlineKeyboardButton(
                "🔒 جویین اجباری کانال", callback_data="admin_toggle_force_join"
            ),
            InlineKeyboardButton(
                "📝 تنظیم کانال اجباری", callback_data="admin_set_force_channel"
            ),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text, reply_markup=reply_markup)


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


def admin_modify_balance_prompt(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    admin_id = query.from_user.id
    if admin_id not in admin_ids:
        query.edit_message_text("❌ دسترسی ندارید.")
        return
    admin_state[admin_id] = {"operation": "modify_balance", "step": "awaiting_user_id"}
    query.edit_message_text(
        "✏️ لطفاً آیدی کاربر مورد نظر را (به صورت عددی) ارسال کنید.\nبرای انصراف، /cancel را بزنید."
    )


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
    query.edit_message_text(
        "✅ لطفاً آیدی کاربر مورد نظر برای لغو مسدودسازی را ارسال کنید."
    )


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
    query.edit_message_text(
        "📝 لطفاً پیام فوروارد شده از کانال یا آیدی عمومی کانال (مثلاً @amir) را ارسال کنید:"
    )


def admin_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        if context.args and context.args[0] == ADMIN_PASSWORD:
            admin_ids.add(user_id)
            update.message.reply_text("✅ شما به عنوان ادمین ثبت شدید.")
        else:
            update.message.reply_text(
                "❌ دسترسی غیرمجاز. برای ورود رمز عبور را همراه /admin ارسال کنید. مثال: /admin 1"
            )
            return
    keyboard = [
        [InlineKeyboardButton("⚙️ پنل ادمین", callback_data="admin_panel_menu")]
    ]
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
        query.edit_message_text(
            f"✅ {points} امتیاز به مبلغ {credit:,} تومان به موجودی شما اضافه شد."
        )
    else:
        query.edit_message_text("❌ امتیاز کافی برای تبدیل موجودی ندارید.")


# ------------------ ثبت هندلرها ------------------


def main() -> None:
    TOKEN = "7487680597:AAG-D9C8jlqQ4se4yV9ozxIOx9Z1bVGDfBk"  # جایگزین کنید با توکن واقعی ربات شما
    load_balance()
    load_history()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # فرمان‌ها
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("admin", admin_command))
    dp.add_handler(CommandHandler("cancel", admin_cancel))
    dp.add_handler(CommandHandler("account", account_menu))

    # هندلرهای CallbackQuery
    dp.add_handler(CallbackQueryHandler(show_main_menu, pattern="^main_menu$"))
    dp.add_handler(CallbackQueryHandler(dns_menu, pattern="^dns_menu$"))
    dp.add_handler(CallbackQueryHandler(buy_dns_plan, pattern="^buy_dnsplan_.*"))
    dp.add_handler(CallbackQueryHandler(account_menu, pattern="^account_menu$"))
    dp.add_handler(
        CallbackQueryHandler(balance_increase_menu, pattern="^balance_increase$")
    )
    dp.add_handler(
        CallbackQueryHandler(ask_custom_balance, pattern="^balance_increase_custom$")
    )
    dp.add_handler(
        CallbackQueryHandler(
            handle_balance_increase_request, pattern="^balance_increase_.*"
        )
    )
    dp.add_handler(
        CallbackQueryHandler(
            balance_request_confirm, pattern="^balance_request_confirm$"
        )
    )
    dp.add_handler(CallbackQueryHandler(confirm_receipt, pattern="^confirm_receipt$"))
    dp.add_handler(
        CallbackQueryHandler(
            admin_approve_purchase, pattern="^admin_approve_purchase_.*"
        )
    )
    dp.add_handler(
        CallbackQueryHandler(admin_reject_purchase, pattern="^admin_reject_purchase_.*")
    )
    dp.add_handler(CallbackQueryHandler(approve_balance, pattern="^approve_balance_.*"))
    dp.add_handler(CallbackQueryHandler(reject_balance, pattern="^reject_balance_.*"))
    dp.add_handler(CallbackQueryHandler(admin_panel_menu, pattern="^admin_panel_menu$"))
    dp.add_handler(
        CallbackQueryHandler(admin_pending_balance, pattern="^admin_pending_balance$")
    )
    dp.add_handler(
        CallbackQueryHandler(apply_discount_prompt, pattern="^apply_discount$")
    )
    dp.add_handler(
        CallbackQueryHandler(
            admin_modify_balance_prompt, pattern="^admin_modify_balance$"
        )
    )
    dp.add_handler(CallbackQueryHandler(convert_referral, pattern="^convert_referral$"))
    dp.add_handler(CallbackQueryHandler(admin_block_user, pattern="^admin_block_user$"))
    dp.add_handler(
        CallbackQueryHandler(admin_unblock_user, pattern="^admin_unblock_user$")
    )
    dp.add_handler(
        CallbackQueryHandler(admin_mass_message, pattern="^admin_mass_message$")
    )
    dp.add_handler(
        CallbackQueryHandler(
            admin_toggle_force_join, pattern="^admin_toggle_force_join$"
        )
    )
    dp.add_handler(
        CallbackQueryHandler(
            admin_set_force_channel, pattern="^admin_set_force_channel$"
        )
    )
    dp.add_handler(CallbackQueryHandler(referral_menu, pattern="^referral_menu$"))

    # هندلر پیام‌های متنی و عکس
    dp.add_handler(
        MessageHandler(Filters.text & ~Filters.command, text_message_handler)
    )
    dp.add_handler(MessageHandler(Filters.photo, receipt_photo_handler))

    updater.start_polling()
    logger.info("✅ ربات در حال اجراست...")
    updater.idle()


if __name__ == "__main__":
    main()