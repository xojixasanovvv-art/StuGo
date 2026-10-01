"""Kategoriya (masalan: Elektronika, Kiyim, Kitoblar).

Kategoriyalar 2 darajada bo'lishi mumkin: `parent` orqali kichik bo'limlar
asosiy bo'lim ostiga yig'iladi (Elektronika > Telefonlar).
"""

from django.db import models
from django.utils.text import slugify

from apps.core.models.base import TimeStampedModel


class Category(TimeStampedModel):
    name = models.CharField("Nomi", max_length=120, unique=True)
    slug = models.SlugField("Slug", max_length=140, unique=True, blank=True)
    description = models.TextField("Tavsif", blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="Yuqori kategoriya",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField("Faol", default=True)
    order = models.PositiveIntegerField("Tartib", default=0)

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"
        ordering = ("order", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)