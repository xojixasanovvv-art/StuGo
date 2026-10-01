"""`manage.py telegram_bot` — Telegram botni long polling bilan ishga tushirish.

Nima uchun alohida command
--------------------------
Telegram webhook ishlatish uchun **ochiq internetdan yetib boradigan**
manzil (ngrok, VPS, domain) talab qiladi. Lokal rivojlashda
`http://127.0.0.1:8000` bundan foydalanmaydi — webhook ishlamaydi.

Shuning uchun biz **long polling** ishlatamiz: bot o'zi Telegram'ga
`getUpdates` deb so'rov yuborib navbatni oladi. Buning uchun faqat
token kerak, hech qanday ochiq manzil emas.

Qanday ishlatiladi
------------------
    # 1) kod yaratish (saytning o'zi `POST /api/v1/auth/telegram/link/`
    #    orqali yaratadi, shuning uchun odatda bu qadam kerak emas)
    # 2) botni ishga tushirish — alohida terminalda, server yonida:
    python manage.py telegram_bot

Bot ishga tushgandan keyin Telegram'da botga "Boshlash" (Start)
bosilsa, `?start=CODE` dagi kod `Profile.telegram_id` ga bog'lanadi.

Ctrl+C bilan to'xtatiladi. `--once` — bitta navbatni o'qib chiqib
chiqish (testlar uchun).
"""

from __future__ import annotations

import signal
import time
from collections import defaultdict, deque

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.users import telegram


class _RateLimiter:
    """Bir Telegram chat'ida vaqt oralig'ida ruxsat etilgan `/start` soni.

    Nima uchun shu yerda
    -------------------
    Himoya ikki qatlamda:
      * baza tomonda — kod `unique` va 8 xonali, ya'ni taxmin qilib
        topib bo'lmaydi (`link_telegram_account` docstring);
      * bot tomonda — bitta Telegram hisobidan **so'rovlar sonini**
        cheklaydi. Aks holda hujjumchi `getUpdates` orqali 10^8 marta
        `/start 00000001` yuborib, bazani chalg'itadi.

    Nima uchun oddiy dict
    -------------------
    Bot — bitta uzun muddatli jarayon. Bir nechta bot nusxasi ishga
    tushsa, har biri o'z hisobini yuritadi — bu maqbul (chegara
    bo'lishi kerak emas).
    """

    def __init__(self, max_hits: int, window: float = 60.0):
        self.max_hits = max_hits
        self.window = window
        self._hits: dict[int, deque] = defaultdict(deque)

    def allow(self, key: int) -> bool:
        """Bu so'rovni o'tkazish mumkinmi? Mumkin bo'lsa True."""
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.max_hits:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


