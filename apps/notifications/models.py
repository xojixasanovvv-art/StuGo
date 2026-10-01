from django.conf import settings
from django.db import models

from apps.core.models.base import TimeStampedModel


class NotificationType(models.TextChoices):
    NEW_MESSAGE = "new_message", "Yangi xabar"
    VERIFICATION_RESULT = "verification_result", "Verifikatsiya natijasi"
    LISTING_INTEREST = "listing_interest", "E'longa qiziqish"
    NEW_MATCH = "new_match", "Yangi mos roommate"


class Notification(TimeStampedModel):
    """TZ 4.12 — Notification."""

    Type = NotificationType

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Foydalanuvchi",
    )
    type = models.CharField("Turi", max_length=30, choices=NotificationType.choices, db_index=True)
    payload = models.JSONField("Ma'lumot", default=dict, blank=True)
    is_read = models.BooleanField("O'qilgan", default=False, db_index=True)
    read_at = models.DateTimeField("O'qilgan vaqti", null=True, blank=True)

    class Meta:
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]

    def __str__(self):
        return f"{self.user_id} — {self.type}"
