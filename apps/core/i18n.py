"""Interfeys tarjimalari (uz / ru / en).

Arxitektura
------------
StuGo'da matnlar ikki xil joyda yashaydi:

1. **Server tomonda render qilinadigan HTML** (`templates/index.html`) —
   `{% tt "nav.cart" %}` shablon tegidan foydalaniladi.
2. **JavaScript orqali yaratiladigan matnlar** (toast, xato, bo'sh holat) —
   `t("toast.saved")` funksiyasi orqali. Bu matnlar HTML da yo'q, shuning
   uchun Django'ning `{% trans %}` tegi ishlamaydi.

Ikkalasi uchun **bir xil manba** ishlatiladi: `locale/frontend/<lang>.json`.
Buning sababi — bitta kalit bo'lsa, tarjimani topish oson va yangi til
qo'shishda hech narsa o'zgarishi kerak emas.

Nima uchun `.po`/`.mo` emas?
----------------------------
Django standarti `.po`/`.mo` fayllardir, lekin ular:
- `makemessages` komandasini har o'zgarishda ishga tushirishni talab qiladi;
- inline JavaScript ichidagi matnlarni avtomatik topa olmaydi
  (`_("...")` ichiga o'rash kerak, bu JS kodini ifodalashga xalal qiladi);
- admin va framework matnlari uchun kerak, lekin foydalanuvchi ko'radigan
  interfeys uchun noqulay.

Shu sababdan:
- Django/DRF/admin matnlari uchun -> standart `.po`/`.mo` (`locale/`)
- Foydalanuvchi interfeysi uchun -> JSON katalog (`locale/frontend/`)

Ikkalasi bir xil tilni (`LANGUAGE_CODE`) oladi va `LocaleMiddleware` orqali
boshqariladi, shuning uchun foydalanuvchi uchun bitta til tugmasi yetarli.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils.translation import get_language

# Xotirada saqlanadigan kataloglar: {lang: {key: text}}
_CACHE: dict[str, dict[str, str]] = {}

# Default til — kalit topilmasa shu qiymat qaytariladi. Bo'sh qoldirilmaydi,
# aks holda interfeysda bo'sh joylar paydo bo'ladi (bu jihatdan xavfsizroq).
FALLBACK_LANG = "uz"


def _locale_dir() -> Path:
    """Tarjima fayllari papkasini qaytaradi."""
    return Path(getattr(settings, "FRONTEND_LOCALE_DIR", Path("locale") / "frontend"))


def available_languages() -> list[str]:
    """Katalog fayli mavjud tillar ro'yxati (masalan: `["uz", "ru", "en"]`)."""
    from django.conf import settings as s

    dir_ = _locale_dir()
    declared = [code for code, _ in getattr(s, "LANGUAGES", [])]
    found = {p.stem for p in dir_.glob("*.json") if p.is_file()}
    # `LANGUAGES` da e'lon qilinganlar birinchi bo'lib, so'ng diskdagi qolganlari
    return declared + sorted(found - set(declared))


def _normalize(lang: str | None) -> str:
    """`ru-RU`, `RU`, None kabi qiymatlardan asosiy til kodini oladi."""
    if not lang:
        return FALLBACK_LANG
    code = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return code or FALLBACK_LANG


def load(lang: str | None = None, reload: bool = False) -> dict[str, str]:
    """Berilgan til uchun butun katalogni yuklaydi.

    Natijada `dict[str, str]` — kalit -> tarjima matni.
    """
    code = _normalize(lang or get_language())
    if not reload and code in _CACHE:
        return _CACHE[code]

    path = _locale_dir() / f"{code}.json"
    data: dict[str, str] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # Faqat satrlarni olamiz — noto'g'ri tuzilma jim qoldiriladi
                data = {str(k): str(v) for k, v in raw.items() if isinstance(v, (str, int, float))}
        except (OSError, ValueError):
            data = {}

    _CACHE[code] = data
    return data


def get(key: str, lang: str | None = None, **params: Any) -> str:
    """Tarjimani oladi.

        >>> t("toast.saved")
        'Saqlandi'
        >>> t("cart.items", lang="en", count=3)
        '3 items'

    Kalit topilmasa o'zbekcha matn qaytariladi, u ham topilmasa kalitning
    o'zi qaytariladi — bu esa `KeyError` o'rniga sezilarli xatoni beradi va
    ishlab turgan kodni buzmaydi.
    """
    code = _normalize(lang or get_language())

    text = load(code).get(key)
    if text is None:
        text = load(FALLBACK_LANG).get(key)

    if text is None:
        # Topilmadi: kalitni o'zi qaytaramiz — xato sezilarli bo'lsin,
        # lekin foydalanuvchiga `None`/bo'sh joy ko'rsatmaydi.
        return key

    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError, ValueError):
            # Tarjimada `{count}` o'rniga boshqa placeholder bo'lsa —
            # formatlash xatosi foydalanuvchiga ko'rinmasin.
            return text

    return text


def catalog_for(lang: str | None = None) -> dict[str, str]:
    """JavaScript uchun katalogni qaytaradi (merge qilingan holda).

    Default til (o'zbekcha) ham qo'shiladi, shunda katalog ichida barcha
    kalitlar bo'ladi va JS tomonda `{lang: katalog}` ko'rinishida saqlanadi —
    bu tilni brauzerda serverga so'rov yubormasdan almashtirish imkonini
    beradi.
    """
    base = dict(load(FALLBACK_LANG))
    base.update(load(lang))
    return base


def all_catalogs() -> dict[str, dict[str, str]]:
    """Barcha tillar uchun kataloglar: `{"uz": {...}, "ru": {...}, "en": {...}}`.

    Sahifa bir marta yuklanganda barcha tillar JS ga beriladi — keyin tilni
    almashtirish **serverga so'rov yubormaydi** (tez va uzluksiz).
    """
    langs = available_languages()
    base = load(FALLBACK_LANG)
    out: dict[str, dict[str, str]] = {}
    for code in langs:
        merged = dict(base)
        merged.update(load(code))
        out[code] = merged
    if FALLBACK_LANG not in out:
        out[FALLBACK_LANG] = base
    return out


def missing_keys(lang: str | None = None) -> list[str]:
    """Berilgan tilda yetishmayotgan kalitlar (default tilga nisbatan).

    Testlar va CI uchun: tarjimada o'zbekcha kalit qolib ketgan bo'lsa,
    ingliz/rus tilida u ko'rinib turadi (`missing translation`).
    """
    base = set(load(FALLBACK_LANG))
    return sorted(base - set(load(lang)))


def language_meta() -> list[dict[str, str]]:
    """Til tanlash uchun frontend ma'lumotlari.

    [{"code": "uz", "name": "O'zbekcha", "current": true}, ...]
    """
    current = _normalize(get_language())
    from django.conf import settings as s

    labels = dict(getattr(s, "LANGUAGES", []))
    return [
        {
            "code": code,
            "name": labels.get(code, code),
            "current": code == current,
        }
        for code in available_languages()
    ]


def clear_cache() -> None:
    """Testlar uchun: katalog xotirasini tozalaydi."""
    _CACHE.clear()