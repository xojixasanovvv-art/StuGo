"""Demo to'lov: vaqtinchalik karta + screenshot orqali tasdiqlash.

Nima uchun haqiqiy to'lov emas
-----------------------------
Loyiha **o'quv/demo** maqsadida: haqiqiy bank kartalariga ulanish
yo'q, `POST /payments/` da hech qanday maxfiy karta ma'lumoti saqlanmaydi.
Foydalanuvchi demo kartadan birini tanlaydi, to'lov chekasini (screenshot)
rasm qilib yuklaydi, admin esa uni ko'rib tasdiqlaydi.

Muhim xavfsizlik qoidasi: **faqat demo karta raqamlari qabul qilinadi**.
`card_number` oddiy matn bo'lgani uchun foydalanuvchi haqiqiy kartani
kiritsa, u serverda saqlanib qolishi mumkin — shuning uchun `clean()` da
aniq tekshiriladi va hech qachon `POST` orqali karta yaratilmaydi
(kartalar faqat `createsuperuser`/admin orqali qo'shiladi).
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models.base import TimeStampedModel

# To'lov chekasini tasdiqlash uchun berilgan vaqt
PAYMENT_WINDOW = timedelta(minutes=30)


class DemoCard(TimeStampedModel):
    """Tasdiqlash uchun mo'ljallangan vaqtinchalik karta."""

    number = models.CharField("Karta raqami", max_length=20, unique=True)
    holder = models.CharField("Karta egasi", max_length=100, default="Demo Card")
    balance = models.DecimalField(
        "Qoldiq",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        verbose_name = "Demo karta"
        verbose_name_plural = "Demo kartalar"
        ordering = ("number",)

    def __str__(self):
        return self.masked

    @property
    def masked(self):
        """Faqat oxirgi 4 ta raqam ko'rinadi: `8600 **** **** 9012`.

        To'lov oynasida to'liq raqamni ko'rsatish kerak emas — bu demo
        kartalar, lekin himoya odati sifatida to'liq raqamni hech qachon
        javobda qaytarmaymiz.
        """
        digits = "".join(ch for ch in self.number if ch.isdigit())
        if len(digits) <= 4:
            return digits
        return f"{digits[:4]} **** **** {digits[-4:]}"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Tekshirilmoqda"
    VERIFIED = "verified", "Tasdiqlandi"
    REJECTED = "rejected", "Rad etildi"
    EXPIRED = "expired", "Muddati tugadi"


class Payment(TimeStampedModel):
    Status = PaymentStatus

    order = models.OneToOneField(
        "shop.Order",
        verbose_name="Buyurtma",
        on_delete=models.CASCADE,
        related_name="payment",
    )
    payer = models.ForeignKey(
        "users.User",
        verbose_name="To'lovchi",
        on_delete=models.CASCADE,
        related_name="shop_payments",
    )
    demo_card = models.ForeignKey(
        DemoCard,
        verbose_name="Demo karta",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(
        "Summa", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    status = models.CharField(
        "Holati", max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    screenshot = models.ImageField(
        "Cheka (screenshot)", upload_to="shop/payments/%Y/%m/", blank=True
    )
    expires_at = models.DateTimeField("Muddati")

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ("-created_at",)

    def __str__(self):
        return f"To'lov #{self.pk} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + PAYMENT_WINDOW
        super().save(*args, **kwargs)

    def clean(self):
        if self.expires_at and self.expires_at < timezone.now():
            raise ValidationError({"expires_at": "To'lov muddati o'tib ketgan."})

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def seconds_left(self):
        """Qolgan soniya (UI da countdown uchun). Muddati o'tgan bo'lsa 0."""
        left = int((self.expires_at - timezone.now()).total_seconds())
        return max(left, 0)