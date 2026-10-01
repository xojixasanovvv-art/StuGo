from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.models.profile import Profile
from apps.users.models.user import User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance: User, created: bool, **kwargs):
    """Har bir yangi foydalanuvchi uchun avtomatik profil yaratadi."""
    if created:
        Profile.objects.get_or_create(user=instance)
