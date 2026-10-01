from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    label = "users"
    verbose_name = "Foydalanuvchilar va verifikatsiya"

    def ready(self):
        from apps.users import signals  # noqa: F401
