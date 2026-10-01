from django.conf import settings
from django.db import models

from apps.core.models.base import TimeStampedModel


class Report(TimeStampedModel):
    """TZ 4.11 — Report (shikoyat)."""

    class TargetType(models.TextChoices):
        USER = "user", "Foydalanuvchi"
        LISTING = "listing", "E'lon"
        MESSAGE = "message", "Xabar"

    class Status(models.TextChoices):
        OPEN = "open", "Ochiq"
        RESOLVED = "resolved", "Hal qilindi"
        DISMISSED = "dismissed", "Bekor qilindi"

    REASONS = (
        ("fake", "Soxta e'lon"),
        ("broker", "Makler"),
        ("fraud", "Firibgarlik"),
        ("abuse", "Shikoyat / kuzatuvchilik"),
        ("spam", "Spam"),
        ("minor_safety", "Voyaga yetmagan xavfsizligi"),
        ("other", "Boshqa"),
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name="Shikoyat qiluvchi",
    )
    target_type = models.CharField(
        "Nishon turi", max_length=20, choices=TargetType.choices, db_index=True
    )
    target_id = models.PositiveIntegerField("Nishon id", db_index=True)
    reason = models.CharField("Sabab", max_length=30, choices=REASONS)
    description = models.TextField("Tavsif", max_length=2000, blank=True)
    status = models.CharField(
        "Status", max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_reports",
        verbose_name="Ko'rib chiqqan",
    )
    reviewed_at = models.DateTimeField("Ko'rib chiqilgan", null=True, blank=True)

    class Meta:
        verbose_name = "Shikoyat"
        verbose_name_plural = "Shikoyatlar"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.get_target_type_display()}#{self.target_id} — {self.get_reason_display()}"


class Block(TimeStampedModel):
    """TZ 4.13 — Block (bloklash)."""

    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks",
        verbose_name="Bloklagan",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_by",
        verbose_name="Bloklangan",
    )

    class Meta:
        verbose_name = "Blok"
        verbose_name_plural = "Bloklar"
        unique_together = ("blocker", "blocked")
        # Pagination uchun tartib SHART: `UnorderedObjectListWarning`
        # aks holda har sahifada turli natija beradi.
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["blocker", "-created_at"])]

    def __str__(self):
        return f"{self.blocker} ✕ {self.blocked}"
