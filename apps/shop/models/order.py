"""Buyurtma va uning bandlari.

Muhim qoida: **narx `OrderItem` da snapshot sifatida saqlanadi**. Sababi —
savatdan keyin mahsulot narxi o'zgarsa, foydalanuvchi yana o'sha eski narx
bo'yicha to'lashni kutadi (buyurtma "muqofazalangan" bo'lishi kerak).
"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import TimeStampedModel


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    PAID = "paid", "To'langan"
    SHIPPED = "shipped", "Yuborilgan"
    DELIVERED = "delivered", "Yetkazilgan"
    CANCELLED = "cancelled", "Bekor qilingan"


class Order(TimeStampedModel):
    Status = OrderStatus

    buyer = models.ForeignKey(
        "users.User",
        verbose_name="Xaridor",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    status = models.CharField(
        "Holati", max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    total_price = models.DecimalField("Jami", max_digits=12, decimal_places=2, default=0)
    address = models.ForeignKey(
        "shop.Address",
        verbose_name="Manzil",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    class Meta:
        verbose_name = "Buyurtma"
        verbose_name_plural = "Buyurtmalar"
        ordering = ("-created_at",)

    def __str__(self):
        return f"Buyurtma #{self.pk}"

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    def recompute_total(self, save=False):
        """Bandlar asosida jami narxni qayta hisoblaydi.

        Har safar chaqirilmaydi — faqat bandlar o'zgarganda (`add_item`,
        `remove_item`, tasdiqlash). Aks holda har bir `save()` da 1 ta
        `SUM()` query bajariladi.
        """
        total = sum((item.line_total for item in self.items.all()), start=0)
        self.total_price = total
        if save:
            self.save(update_fields=["total_price", "updated_at"])
        return total


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name="Buyurtma", on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "shop.Product",
        verbose_name="Mahsulot",
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items",
    )
    # Snapshot: nomi ham, narxi ham o'zgarishi mumkin — buyurtma esa o'zgarmaydi
    title_snapshot = models.CharField("Nom (snapshot)", max_length=200)
    price_at_order = models.DecimalField("Narx (snapshot)", max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField("Miqdor", default=1)

    class Meta:
        verbose_name = "Buyurtma bandi"
        verbose_name_plural = "Buyurtma bandlari"

    def __str__(self):
        return f"{self.title_snapshot} x{self.quantity}"

    def clean(self):
        if self.price_at_order is not None and self.price_at_order < 0:
            raise ValidationError({"price_at_order": "Narx manfiy bo'lishi mumkin emas."})

    @property
    def line_total(self):
        return self.price_at_order * self.quantity