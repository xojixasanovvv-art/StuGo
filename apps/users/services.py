import logging
import re
import secrets
import time

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

# --- Telefon raqam validatsiyasi -------------------------------------------
# StuGo — O'zbekiston studentlar platformasi, shuning uchun faqat +998
# raqamlari qabul qilinadi: +998 + 2 xonali operator/region kodi + 7 xonali raqam.
#
# Manbalar: ITU E.164 (O'zbekiston), Wikipedia "Telephone numbers in
# Uzbekistan", goldenpages.uz va operatorlarning rasmiy sahifalari.
#
# Muhim: bu ro'yxat yangi operator kodlari chiqishi bilan to'liq emas bo'lishi
# mumkin. Shu sababli `.env` dagi `PHONE_OPERATOR_CODES` orqali kengaytirish
# mumkin — kodga tegmasdan yangi kod qo'shish uchun.
_uz_mobile = {"20", "33", "50", "70", "77", "80", "87", "88", "90",
              "91", "92", "93", "94", "95", "97", "98", "99"}
_uz_geo = {"61", "62", "65", "66", "67", "69", "71", "72", "73",
           "74", "75", "76", "78", "79"}
_uz_other = {"55", "36"}  # Uztelecom VoIP / Sharq Telecom (EVO)

_DEFAULT_OPERATOR_CODES = _uz_mobile | _uz_geo | _uz_other


def _operator_codes() -> set[str]:
    """Amaldagi operator kodlari (default + `.env` dan qo'shilgan)."""
    extra = getattr(settings, "PHONE_OPERATOR_CODES", "") or ""
    added = {c.strip() for c in extra.replace(";", ",").split(",") if c.strip().isdigit() and len(c.strip()) == 2}
    return _DEFAULT_OPERATOR_CODES | added


_UZ_CLEAN_RE = re.compile(r"^998\d{9}$")
_UZ_E164_RE = re.compile(r"^\+998\d{9}$")


def normalize_phone(raw: str) -> str:
    """Har qanday kirish formatini +998XXXXXXXXX ko'rinishiga keltiradi.

    Qabul qilinadigan formatlar:
        +998 90 123 45 67 / 998901234567 / 901234567 / 00998901234567

    Aks holda ValueError chiqadi — serializer uni to'g'ri xatoga aylantiradi.
    """
    if raw is None:
        raise ValueError("Telefon raqam kiritish shart.")
    cleaned = re.sub(r"[\s\-()]", "", str(raw).strip())
    if not cleaned:
        raise ValueError("Telefon raqam kiritish shart.")

    # 00998901234567 -> +998901234567
    if cleaned.startswith("00998"):
        cleaned = "+" + cleaned[2:]
    # 998901234567 -> +998901234567
    elif cleaned.startswith("998"):
        cleaned = "+" + cleaned
    # 901234567 (9 raqamli, mamlakat kodi bilan)
    elif len(cleaned) == 9 and cleaned.isdigit():
        cleaned = "+998" + cleaned

    if not _UZ_E164_RE.match(cleaned):
        # Aniq nima xato ekanini aytish uchun raqam uzunligini tekshiramiz.
        digits = re.sub(r"\D", "", cleaned)
        if len(digits) == 12:
            raise ValueError(
                "Bu raqam 998 dan boshlanmaydi. +998 bilan yozing. "
                "Namuna: +998 90 123 45 67"
            )
        if len(digits) != 12:
            raise ValueError(
                f"Telefon raqam {len(digits)} xonali, 12 xonali bo'lishi kerak "
                "(+998 + 2 xonali operator + 7 xonali raqam). Namuna: +998 90 123 45 67"
            )
        raise ValueError(
            "Telefon raqam noto'g'ri. Namuna: +998 90 123 45 67"
        )

    operator = cleaned[4:6]
    if operator not in _operator_codes():
        raise ValueError(
            f"Operator kodi {operator} topilmadi. "
            "Mumkin kodlar: 20, 33, 50, 77, 88, 90, 91, 93, 94, 95, 97, 98, 99 "
            "(shuningdek 61, 65, 66, 69, 71, 72, 73, 74, 75, 76, 78, 79 — "
            "shahar raqamlari)."
        )

    return cleaned


def _mask_phone(phone: str) -> str:
    """Log uchun raqamni yashirish: +998901234567 -> +998*****67"""
    if len(phone) < 6:
        return "***"
    return f"{phone[:5]}*****{phone[-2:]}"


def _mask_email(email: str) -> str:
    """Log uchun emailni yashirish: student@tumansoft.uz -> s***@tumansoft.uz"""
    if "@" not in email:
        return "***"
    name, _, domain = email.partition("@")
    head = name[:1] if name else ""
    return f"{head}***@{domain}"


def send_otp(phone: str, purpose: str = "register") -> str:
    """Telefon uchun OTP yaratadi. Qaytaradi: kod."""
    return _issue_code(phone, purpose, label=_mask_phone(phone))


def verify_otp(phone: str, code: str, purpose: str = "register") -> tuple[bool, str]:
    """Telefon OTP kodini tekshiradi. Qaytaradi: (ok, xato_xabari)."""
    return _check_code(phone, code, purpose)


