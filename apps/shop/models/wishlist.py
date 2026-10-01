"""Sevimlilar (yurak) — mahsulotlarni saqlash.

`Favorite` (housing) bilan tuzilishi bir xil: `(user, product)` unique
konstrainti bilan takrorlanishga yo'q.
"""

from django.db import models

from apps.core.models.base import TimeStampedModel


class WishlistItem(TimeStampedModel):
    owner = models.ForeignKey(
        "users.User",
        verbose_name="Egasi",
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        "shop.Product",
        verbose_name="Mahsulot",
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
    )

    class Meta:
        verbose_name = "Sevimli mahsulot"
        verbose_name_plural = "Sevimli mahsulotlar"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["owner", "product"], name="uq_wishlist_owner_product")
        ]

    def __str__(self):
        return f"{self.owner_id} ♥ {self.product_id}"