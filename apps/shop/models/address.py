"""Yetkazib berish manzili.

Foydalanuvchilar bir nechta manzil saqlashi mumkin, lekin bittasi
`is_default=True` bo'ladi (`clean()` va `save()` orqali saqlanadi).
"""

from django.db import models

from apps.core.models.base import TimeStampedModel


class Address(TimeStampedModel):
    owner = models.ForeignKey(
        "users.User",
        verbose_name="Egasi",
        on_delete=models.CASCADE,
        related_name="shop_addresses",
    )
    title = models.CharField("Nomi", max_length=80, default="Uy")
    city = models.CharField("Shahar", max_length=100)
    district = models.CharField("Tuman", max_length=100, blank=True)
    street = models.CharField("Ko'cha", max_length=200)
    house = models.CharField("Uy", max_length=20)
    is_default = models.BooleanField("Asosiy", default=False)

    class Meta:
        verbose_name = "Manzil"
        verbose_name_plural = "Manzillar"
        ordering = ("-is_default", "-created_at")

    def __str__(self):
        return f"{self.city}, {self.street} {self.house}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Faqat bitta asosiy manzil bo'lishi kerak — boshqalarini o'chiramiz
        if self.is_default:
            Address.objects.filter(owner=self.owner).exclude(pk=self.pk).update(is_default=False)
        elif not Address.objects.filter(owner=self.owner, is_default=True).exists():
            # Birinchi manzil avtomatik asosiy bo'ladi
            Address.objects.filter(pk=self.pk).update(is_default=True)
            self.is_default = True

    @property
    def full(self):
        parts = [self.city, self.district, self.street, self.house]
        return ", ".join(p for p in parts if p)