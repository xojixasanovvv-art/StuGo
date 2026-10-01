from django.conf import settings
from django.db import models

from apps.core.models.base import TimeStampedModel


class VerificationMethod(models.TextChoices):
    UNIVERSITY_EMAIL = "university_email", "Universitet email"
    DOCUMENT = "document", "Talabalik hujjati + selfi"
    APPLICANT = "applicant", "Abituriyent hujjati"


class VerificationStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    APPROVED = "approved", "Tasdiqlangan"
    REJECTED = "rejected", "Rad etilgan"


class VerificationRequest(TimeStampedModel):
    """TZ 4.3 — Verifikatsiya so'rovi."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_requests",
        verbose_name="Foydalanuvchi",
    )
    method = models.CharField("Usul", max_length=30, choices=VerificationMethod.choices)
    document_image = models.ImageField(
        "Hujjat rasmi", upload_to="verification/documents/", blank=True, null=True
    )
    selfie = models.ImageField(
        "Selfi", upload_to="verification/selfies/", blank=True, null=True
    )
    university_email = models.EmailField("Universitet emaili", blank=True)
    status = models.CharField(
        "Status",
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_verifications",
        verbose_name="Ko'rib chiqqan",
    )
    reject_reason = models.CharField("Rad etish sababi", max_length=300, blank=True)

    class Meta:
        verbose_name = "Verifikatsiya so'rovi"
        verbose_name_plural = "Verifikatsiya so'rovlari"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} — {self.get_method_display()} ({self.status})"
