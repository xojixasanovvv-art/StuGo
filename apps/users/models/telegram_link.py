"""TZ 4.2 — Telegram bog'lanish kodi (bir martalik).

Nima uchun baza, cache emas
---------------------------
Sayt (daphne) va bot (`manage.py telegram_bot`) — **ikki alohida
jarayon**. Django'ning `LocMemCache` backendi har bir jarayonda
alohida xotirada ishlaydi: saytda yaratilgan kodni bot ko'ra olmaydi.
Lokal rivojlashda Redis yo'q, shuning uchun kodni **bazada** saqlaymiz.

Bu yechim yana ikki foyda beradi:
  * server'ni qayta ishga tushirsangiz ham kod o'lib ketmaydi;
  * kodlarni SQL orqali ko'rish va tozalash mumkin (`purge_test_data`).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import TimeStampedModel


class TelegramLinkCode(TimeStampedModel):
    """Botga yuboriladigan 8 xonali bir martalik kod."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="telegram_link_codes",
        verbose_name="Foydalanuvchi",
    )
    # `unique=True` — kod takrorlanmaydi. `secrets` bilan generatsiya
    # qilinadi (8 xonali = 10^8 variant), `max_length` kichik bo'lishi
    # uni ixcham saqlashga imkon beradi va skanlashda qulay.
    code = models.CharField("Kod", max_length=16, unique=True, db_index=True)
    expires_at = models.DateTimeField("Muddati")
    # Noto'g'ri urinishlar soni — brute force'ni sekinlashtiradi.
    attempts = models.PositiveSmallIntegerField("Urinishlar", default=0)
    # Kod qachon ishlatilgani. `NULL` = hali ishlatilmagan.
    used_at = models.DateTimeField("Ishlatilgan", null=True, blank=True)

    class Meta:
        verbose_name = "Telegram bog'lanish kodi"
        verbose_name_plural = "Telegram bog'lanish kodlari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.user_id})"

    # ------------------------------------------------------------------
    @property
    def is_valid(self) -> bool:
        """Ishlatilmagan va muddati tugamaganmi?"""
        return self.used_at is None and self.expires_at > timezone.now()
