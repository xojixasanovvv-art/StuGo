from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from apps.core.enums import Gender


class UserManager(BaseUserManager):
    """Username o'rniga telefon raqam bilan ishlaydigan menejer."""

    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        if not phone:
            raise ValueError("Telefon raqam kiritilishi shart.")
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password) if password else user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser is_staff=True bo'lishi kerak.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser is_superuser=True bo'lishi kerak.")
        return self._create_user(phone, password, **extra_fields)


class Role(models.TextChoices):
    STUDENT = "student", "Talaba"
    LANDLORD = "landlord", "Kvartira egasi"
    PARENT = "parent", "Ota-ona"
    MODERATOR = "moderator", "Moderator"
    ADMIN = "admin", "Admin"


class User(AbstractUser):
    """TZ 4.1 — User: telefon raqam asosiy login. Username majburiy emas."""

    objects = UserManager()

    username = None  # telefon raqam asosiy identifikator
    phone = models.CharField("Telefon raqam", max_length=20, unique=True, db_index=True)
    email = models.EmailField("Email", blank=True)
    role = models.CharField(
        "Rol", max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True
    )
    is_verified = models.BooleanField("Verifikatsiya qilingan", default=False)
    gender = models.CharField(
        "Jins", max_length=10, choices=Gender.choices, default=Gender.UNKNOWN
    )

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Foydalanuvchi"
        verbose_name_plural = "Foydalanuvchilar"

    def __str__(self):
        return f"{self.phone} ({self.get_role_display()})"