def send_email_otp(email: str, purpose: str = "email_verify") -> str:
    """Universitet emaili uchun tasdiqlash kodi yuboradi.

    Email ro'yxatdan o'tkazishni tasdiqlash uchun `is_verified` beriladi,
    shuning uchun foydalanuvchi bu kodni faqat o'z inbox'i orqali olishi
    kerak — o'z mailini "tasdiqlangan" deb e'lon qila olmaydi.
    """
    return _issue_code(email, purpose, label=_mask_email(email))


def verify_email_otp(email: str, code: str, purpose: str = "email_verify") -> tuple[bool, str]:
    """Email tasdiqlash kodini tekshiradi. Qaytaradi: (ok, xato_xabari)."""
    return _check_code(email, code, purpose)


def cooldown_seconds_left(target: str, purpose: str) -> int:
    """Qayta yuborishgacha qolgan sekundlar. 0 = yuborish mumkin.

    View'lar bu qiymatni frontend'ga yuboradi, u o'z tilidagi xabarni
    shakllantiradi (server bitta tilni qaytarmaydi).
    """
    last_sent = cache.get(f"otp_cooldown:{purpose}:{target}")
    if not last_sent:
        return 0
    elapsed = (timezone.now() - last_sent).total_seconds()
    return max(int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed), 0)


def _issue_code(target: str, purpose: str, label: str) -> str:
    """OTP kod yaratadi, cache'ga yozadi va yuboruvchini chaqiradi.

    Xavfsizlik: urinishlar hisobi *kodga emas, target bo'yicha oynaga*
    bog'lanadi (`otp_window`). Shu sababli haker qayta yuborish orqali
    limitni to'zlay olmaydi. Oyna `OTP_EXPIRE_SECONDS` da tugaydi.
    """
    ttl = settings.OTP_EXPIRE_SECONDS
    cooldown = settings.OTP_RESEND_COOLDOWN_SECONDS
    key = f"otp:{purpose}:{target}"
    cooldown_key = f"otp_cooldown:{purpose}:{target}"
    window_key = f"otp_window:{purpose}:{target}"

    # Qayta yuborish oralig'ini cheklash
    last_sent = cache.get(cooldown_key)
    if last_sent:
        elapsed = (timezone.now() - last_sent).total_seconds()
        wait = int(cooldown - elapsed)
        if wait > 0:
            raise ValueError(f"Kodni qayta yuborish uchun {wait} soniya kutib turing.")

    # Oynani birinchi yuborishda boshlaymiz. Qayta yuborish oynani
    # umaytirmaydi — aks holda urinishlar chegarasi cho'zilib ketardi.
    # Django cache API'sida `ttl()` yo'q, shuning uchun tugash vaqti
    # (`timestamp`) qiymat sifatida saqlanadi.
    window_end = cache.get(window_key)
    if not isinstance(window_end, (int, float)) or window_end <= time.time():
        window_end = time.time() + ttl
        cache.set(window_key, window_end, ttl)
    remaining = max(int(window_end - time.time()), 1)

    code = f"{secrets.randbelow(10 ** settings.OTP_LENGTH):0{settings.OTP_LENGTH}d}"
    cache.set(key, code, remaining)
    cache.set(cooldown_key, timezone.now(), cooldown)

    logger.info("OTP yuborildi | purpose=%s target=%s", purpose, label)

    # TODO production: Eskiz.uz / PlayMobile (SMS) va SMTP (email).
    # Provider ulanmagan: kod faqat DEBUG rejimida logga yoziladi,
    # production'da esa hech qayerda saqlanmaydi.
    if settings.DEBUG and settings.OTP_DEBUG_RETURN_CODE:
        logger.info("[OTP:DEBUG] %s -> StuGo: %s", label, code)

    return code


def _check_code(target: str, code: str, purpose: str) -> tuple[bool, str]:
    key = f"otp:{purpose}:{target}"
    attempts_key = f"otp_attempts:{purpose}:{target}"
    window_key = f"otp_window:{purpose}:{target}"

    stored = cache.get(key)
    if not stored:
        cache.delete(attempts_key)
        cache.delete(window_key)
        return False, "Kod muddati tugagan yoki yuborilmagan."

    attempts = cache.get(attempts_key, 0)
    if attempts >= settings.OTP_MAX_ATTEMPTS:
        cache.delete(key)
        cache.delete(f"otp_cooldown:{purpose}:{target}")
        return False, (
            "Urinishlar soni tugagan. Yangi kod uchun "
            f"{settings.OTP_EXPIRE_SECONDS} soniya kutib turing."
        )

    # Doimiy vaqtli taqqoslash — timing attack'dan himoya
    if not secrets.compare_digest(str(code).strip(), str(stored)):
        # TTL'ni cho'zmaymiz: oyna qolgan vaqtda saqlanadi.
        window_end = cache.get(window_key)
        left_ttl = (
            max(int(window_end - time.time()), 1)
            if isinstance(window_end, (int, float))
            else 1
        )
        cache.set(attempts_key, attempts + 1, left_ttl)
        left = settings.OTP_MAX_ATTEMPTS - (attempts + 1)
        if left <= 2:
            return False, f"Kod xato. Yana {left} ta urinish qoldi."
        return False, "Kod xato."

    cache.delete(key)
    cache.delete(attempts_key)
    cache.delete(window_key)
    cache.delete(f"otp_cooldown:{purpose}:{target}")
    return True, ""