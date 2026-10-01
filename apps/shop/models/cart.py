"""Savat (cart) va uning bandlari.

Har bir foydalanuvchida **bitta** savat bor: `Cart.owner` OneToOne. Bu view
qatlamida `get_or_create` bilan avtomatik yaratiladi, shuning uchun frontend'ga
"savatni yaratish" alohida so'rovi kerak emas.

Narx `CartItem` da **saqlanmaydi** — u `Product.price` dan hisoblanadi. Aks
holda narx o'zgarganda savatdagi eski narx ko'rinib qoladi va xato bo'lad
(foydalanuvchi boshqa narxga to'laydi).
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import TimeStampedModel
from apps.shop.models.product import Product


class Cart(TimeStampedModel):
    owner = models.OneToOneField(
        "users.User",
        verbose_name="Egali",
        on_delete=models.CASCADE,
        related_name="cart",
    )

    class Meta:
        verbose_name = "Savat"
        verbose_name_plural = "Savatlar"

    def __str__(self):
        return f"Savat #{self.pk}"

    @property
    def total_count(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def total_price(self):
        """Jami narx — bandlar bo'sh bo'lsa 0 (None emas)."""
        total = sum((item.line_total for item in self.items.all()), start=0)
        return total

    @property
    def is_empty(self):
        return not self.items.exists()


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(Cart, verbose_name="Savat", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product,
        verbose_name="Mahsulot",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField("Miqdor", default=1)

    class Meta:
        verbose_name = "Savat bandi"
        verbose_name_plural = "Savat bandlari"
        constraints = [
            models.UniqueConstraint(fields=["cart", "product"], name="uq_cart_product")
        ]

    def __str__(self):
        return f"{self.product_id} x{self.quantity}"

    def clean(self):
        if self.quantity is not None and self.quantity < 1:
            raise ValidationError({"quantity": "Miqdor kamida 1 bo'lishi kerak."})

    @property
    def line_total(self):
        return self.product.price * self.quantity