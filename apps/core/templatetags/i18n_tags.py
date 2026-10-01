"""Interfeys tarjimalari uchun shablon teglari.

Ishlatish:

    {% load i18n_tags %}

    <h3>{% tt "nav.housing" %}</h3>
    <input placeholder="{% tt 'auth.phonePlaceholder' %}">
    <button data-i18n="{% ttkey "common.save" %}">

Qoidalar
--------
1. Kalit katalogda yo'q bo'lsa — `KeyError` emas, **o'zbekcha matn** (yoki
   kalitning o'zi) chiqadi. Sababi: tarjima yetishmasa interfeys bo'sh joy
   bilan buzilmasin, faqat o'zbekchaga qaytadi.
2. `{% ttkey %}` — matn emas, **kalitning o'zini** chiqaradi. JS ichida
   `data-i18n="..."` uchun kerak (keyinchalik JS tarjimani kalit orqali
   topadi).
3. `{% ttvars "auth.welcome" name="Ali" %}` — `t("auth.welcome", name="Ali")`.
"""

from __future__ import annotations

from typing import Any

from django import template

from apps.core.i18n import get as translate
from apps.core.i18n import language_meta
from apps.core.i18n import load as load_catalog

register = template.Library()


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
    """Placeholder'larni to'rdirilgan tarjimani chiqaradi.

        {% ttvars "auth.welcome" name="Ali" %}  -> Xush kelibsiz, Ali
    """
    return translate(key, **params)


@register.simple_tag(name="lang_list")
def lang_list() -> list[dict[str, str]]:
    """Til tanlash uchun ro'yxat: `[{"code","name","current"}, ...]`."""
    return language_meta()