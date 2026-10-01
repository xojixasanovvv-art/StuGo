from django.db import models


class TimeStampedModel(models.Model):
    """created_at / updated_at maydonli abstrakt asos."""

    created_at = models.DateTimeField("Yaratilgan", auto_now_add=True)
    updated_at = models.DateTimeField("Yangilangan", auto_now=True)

    class Meta:
        abstract = True
