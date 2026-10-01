from django.conf import settings
from django.db import models

from apps.core.models.base import TimeStampedModel


class Conversation(TimeStampedModel):
    """TZ 4.10 — Conversation (1-ga-1 suhbat).

    `participants` M2M saqlanadi (frontend uchun qulay), lekin unikal
    juftlik `user_low`/`user_high` orqali qo'llab-quvvatlanadi. Aks holda
    ikki parallel `POST /conversations/` so'rovi bitta suhbat o'rniga
    ikkita suhbat yaratib qo'yardi.
    """

    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="conversations",
        verbose_name="Ishtirokchilar",
    )
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_low",
        verbose_name="Ishtirokchi (kichik id)",
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations_high",
        verbose_name="Ishtirokchi (katta id)",
    )

    class Meta:
        verbose_name = "Suhbat"
        verbose_name_plural = "Suhbatlar"
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["user_low", "user_high"], name="conversation_unique_pair"
            )
        ]
        indexes = [models.Index(fields=["user_low", "-updated_at"]), models.Index(fields=["user_high", "-updated_at"])]

    @classmethod
    def normalize_ids(cls, user1_id, user2_id) -> tuple[int, int]:
        return (user1_id, user2_id) if user1_id < user2_id else (user2_id, user1_id)

    @classmethod
    def get_or_create_pair(cls, user1, user2):
        """Juftlik uchun suhbatni qaytaradi yoki atomik yaratadi.

        Qaytaradi: (conversation, created)
        """
        low_id, high_id = cls.normalize_ids(user1.id, user2.id)
        # `get_or_create` unique constraint bilan birga ishlaydi: parallel
        # so'rovlarda IntegrityError ichida ushlab, mavjud yozuvni qaytaradi.
        conv, created = cls.objects.get_or_create(
            user_low_id=low_id,
            user_high_id=high_id,
        )
        if created:
            conv.participants.set([low_id, high_id])
        return conv, created

    def partner_for(self, user):
        """Berilgan foydalanuvchidan tashqaridagi ishtirokchi."""
        if self.user_low_id == user.id:
            return self.user_high
        return self.user_low

    def __str__(self):
        return f"Suhbat: {self.user_low} ↔ {self.user_high}"