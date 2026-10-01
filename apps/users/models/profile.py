from django.conf import settings
from django.db import models

from apps.core.enums import Gender
from apps.core.models.base import TimeStampedModel


class Profile(TimeStampedModel):
    """TZ 4.2 — Profile: qo'shimcha shaxsiy ma'lumotlar."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Foydalanuvchi",
    )
    full_name = models.CharField("To'liq ism", max_length=150, blank=True)
    avatar = models.ImageField("Avatar", upload_to="avatars/", blank=True, null=True)
    birth_date = models.DateField("Tug'ilgan sana", null=True, blank=True)
    gender = models.CharField(
        "Jins", max_length=10, choices=Gender.choices, default=Gender.UNKNOWN
    )
    city = models.CharField("Shahar", max_length=100, blank=True)
    university = models.CharField("Universitet", max_length=200, blank=True)
    faculty = models.CharField("Fakultet", max_length=200, blank=True)
    course = models.PositiveSmallIntegerField("Kurs", null=True, blank=True)
    bio = models.TextField("Bio", max_length=1000, blank=True)
    languages = models.CharField("Tillar", max_length=200, blank=True)
    interests = models.CharField("Qiziqishlar", max_length=300, blank=True)

    # --- Telegram bilan bog'lanish -----------------------------------
    # Bot orqali bog'langanda to'ldiriladi. `telegram_id` — Telegram
    # bergan raqamli (64-bit) foydalanuvchi identifikatori; shuning uchun
    # `PositiveBigIntegerField` emas, `BigIntegerField` ishlatiladi
    # (Telegram id 32-bit chegarasini oshgan).
    #
    # `unique=True` + `null=True`: ko'p foydalanuvchilar bog'lanmagan
    # bo'lishi mumkin, lekin bitta Telegram hisobi FAQAT bitta
    # StuGo hisobiga ulanishi mumkin — aks holda bir odam ikki hisob
    # bilan kirib, xabarlar chalkashadi.
    telegram_id = models.BigIntegerField(
        "Telegram ID", unique=True, null=True, blank=True, db_index=True
    )
    telegram_username = models.CharField(
        "Telegram username", max_length=64, blank=True
    )
    telegram_linked_at = models.DateTimeField("Telegram bog'landi", null=True, blank=True)

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profillar"

    def __str__(self):
        return self.full_name or str(self.user)

    @property
    def is_telegram_linked(self) -> bool:
        """Telegram bilan bog'langanmi?"""
        return self.telegram_id is not None
