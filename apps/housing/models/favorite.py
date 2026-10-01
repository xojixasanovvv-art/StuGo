from django.conf import settings
from django.db import models

from apps.core.models.base import TimeStampedModel


class Favorite(TimeStampedModel):
    """TZ 4.9 — Favorite (sevimlilar)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="Foydalanuvchi",
    )
    listing = models.ForeignKey(
        "housing.Listing",
        on_delete=models.CASCADE,
        related_name="favorited_by",
        verbose_name="E'lon",
    )

    class Meta:
        verbose_name = "Sevimli"
        verbose_name_plural = "Sevimlilar"
        unique_together = ("user", "listing")

    def __str__(self):
        return f"{self.user} → {self.listing}"
