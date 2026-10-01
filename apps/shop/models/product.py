"""Mahsulot va uning rasmlari.

Mahsulot sifati va narxi bo'yicha tekshiruvlar `clean()` da bajariladi —
chunki narx manfiy bo'lishi yoki "nom" maydoniga notebook yozilishi
ma'nosiz ma'lumot kiritishga to'sqinlik qilmasligi kerak.

Rasm cheklovlari: 1..8 ta, JPG/PNG/WEBP, 5 MB gacha.
"""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models.base import TimeStampedModel

MIN_IMAGES = 1
MAX_IMAGES = 8
MAX_IMAGE_MB = 5


class Product(TimeStampedModel):
    MIN_IMAGES = MIN_IMAGES
    MAX_IMAGES = MAX_IMAGES

    class Condition(models.TextChoices):
        NEW = "new", "Yangi"
        LIKE_NEW = "like_new", "Yangidek"
        GOOD = "good", "Yaxshi"
        FAIR = "fair", "O'rtacha"
        USED = "used", "Ishlatilgan"

    owner = models.ForeignKey(
        "users.User",
        verbose_name="Sotuvchi",
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        "shop.Category",
        verbose_name="Kategoriya",
        on_delete=models.PROTECT,
        related_name="products",
    )
    title = models.CharField("Sarlavha", max_length=200)
    description = models.TextField("Tavsif", max_length=5000)
    price = models.DecimalField(
        "Narx",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    stock = models.PositiveIntegerField("Qoldiq", default=1)
    condition = models.CharField(
        "Holati", max_length=20, choices=Condition.choices, default=Condition.USED
    )
    is_active = models.BooleanField("Faol", default=True)

    class Meta:
        verbose_name = "Mahsulot"
        verbose_name_plural = "Mahsulotlar"
        ordering = ("-created_at",)

    def __str__(self):
        return self.title

    def clean(self):
        if self.price is not None and self.price < 0:
            raise ValidationError({"price": "Narx manfiy bo'lishi mumkin emas."})
        if self.stock is not None and self.stock < 0:
            raise ValidationError({"stock": "Qoldiq manfiy bo'lishi mumkin emas."})

    @property
    def main_image(self):
        """Birinchi rasm (kartalar uchun). `None` bo'lsa frontend placeholder
        ko'rsatadi."""
        return self.images.order_by("position", "id").first()


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        verbose_name="Mahsulot",
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField("Rasm", upload_to="shop/products/%Y/%m/")
    position = models.PositiveSmallIntegerField("Tartib", default=0)
    created_at = models.DateTimeField("Yaratilgan", auto_now_add=True)

    class Meta:
        verbose_name = "Mahsulot rasmi"
        verbose_name_plural = "Mahsulot rasmlari"
        ordering = ("position", "id")

    def __str__(self):
        return f"{self.product_id} - rasm #{self.pk}"