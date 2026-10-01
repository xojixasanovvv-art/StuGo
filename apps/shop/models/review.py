"""Mahsulot sharhlari.

Ikkita cheklov:
1. Har bir foydalanuvchi har bir mahsulotga **bitta** sharh qoldira oladi
   (`UniqueConstraint`) — takrorlashga yo'q.
2. O'z mahsulotiga sharh yozolmaydi (`clean()` da tekshiriladi).
"""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models.base import TimeStampedModel


class Review(TimeStampedModel):
    author = models.ForeignKey(
        "users.User",
        verbose_name="Muallif",
        on_delete=models.CASCADE,
        related_name="shop_reviews",
    )
    product = models.ForeignKey(
        "shop.Product",
        verbose_name="Mahsulot",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        "Baho",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField("Izoh", max_length=1000, blank=True)

    class Meta:
        verbose_name = "Sharh"
        verbose_name_plural = "Sharhlar"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["author", "product"], name="uq_review_author_product")
        ]

    def __str__(self):
        return f"{self.product_id} — {self.rating}/5"

    def clean(self):
        if self.author_id and self.product_id and self.author_id == self.product.owner_id:
            raise ValidationError("O'z mahsulotingizga sharh qoldira olmaysiz.")