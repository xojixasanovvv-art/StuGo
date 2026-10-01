from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models.base import TimeStampedModel


class MatchStatus(models.TextChoices):
    PENDING = "pending", "Kutilmoqda"
    ACCEPTED = "accepted", "Qabul qilindi"
    REJECTED = "rejected", "Rad etildi"


class Match(TimeStampedModel):
    """TZ 4.8 — Match (moslik).

    JUFTLIK NORMALIZATSIYASI: `user_a_id < user_b_id` doimiy qoidasi.
    Aks holda bitta juftlik ikki marta yoziladi (A->B va B->A), va
    `unique_together` ittifoqlikni ushlab turmaydi.
    """

    Status = MatchStatus

    user_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="matches_initiated",
        verbose_name="Foydalanuvchi A",
    )
    user_b = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="matches_received",
        verbose_name="Foydalanuvchi B",
    )
    score = models.PositiveSmallIntegerField("Moslik foizi", default=0)
    status = models.CharField(
        "Status", max_length=20, choices=MatchStatus.choices, default=MatchStatus.PENDING
    )

    class Meta:
        verbose_name = "Moslik"
        verbose_name_plural = "Mosliklar"
        unique_together = ("user_a", "user_b")
        ordering = ("-score", "-created_at")
        constraints = [
            models.CheckConstraint(condition=Q(user_a__lt=F("user_b")), name="match_user_a_lt_user_b"),
        ]
        indexes = [models.Index(fields=["user_a", "status"]), models.Index(fields=["user_b", "status"])]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._normalize_pair()

    def save(self, *args, **kwargs):
        self._normalize_pair()
        super().save(*args, **kwargs)

    def _normalize_pair(self) -> None:
        """Juftlikni `user_a < user_b` tartibiga keltiradi."""
        a, b = self.user_a_id, self.user_b_id
        if a is not None and b is not None and a > b:
            self.user_a_id, self.user_b_id = b, a

    @classmethod
    def normalize_ids(cls, user1_id, user2_id) -> tuple[int, int]:
        """Ikkala yo'nalish uchun bir xil natija beradigan juftlik id'lari."""
        return (user1_id, user2_id) if user1_id < user2_id else (user2_id, user1_id)

    @classmethod
    def for_users(cls, user1, user2, **defaults):
        """Juftlikni topadi yoki normallangan tartibda yaratadi.

        Eslatma: avvalgi kod `get_or_create(user_a=request.user, ...)` deb
        yozardi, shuning uchun qarama-qarshi tomondan so'rov kelganda
        `unique_together` ga tegib, ikkinchi qator paydo bo'lardi.
        """
        a_id, b_id = cls.normalize_ids(user1.id, user2.id)
        match, created = cls.objects.get_or_create(
            user_a_id=a_id, user_b_id=b_id, defaults=defaults
        )
        return match, created

    def partner_for(self, user) -> object:
        """Berilgan foydalanuvchi uchun 'boshqa' tomonni qaytaradi."""
        return self.user_b if self.user_a_id == user.id else self.user_a

    def __str__(self):
        return f"{self.user_a} ↔ {self.user_b} ({self.score}%)"