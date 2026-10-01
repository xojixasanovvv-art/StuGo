from django.db import models


class Amenity(models.Model):
    """TZ 4.6 — Amenity (jihozlar: wifi, kir yuvish mashinasi va h.k.)."""

    name = models.CharField("Nomi", max_length=100, unique=True)
    icon = models.CharField("Ikonka", max_length=50, blank=True)

    class Meta:
        verbose_name = "Jihoz"
        verbose_name_plural = "Jihozlar"
        ordering = ("name",)

    def __str__(self):
        return self.name
