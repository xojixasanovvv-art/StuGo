from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.enums import Currency, Gender
from apps.core.models.base import TimeStampedModel

MIN_IMAGES = 3
MAX_IMAGES = 15
MAX_ACTIVE_LISTINGS_BEFORE_MODERATION = 3


class ListingType(models.TextChoices):
    WHOLE_APARTMENT = "whole_apartment", "Butun kvartira"
    ROOM = "room", "Xona"
    BEDSPACE = "bedspace", "Joy"


class ListingStatus(models.TextChoices):
    DRAFT = "draft", "Qoralama"
    ACTIVE = "active", "Faol"
    ARCHIVED = "archived", "Arxivlangan"
    MODERATION = "moderation", "Moderatsiyada"
    REJECTED = "rejected", "Rad etilgan"


class Listing(TimeStampedModel):
    """TZ 4.4 — Listing (kvartira e'loni)."""

    Type = ListingType
    Status = ListingStatus

    # Klass atributlari sifatida ham ko'rsatiladi, shunda view/serializer'lar
    # `Listing.MIN_IMAGES` / `Listing.MAX_IMAGES` orqali murojaat qilishi mumkin.
    MIN_IMAGES = MIN_IMAGES
    MAX_IMAGES = MAX_IMAGES

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
        verbose_name="Egasi",
    )
    title = models.CharField("Sarlavha", max_length=200)
    description = models.TextField("Tavsif", max_length=5000)
    type = models.CharField("Turi", max_length=20, choices=ListingType.choices)
    price = models.DecimalField(
        "Narx", max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    currency = models.CharField(
        "Valyuta", max_length=3, choices=Currency.choices, default=Currency.UZS
    )
    deposit = models.DecimalField(
        "Depozit",
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    city = models.CharField("Shahar", max_length=100, db_index=True)
    district = models.CharField("Tuman", max_length=100, blank=True)
    address = models.CharField("Manzil", max_length=300, blank=True)
    lat = models.DecimalField("Kenglik", max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField("Uzunlik", max_digits=9, decimal_places=6, null=True, blank=True)
    rooms = models.PositiveSmallIntegerField("Xonalar soni", null=True, blank=True)
    area = models.PositiveSmallIntegerField("Maydoni (m²)", null=True, blank=True)
    floor = models.PositiveSmallIntegerField("Qavat", null=True, blank=True)
    total_floors = models.PositiveSmallIntegerField("Binoning qavatlari", null=True, blank=True)
    current_residents = models.PositiveSmallIntegerField(
        "Hozirgi yashovchilar", null=True, blank=True
    )
    residents_gender = models.CharField(
        "Yashovchilar jinsi",
        max_length=10,
        choices=Gender.choices,
        default=Gender.UNKNOWN,
    )
    smoking_allowed = models.BooleanField("Chekishga ruxsat", default=False)
    pets_allowed = models.BooleanField("Uy hayvonlariga ruxsat", default=False)
    available_from = models.DateField("Bo'sh bo'lish sanasi", null=True, blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=ListingStatus.choices,
        default=ListingStatus.ACTIVE,
        db_index=True,
    )
    amenities = models.ManyToManyField("housing.Amenity", blank=True, related_name="listings")

    class Meta:
        verbose_name = "E'lon"
        verbose_name_plural = "E'lonlar"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["city", "status", "-created_at"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self):
        return f"{self.title} — {self.city}"

    def clean(self):
        if self.total_floors and self.floor and self.floor > self.total_floors:
            raise ValidationError({"floor": "Qavat bino qavatlari sonidan katta bo'lmasligi kerak."})

    def save(self, *args, **kwargs):
        # TZ 5.3: ko'p e'lon joylasa — avtomatik moderatsiyaga.
        # Eslatma: bu COUNT faqat YANGI qator yaratilganda bajariladi.
        # Har bir `save()` da (masalan `archive()` da) bajarilsa, har
        # bir qator uchun alohida SELECT COUNT kiritilardi.
        adding = self._state.adding
        update_fields = kwargs.get("update_fields")
        status_changing = update_fields is None or "status" in update_fields

        if self.status == ListingStatus.ACTIVE and adding and status_changing:
            active_count = Listing.objects.filter(
                owner_id=self.owner_id, status=ListingStatus.ACTIVE
            ).count()
            if active_count >= MAX_ACTIVE_LISTINGS_BEFORE_MODERATION:
                self.status = ListingStatus.MODERATION
                if update_fields is not None:
                    kwargs["update_fields"] = list(set(update_fields) | {"status"})
        super().save(*args, **kwargs)

    def archive(self, *, save: bool = True) -> None:
        """E'lonni arxivlaydi (fizik o'chirmasdan)."""
        self.status = ListingStatus.ARCHIVED
        if save:
            self.save(update_fields=["status", "updated_at"])
