"""Telegram integratsiyasi — bot orqali hisobni ulash.

Nima qiladi
-----------
Foydalanuvchi saytda "Telegram bilan bog'lanish" tugmasini bosadi va
server unga bir martalik **kod** beradi. Keyin foydalanuvchi shu kod
telegram botining deep-link ochilish manziliga (`https://t.me/BOT?start=CODE`)
o'tadi va Telegram'da "Boshlash" ni bosadi.

Bot yangi xabarni oladi (`getUpdates`, long polling) va o'sha kodni
`Profile.telegram_id` ga bog'laydi. Sayt bir necha sekund ichida
holatni so'rab (`GET /auth/telegram/status/`) bog'lanishni tasdiqlaydi.

Nima uchun shu yo'l
-------------------
Telegram Login Widget va webhook **ochiq domen** talab qiladi
(my.telegram.org da sayt ro'yxatdan o'tkazilishi kerak). Bu esa
lokal rivojlashda (`http://127.0.0.1:8000`) umuman mumkin emas.
Deep-link + long polling esa faqat bot tokeniga muhtoj.

Nima uchun kod bazada saqlanadi
-------------------------------
Sayt va bot — ikki alohida jarayon. `LocMemCache` ular o'rtasida
bo'linmaydi (lokal rejimda Redis yo'q), shuning uchun kod
`TelegramLinkCode` jadvalida turadi. Batafsil izoh — model faylida.

Xavfsizlik
----------
* Kod 8 xonali tasodifiy (`secrets`), `TELEGRAM_LINK_TTL_SECONDS`
  (standart 600 s = 10 daqiqa) muddati bor va faqat bir marta
  ishlatiladi (`used_at`).
* Noto'g'ri urinishlar `TELEGRAM_LINK_MAX_ATTEMPTS` bilan cheklangan.
* Telegram id `unique` — bitta Telegram hisobi FAQAT bitta StuGo
  hisobiga ulanishi mumkin.
"""

from __future__ import annotations

import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# --- Telegram Bot API -------------------------------------------------------
_API = "https://api.telegram.org"
_TIMEOUT = 15  # sekund — oddiy so'rovlar uchun

# `getUpdates` long polling: Telegram serveri `timeout` sekund kutadi va
# keyin javob qaytaradi. Soket vaqti bundan **uzunroq** bo'lishi shart,
# aks holda `urlopen` `TimeoutError` beradi va bot hech qachon xabar
# olmaydi. Shuning uchun `get_updates` alohida uzunroq muddat ishlatadi.
_LONG_POLL_MARGIN = 20


class TelegramError(Exception):
    """Telegram API bilan bog'lanishda xatolik (foydalanuvchiga ko'rsatiladi)."""


