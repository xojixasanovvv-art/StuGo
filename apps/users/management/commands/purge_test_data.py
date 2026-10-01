"""E2E sinovdan qolgan vaqtinchalik ma'lumotlarni tozalaydi.

Ishga tushirish:

    python manage.py purge_test_data

Faqat e2e_test.py tomonidan yaratilgan foydalanuvchilar (telefoni
`+998909...` bilan boshlanadi, e-maili `stugo*@tuit.uz`) va ularning
e'lonlari o'chiriladi. Qo'lda yaratgan ma'lumotlaringiz tegilmaydi.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "E2E sinov qoldiqlarini (vaqtinchalik foydalanuvchi va e'lonlar) o'chiradi."

    def handle(self, *args, **options):
        qs = User.objects.filter(email__startswith="stugo") | User.objects.filter(
            phone__regex=r"^\+998909\d+$"
        )
        users = list(qs.distinct())
        if not users:
            self.stdout.write("Tozalash uchun ma'lumot topilmadi.")
            return

        # Listing va chat `on_delete=CASCADE`, shuning uchun user o'chirilishi
        # ularni ham avtomatik olib tashlaydi.
        emails = [u.email for u in users if u.email]
        for u in users:
            u.delete()
        self.stdout.write(self.style.SUCCESS(f"{len(users)} ta foydalanuvchi va ularga bog'liq ma'lumotlar o'chirildi:"))
        for e in emails:
            self.stdout.write(f"  {e}")