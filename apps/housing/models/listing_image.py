from django.db import models

from apps.core.models.base import TimeStampedModel


class ListingImage(TimeStampedModel):
    """TZ 4.5 — ListingImage."""

    listing = models.ForeignKey(
        "housing.Listing",
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="E'lon",
    )
    image = models.ImageField("Rasm", upload_to="listings/")
    order = models.PositiveSmallIntegerField("Tartib", default=0)

    class Meta:
        verbose_name = "E'lon rasmi"
        verbose_name_plural = "E'lon rasmlari"
        ordering = ("order", "created_at")

    def __str__(self):
        return f"#{self.order} — {self.listing.title}"