def _token() -> str:
    return (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()


def is_configured() -> bool:
    """Bot tokeni `.env` da yozilganmi?"""
    return bool(_token())


def _call(method: str, payload: dict | None = None, timeout: int | None = None) -> dict:
    """Bot API ga so'rov yuboradi. Qaytaradi: `result` ichidagi ma'lumot.

    Telegram har doim `{"ok": bool, "result": ...}` qaytaradi. `ok: false`
    bo'lsa `description` da xatoni tushuntiradi — uni `TelegramError`
    orqali yuqoriga uzatamiz.

    `timeout` — soket vaqti (soniya). `getUpdates` long polling uchun
    serverdan so'rayotgan vaqtdan uzunroq bo'lishi kerak.
    """
    token = _token()
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN sozlanmagan.")

    url = f"{_API}/bot{token}/{method}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 404 odatda "bot tokeni noto'g'ri" degani
        raise TelegramError(f"HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TelegramError(str(exc)) from exc

    if not body.get("ok"):
        raise TelegramError(body.get("description", "Telegram javob bermadi."))
    return body.get("result") or {}


def get_me() -> dict:
    """Bot ma'lumotlari: `{"id", "username", "first_name", ...}`."""
    return _call("getMe")


def bot_username() -> str | None:
    """Botning `@username` ko'rinishi yoki `None`."""
    try:
        return (get_me() or {}).get("username")
    except TelegramError as exc:
        logger.warning("Telegram getMe failed: %s", exc)
        return None


def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    """Foydalanuvchiga xabar yuboradi."""
    payload: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return _call("sendMessage", payload)


# --- Bog'lanish kodi (deep link) -------------------------------------------

def _ttl() -> int:
    return int(getattr(settings, "TELEGRAM_LINK_TTL_SECONDS", 600))


def _max_attempts() -> int:
    """Bir Telegram chat'ida vaqt oralig'ida ruxsat etilgan urinishlar.

    `telegram_bot` buyrug'i shu qiymatdan foydalanadi (jarayon ichidagi
    `_RateLimiter`). Bu funksiya o'zi chegarani qo'llamaydi — kod aniq
    qidirilgani uchun baza tomonidan brute force'ni ushlab bo'lmaydi.
    """
    return int(getattr(settings, "TELEGRAM_LINK_MAX_ATTEMPTS", 5))


def create_link_code(user_id: int) -> str:
    """Foydalanuvchi uchun yangi bir martalik kod yaratadi.

    Eslatma: bitta foydalanuvchining avvalgi kodi o'chiriladi — aks holda
    bir nechta kod bir vaqtda yashirib qolardi va qaysi biri "haqiqiy"
    bo'lganini bilib bo'lmasdi.
    """
    from apps.users.models import TelegramLinkCode

    now = timezone.now()
    # Eskirgan va ishlatilgan kodlarni tozalaymiz — jadada
    # o'sib borishining oldini oladi (bot har daqiqada tekshirsa).
    TelegramLinkCode.objects.filter(expires_at__lt=now).delete()
    TelegramLinkCode.objects.filter(user_id=user_id).delete()

    for _ in range(5):
        code = f"{secrets.randbelow(10 ** 8):08d}"
        try:
            with transaction.atomic():
                TelegramLinkCode.objects.create(
                    user_id=user_id,
                    code=code,
                    expires_at=now + timezone.timedelta(seconds=_ttl()),
                )
            return code
        except IntegrityError:
            # (juda kam ehtimol) kod tasodifiy takrorlandi — qayta urunamiz
            continue
    raise TelegramError("Kod yaratib bo'lmadi, qayta urinib ko'ring.")


def peek_code_owner(code: str) -> int | None:
    """Kod qaysi foydalanuvchiga tegishli.

    Faqat o'qish uchun — kodni "ishlatilgan" deb belgilamaydi.
    `None` qaytaradi agar kod topilmasa, muddati tugagan yoki allaqachon
    ishlatilgan bo'lsa.
    """
    from apps.users.models import TelegramLinkCode

    row = TelegramLinkCode.objects.filter(code=(code or "").strip()).first()
    return row.user_id if row and row.is_valid else None


def consume_code(code: str) -> int | None:
    """Kodni "ishlatilgan" deb belgilaydi va foydalanuvchi ID qaytaradi."""
    from apps.users.models import TelegramLinkCode

    row = TelegramLinkCode.objects.filter(code=(code or "").strip()).first()
    if not row or not row.is_valid:
        return None
    row.used_at = timezone.now()
    row.save(update_fields=["used_at", "updated_at"])
    return row.user_id


def deep_link(username: str, code: str) -> str:
    """Foydalanuvchi ochadigan havola: `https://t.me/BOT?start=CODE`.

    `start` parametri Telegram'da `/start CODE` deb yuboriladi.
    """
    return f"https://t.me/{urllib.parse.quote(username)}?start={urllib.parse.quote(code)}"


def get_updates(offset: int | None = None, timeout: int = 25) -> list[dict]:
    """Bot navbatini o'qiydi (long polling).

    `timeout` — Telegram serverdagi kutish (uzunroq bo'lsa, bo'sh
    javobda ulanishni ushlab turadi va so'rovlar sonini kamaytiradi).

    Muhim: soket vaqti `timeout + _LONG_POLL_MARGIN` — aks holda
    `urlopen` server javob berishidan oldin `TimeoutError` beradi va
    bot qayta-qayta "read operation timed out" xatosini chiqaradi
    (lekin hech qachon xabar olmaydi).
    """
    payload: dict = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    return _call("getUpdates", payload, timeout=timeout + _LONG_POLL_MARGIN) or []


# --- Hisobni ulash ----------------------------------------------------------

def link_telegram_account(
    code: str, telegram_id: int, username: str = ""
) -> tuple[str, int]:
    """`/start CODE` xabarini qayta ishlaydi va hisobni bog'laydi.

    Qaytaradi: `(natija, http_kod)`. `natija` quyidagilardan biri:
      * `linked`         — muvaffaqiyatli bog'landi
      * `no_code`        — kod topilmadi
      * `bad_code`       — muddati tugagan yoki allaqachon ishlatilgan
      * `already_linked` — bu Telegram hisobi boshqa StuGo hisobida

    Himoya haqida: bu funksiya **hech qanday urinish chegarasini
    o'zi ushlamaydi**. Kod baza bo'yicha aniq qidiriladi, ya'ni
    tasodifiy kodni «taxmin qilish» 10^8 ta so'rov talab qiladi va
    bot uchun ham, bazа uchun ham amaliy emas. Haqiqiy himoya
    **Telegram foydalanuvchisi bo'yicha** (`telegram_bot` buyrug'ida
    `_RateLimiter`) — u 10^8 ta `getUpdates` yubormasligini kafolatlaydi.
    """
    from apps.users.models import Profile, TelegramLinkCode

    code = (code or "").strip()
    if not code:
        return ("no_code", 400)

    row = TelegramLinkCode.objects.filter(code=code).first()
    if row is None:
        return ("no_code", 400)

    if row.used_at is not None:
        return ("bad_code", 400)
    if row.expires_at <= timezone.now():
        return ("bad_code", 400)

    # Bu Telegram hisobi boshqa StuGo hisobiga ulanganmi?
    clash = (
        Profile.objects.filter(telegram_id=telegram_id)
        .exclude(user_id=row.user_id)
        .first()
    )
    if clash is not None:
        return ("already_linked", 409)

    now = timezone.now()
    with transaction.atomic():
        Profile.objects.filter(user_id=row.user_id).update(
            telegram_id=telegram_id,
            telegram_username=username or "",
            telegram_linked_at=now,
        )
        # `update()` yangi qator yaratmaydi. Profil signal bilan
        # yaratilgan bo'lsa ham, `get_or_create` bilan ishonchli
        # bo'lamiz.
        Profile.objects.get_or_create(
            user_id=row.user_id,
            defaults={
                "telegram_id": telegram_id,
                "telegram_username": username or "",
                "telegram_linked_at": now,
            },
        )
        # Kod bir marta ishlatiladi. `attempts` — necha marta ko'rsatilgani
        # (diagnostika uchun; himoya bot tomonda, qarang docstring).
        row.used_at = now
        row.attempts = (row.attempts or 0) + 1
        row.save(update_fields=["used_at", "attempts", "updated_at"])

    logger.info("Telegram: %s foydalanuvchi %s ga bog'landi", row.user_id, telegram_id)
    return ("linked", 200)


def site_url() -> str:
    """Saytning to'liq manzili (oxirida `/` BO'LMAYDI)."""
    return (getattr(settings, "TELEGRAM_WEB_BASE_URL", "") or "").rstrip("/")


def home_link() -> str:
    return f"{site_url()}/" if site_url() else ""
