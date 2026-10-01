"""Interfeys tarjimalari uchun shablon teglari.

Ishlatish:

    {% load i18n_tags %}

    <h3>{% tt "nav.housing" %}</h3>
    <input placeholder="{% tt 'auth.phonePlaceholder' %}">
    <option>{% tt "housing.allCities" %}</option>

Qoidalar
--------
1. Kalit katalogda yo'q bo'lsa — `KeyError` emas, **o'zbekcha matn**
   (yoki kalitning o'zi) chiqadi. Sababi: tarjima yetishmasa interfeys
   bo'sh joy bilan buzilmasin, faqat o'zbekchaga qaytadi.
2. `{% ttkey %}` — matn emas, **kalitning o'zini** chiqaradi. JS ichida
   `data-i18n="..."` uchun kerak (keyinchalik JS tarjimani kalit orqali
   topadi).
3. `{% ttvars "greeting" name="Ali" %}` — `t("greeting", name="Ali")`.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.utils.safestring import mark_safe

from apps.core.i18n import get as translate
from apps.core.i18n import load as load_catalog

register = template.Library()


def _fallback(key: str) -> str:
    """Kalit katalogda yo'q bo'lsa nima qaytarish kerak.

    Avval o'zbekcha katalogni tekshiramiz (boshqa til tanlangan bo'lishi
    mumkin), keyin kalitning o'zini qaytaramiz — bo'sh joy ko'rsatgandan
    ko'ra kalitni ko'rsatish yaxshi, chunki muammoni darhol aniqlash mumkin.
    """
    return load_catalog("uz").get(key, key)


@register.simple_tag(name="tt")
def tt(key: str, **params: Any) -> str:
    """Tarjimani chiqaradi.

        {% tt "common.save" %}                     -> Saqlash
        {% tt "auth.welcome" name="Ali" %}          -> Xush kelibsiz, Ali
    """
    return translate(key, **params)


@register.simple_tag(name="ttkey")
def ttkey(key: str) -> str:
    """Kalitning o'zini chiqaradi (JS uchun `data-i18n` atributlari).

        <button data-i18n="{% ttkey "common.save" %}">
    """
    return key


@register.simple_tag(name="ttvars")
def ttvars(key: str, **params: Any) -> str:
    """Placeholder'larni to'ldirib tarjimani chiqaradi.

        {% ttvars "auth.welcome" name="Ali" %}  -> Xush kelibsiz, Ali
    """
    return translate(key, **params)


@register.simple_tag(takes_context=True)
def active_lang(context) -> str:
    """Joriy til kodi (`uz` / `ru` / `en`)."""
    lang = getattr(context.get("request"), "LANGUAGE_CODE", None)
    return lang or "uz"


@register.simple_tag(name="lang_list")
def lang_list() -> list[dict[str, str]]:
    """Til tanlash uchun ro'yxat: `[{"code","name","current"}, ...]`.

    Template'da takror ishlatish o'rniga shu ro'yxatni bir marta berib,
    JS uni qayta ishlatadi.
    """
    from apps.core.i18n import language_meta

    return language_meta()