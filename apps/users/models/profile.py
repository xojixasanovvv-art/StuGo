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

    class Meta:
        verbose_name = "Profil"
        verbose_name_plural = "Profillar"

    def __str__(self):
        return self.full_name or str(self.user)
