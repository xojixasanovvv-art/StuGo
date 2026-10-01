from django.conf import settings
from django.db import models

from apps.core.models.base import TimeStampedModel


class Message(TimeStampedModel):
    """TZ 4.10 — Message (xabar)."""

    conversation = models.ForeignKey(
        "chat.Conversation",
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Suhbat",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
        verbose_name="Yuborgan",
    )
    text = models.TextField("Matn", max_length=4000, blank=True)
    image = models.ImageField("Rasm", upload_to="chat/", blank=True, null=True)
    read_at = models.DateTimeField("O'qilgan vaqti", null=True, blank=True)

    class Meta:
        verbose_name = "Xabar"
        verbose_name_plural = "Xabarlar"
        ordering = ("created_at",)
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        preview = (self.text or "")[:30]
        return f"{self.sender}: {preview}" if preview else f"{self.sender}: [rasm]"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