class Command(BaseCommand):
    help = "Telegram botni long polling bilan ishga tushiradi (hisob bog'lash)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Faqat bitta navbatni o'qib chiqib to'xtaydi (test uchun).",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=25,
            help="Telegram serverdagi kutish (sekund). 0-59. Default 25.",
        )
        parser.add_argument(
            "--idle-sleep",
            type=float,
            default=1.0,
            help="Xabar bo'lmaganda necha soniya kutamiz (default 1.0).",
        )
        parser.add_argument(
            "--max-attempts-per-minute",
            type=int,
            default=int(getattr(settings, "TELEGRAM_LINK_MAX_ATTEMPTS", 5)),
            help="Bir Telegram chat'ida daqiqasiga ruxsat etilgan /start soni.",
        )

    def handle(self, *args, **options):
        if not telegram.is_configured():
            raise CommandError(
                "TELEGRAM_BOT_TOKEN .env da yo'q. BotFather tokenini yozing va "
                "qayta urinib ko'ring."
            )

        try:
            me = telegram.get_me()
        except telegram.TelegramError as exc:
            raise CommandError(f"Botga ulanib bo'lmadi: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Bot ulandi: @%s" % me.get("username", "?")))

        self.limiter = _RateLimiter(max(1, options["max_attempts_per_minute"]))
        offset: int | None = None
        self._running = True

        def _stop(signum, frame):  # noqa: ARG001
            self._running = False
            self.stdout.write("\nTo'xtatildi.")

        # Ctrl+C (SIGINT) va Linux'da SIGTERM ni ushlaymiz — shunda
        # `offset` saqlanadi va Telegram'ga navbatni tasdiqlaymiz.
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _stop)
            except (ValueError, OSError):  # pragma: no cover — Windows thread
                pass

        while self._running:
            try:
                updates = telegram.get_updates(offset=offset, timeout=options["timeout"])
            except telegram.TelegramError as exc:
                # Telegram vaqtincha javob bermaydi (tarmoq uzilishi, 429).
                # Buyruqni o'ldirmaydi — biroz kutib, qayta urunadi.
                self.stderr.write(self.style.WARNING(f"getUpdates xatosi: {exc}"))
                time.sleep(5)
                continue

            for update in updates:
                # Telegram har update ga monoton `update_id` beradi. Keyingi
                # so'rovda shu raqamni `offset` qilib yuborish, "olindi"
                # deb tasdiqlash usuli — shunda xabar ikki marta qaytmaydi.
                offset = update["update_id"] + 1
                self._handle_update(update)

            if options["once"]:
                break

            if not updates:
                close_old_connections()
                time.sleep(options["idle_sleep"])

        self.stdout.write("Bot to'xtadi. Fayil: apps/users/telegram.py")

    # ------------------------------------------------------------------
    def _handle_update(self, update: dict) -> None:
        """Bir kelgan xabarni qayta ishlaydi."""
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}

        chat_id = chat.get("id")
        # Faqat shaxsiy chat'da bog'lanish mumkin — guruhda `chat.id`
        # manzil (negative) bo'ladi, haqiqiy foydalanuvchi esa
        # `message.from.id` da. `None` bo'lsa hech narsa bog'lamaymiz.
        telegram_id = chat_id if chat.get("type") == "private" else None
        username = chat.get("username") or (message.get("from") or {}).get("username") or ""

        if telegram_id is None:
            return

        # So'rovlar sonini cheklaymiz — aks holda bitta chat baza
        # so'rovlari bilan bombalaydi.
        if not self.limiter.allow(telegram_id):
            self.stderr.write(
                self.style.WARNING(f"  chat {chat_id}: urinishlar limiti oshdi, e'tiborsiz")
            )
            return

        code = self._extract_code(text)
        if not code:
            # Kod kelmagan — foydalanuvchiga qanday bog'lanishni aytib beramiz.
            self._reply(chat_id, self._welcome_text())
            return

        result, http_status = telegram.link_telegram_account(
            code, telegram_id, username
        )
        # `->` va `—` ishlatamiz: Windows konsolining standart kod sahifasi
        # (cp1251) `→` belgisini chiqara olmaydi va `UnicodeEncodeError`
        # beradi — buyruq shu sababdan ishdan to'xtaydi.
        self.stdout.write(
            f"  /start {code} -> {result} ({telegram_id} @ {username or '-'})"
        )

        self._reply(chat_id, self._result_text(result))

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_code(text: str) -> str | None:
        """`/start 12345678` yoki `/start@bot 12345678` dan 8 xonali kodni oladi.

        Telegram deep-link `?start=CODE` ni avtomatik ravishda `/start CODE`
        deb yuboradi. Qo'shimcha ravishda oddiy "12345678" yuborilsa ham
        ishlaydi — foydalanuvchi kodni qo'lda kiritishi mumkin.
        """
        if not text:
            return None
        parts = text.split()
        if parts and parts[0].startswith("/start"):
            parts = parts[1:]
        for part in parts:
            part = part.strip().lstrip("@")
            if part.isdigit() and 4 <= len(part) <= 16:
                return part
        return None

    # ------------------------------------------------------------------
    def _welcome_text(self) -> str:
        home = telegram.home_link()
        lines = [
            "Salom! StuGo botiga xush kelibsiz.",
            "",
            "Hisobingizni ulash uchun saytdagi «Telegram bilan bog'lanish» "
            "tugmasini bosing — u sizga 8 xonali kod beradi. "
            "Shu kodni shu yerga yuboring.",
        ]
        if home:
            lines += ["", f"Sayt: {home}"]
        return "\n".join(lines)

    def _result_text(self, result: str) -> str:
        home = telegram.home_link()
        texts = {
            "linked": "Telegram hisobingiz StuGo'ga ulandi! Saytga qaytib, "
            "profilni yangilang.",
            "no_code": "Bu kod topilmadi yoki muddati tugagan. Saytda yangi kod oling.",
            "bad_code": "Kod noto'g'ri yoki muddati tugagan. Saytda «Telegram bilan "
            "bog'lanish» tugmasini qayta bosing.",
            "attempts_exceeded": "Juda ko'p urinish. Yangi kod oling (saytda tugmani "
            "qayta bosing).",
            "already_linked": "Bu Telegram hisobi boshqa StuGo hisobiga ulangan. "
            "Avval u yerdan uzib, keyin qayta urinib ko'ring.",
        }
        out = texts.get(result, "Noma'lum xatolik yuz berdi.")
        if home and result == "linked":
            out += f"\n{home}"
        return out

    # ------------------------------------------------------------------
    def _reply(self, chat_id: int, text: str) -> None:
        """Xabar yuborish. Xato bo'lsa — jimgina o'tkazib yuboradi
        (foydalanuvchining xabari bir martalik qayta bo'lmasligi kerak)."""
        try:
            telegram.send_message(chat_id, text)
        except telegram.TelegramError as exc:
            self.stderr.write(self.style.WARNING(f"sendMessage xatosi: {exc}"))
