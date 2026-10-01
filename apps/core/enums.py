from django.db import models


class Currency(models.TextChoices):
    UZS = "UZS", "So'm"
    USD = "USD", "Dollar"


class Gender(models.TextChoices):
    MALE = "male", "Erkak"
    FEMALE = "female", "Ayol"
    UNKNOWN = "unknown", "Ko'rsatilmagan"
