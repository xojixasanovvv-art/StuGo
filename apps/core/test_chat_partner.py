"""Suhbat ro'yxatidagi sherik ma'lumotlari.

Muammo: `ConversationSerializer.get_partner()` faqat maskalangan telefon
qaytarardi, shuning uchun frontend ro'yxatda "+9989*****68" ko'rsatardi —
foydalanuvchi uchun tushunarsiz. Endi `full_name` va `avatar` ham
qaytariladi (frontend `renderChat`/`partnerName` allaqachon shularni
 kutaydi).

Bu test shu maydonlarning kelishini tekshiradi.
"""

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.chat.models import Conversation
from apps.users.models import Profile

User = get_user_model()


@override_settings(DEBUG=True, ALLOWED_HOSTS=["testserver", "localhost"])
class ConversationPartnerTests(APITestCase):
    def setUp(self):
        self.alisher = User.objects.create_user(phone="+99890111111", password="x")
        self.zarnigor = User.objects.create_user(phone="+99890222222", password="x")
        Profile.objects.filter(user=self.alisher).update(full_name="Alisher Karimov")
        Profile.objects.filter(user=self.zarnigor).update(full_name="Zarnigor Aliyeva")
        self.conv = Conversation.get_or_create_pair(self.alisher, self.zarnigor)[0]

    def _partner(self, user):
        self.client.force_authenticate(user)
        r = self.client.get("/api/v1/conversations/")
        self.assertEqual(r.status_code, 200)
        rows = r.data["results"]
        self.assertEqual(len(rows), 1)
        return rows[0]["partner"]

    def test_partner_has_full_name(self):
        p = self._partner(self.alisher)
        self.assertEqual(p["id"], self.zarnigor.id)
        self.assertEqual(p["full_name"], "Zarnigor Aliyeva")

    def test_phone_stays_masked(self):
        p = self._partner(self.alisher)
        self.assertNotIn("2222222", p["phone"])
        self.assertTrue(p["phone"].endswith("2"))

    def test_avatar_is_null_when_absent(self):
        p = self._partner(self.alisher)
        self.assertIsNone(p["avatar"])

    def test_partner_fields_are_symmetric(self):
        """Har ikki tomon ham bir xil to'ldirilgan ma'lumotni ko'radi."""
        a = self._partner(self.alisher)
        z = self._partner(self.zarnigor)
        self.assertEqual(a["full_name"], "Zarnigor Aliyeva")
        self.assertEqual(z["full_name"], "Alisher Karimov")

    def test_partner_without_profile_does_not_crash(self):
        """`Profile` yo'q bo'lsa ham 500 bermasligi kerak."""
        Profile.objects.filter(user=self.zarnigor).delete()
        p = self._partner(self.alisher)
        self.assertEqual(p["full_name"], "")
        self.assertIsNone(p["avatar"])

    def test_idempotent_pair_creation(self):
        again, created = Conversation.get_or_create_pair(self.alisher, self.zarnigor)
        self.assertFalse(created)
        self.assertEqual(again.id, self.conv.id)