from django.conf import settings
from django.db import models

from apps.core.enums import Gender
from apps.core.models.base import TimeStampedModel


class RoommateProfile(TimeStampedModel):
    """TZ 4.7 — Roommate anketa."""

    class SleepSchedule(models.TextChoices):
        EARLY = "early", "Erta uxlayman"
        LATE = "late", "Kech uxlayman"
        FLEXIBLE = "flexible", "Turlicha"

    class Cleanliness(models.TextChoices):
        VERY_TIDY = "very_tidy", "Juda toza"
        TIDY = "tidy", "Toza"
        AVERAGE = "average", "O'rtacha"
        RELAXED = "relaxed", "Etibormayman"

    class LookingFor(models.TextChoices):
        HAVE_PLACE = "have_place", "Menda kvartira bor, sherik kerak"
        LOOKING = "looking", "Kvartira ham, sherik ham qidiryapman"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="roommate_profile",
        verbose_name="Foydalanuvchi",
    )
    looking_for = models.CharField(
        "Yo'nalish", max_length=20, choices=LookingFor.choices, default=LookingFor.LOOKING
    )
    budget_min = models.DecimalField(
        "Byudjet (min)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    budget_max = models.DecimalField(
        "Byudjet (max)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    city = models.CharField("Shahar", max_length=100, db_index=True)
    district = models.CharField("Tuman", max_length=100, blank=True)
    move_in_date = models.DateField("Kirish sanasi", null=True, blank=True)
    gender_pref = models.CharField(
        "Jins afzalligi", max_length=10, choices=Gender.choices, default=Gender.UNKNOWN
    )
    sleep_schedule = models.CharField(
        "Uyqu tartibi", max_length=20, choices=SleepSchedule.choices, default=SleepSchedule.FLEXIBLE
    )
    cleanliness = models.CharField(
        "Tozalik darajasi", max_length=20, choices=Cleanliness.choices, default=Cleanliness.AVERAGE
    )
    smoking = models.BooleanField("Chekish", default=False)
    guests_ok = models.BooleanField("Mehmon chaqirish", default=True)
    pets = models.BooleanField("Uy hayvoni", default=False)
    about = models.TextField("O'zim haqimda", max_length=2000, blank=True)
    is_active = models.BooleanField("Faol anketa", default=True)

    class Meta:
        verbose_name = "Roommate anketa"
        verbose_name_plural = "Roommate anketalari"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} — {self.city}"
