import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from unittest import mock

from apps.chat.models import Conversation, Message
from apps.housing.models import Amenity, Listing
from apps.roommates.models import Match, RoommateProfile

User = get_user_model()


class CacheResetMixin:
    """Throttle va OTP hisoblari LocMemCache'da saqlanadi — testlar oraliqda tozalanadi."""

    def setUp(self):
        super().setUp()
        cache.clear()

    def _post_otp(self, phone):
        """OTP so'rovi yuboradi va throttle hisobini tozalaydi.

        Eslatma: `ScopedRateThrottle.THROTTLE_RATES` import vaqtida
        klass atributiga saqlanadi, shuning uchun `override_settings` bilan
        rate'ni o'zgartirib bo'lmaydi — cache'ni tozalash kerak.
        """
        res = self.client.post("/api/v1/auth/send-otp/", {"phone": phone})
        cache.clear()
        return res


class AuthFlowTests(CacheResetMixin, APITestCase):
    """TZ 5.1 — OTP auth oqimi."""

    @override_settings(OTP_DEBUG_RETURN_CODE=True, DEBUG=True)
    def test_send_otp_returns_code_in_debug(self):
        res = self.client.post(
            "/api/v1/auth/send-otp/",
            {"phone": "+998901234567", "purpose": "register"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("debug_code", res.data)

    @override_settings(OTP_DEBUG_RETURN_CODE=True, DEBUG=True)
    def test_register_via_otp(self):
        send = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998901234567"})
        code = send.data["debug_code"]

        res = self.client.post(
            "/api/v1/auth/verify-otp/",
            {"phone": "+998901234567", "code": code},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.assertTrue(User.objects.filter(phone="+998901234567").exists())

    def test_verify_otp_wrong_code(self):
        self.client.post("/api/v1/auth/send-otp/", {"phone": "+998901234567"})
        res = self.client.post(
            "/api/v1/auth/verify-otp/",
            {"phone": "+998901234567", "code": "000000"},
        )
        self.assertEqual(res.status_code, 400)

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/profile/me/").status_code, 401)

    def test_login_with_password(self):
        User.objects.create_user(phone="+998901111111", password="pass12345")
        res = self.client.post(
            "/api/v1/auth/login/",
            {"phone": "+998901111111", "password": "pass12345"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)

    def test_login_wrong_phone_format_returns_401(self):
        """Noto'g'ri formatdagi raqam 500 emas, 401 qaytarishi kerak."""
        User.objects.create_user(phone="+998901111111", password="pass12345")
        res = self.client.post(
            "/api/v1/auth/login/", {"phone": "abc", "password": "pass12345"}
        )
        self.assertEqual(res.status_code, 401)

    def test_login_inactive_user_rejected(self):
        user = User.objects.create_user(phone="+998901111111", password="pass12345")
        user.is_active = False
        user.save()
        res = self.client.post(
            "/api/v1/auth/login/",
            {"phone": "+998901111111", "password": "pass12345"},
        )
        self.assertEqual(res.status_code, 401)


class SecurityRegressionTests(CacheResetMixin, APITestCase):
    """Tuzatilgan xavfsizlik kamchiliklarining regressiya testlari."""

    # --- OTP kodining API dan chiqarilishi ---

    @override_settings(OTP_DEBUG_RETURN_CODE=False)
    def test_debug_code_hidden_when_flag_off(self):
        res = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998901234567"})
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("debug_code", res.data)

    @override_settings(OTP_DEBUG_RETURN_CODE=False, DEBUG=False)
    def test_debug_code_hidden_when_debug_false(self):
        """Production rejimi: DEBUG False bo'lsa kod hech qachon qaytarilmaydi."""
        res = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998901234567"})
        self.assertNotIn("debug_code", res.data)

    # --- Telefon validatsiyasi ---
    # Eslatma: `ScopedRateThrottle.THROTTLE_RATES` klass atributi bo'lib
    # import vaqtida biriktiriladi, shuning uchun `override_settings` bilan
    # rate o'zgartirilmaydi — `_post_otp()` orqali cache tozalanadi.

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_invalid_phones_rejected(self):
        for bad in ["abc", "", "+15550100", "123", "+998 12", "+99890123456789"]:
            res = self._post_otp(bad)
            self.assertEqual(res.status_code, 400, f"{bad!r} qabul qilindi")

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_phone_formats_normalized(self):
        for variant in ["+998901234567", "998901234567", "901234567", "+998 90 123 45 67"]:
            res = self.client.post("/api/v1/auth/send-otp/", {"phone": variant})
            self.assertEqual(res.status_code, 200, f"{variant!r} rad etildi")

    # --- Operator kodlari -------------------------------------------------
    #
    # Dastlabki ro'yxatda faqat 17 ta kod bor edi (90, 91, 93, ... va 62, 65,
    # 69, 71, ...). Real O'zbekistonda esa 33 ta kod ishlatiladi — jumladan
    # 20 (OQ/Beeline), 33 (Humans), 50 (Ucell), 77 (Uzmobile), 80 (Perfectum
    # 5G), 87 va 92. Ularsiz haqiqiy foydalanuvchilar ro'yxatdan o'ta olmasdi.

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_all_real_uz_operator_codes_accepted(self):
        """O'zbekistondagi barcha rasmiy operator/region kodlari qabul qilinishi kerak."""
        for code in [
            "20",  # OQ (Beeline)
            "33",  # Humans
            "50",  # Ucell
            "55",  # Uztelecom (VoIP)
            "61",  # Nukus
            "62",  # Urganch
            "65",  # Buxoro
            "66",  # Samarqand
            "67",  # Guliston
            "69",  # Namangan
            "70",  # Uzmobile
            "71",  # Toshkent
            "72",  # Jizzax
            "73",  # Farg'ona
            "74",  # Andijon
            "75",  # Qarshi
            "76",  # Termez
            "77",  # Uzmobile GSM
            "78",
            "79",  # Navoiy
            "80",  # Perfectum 5G
            "87",  # Mobiuz
            "88",  # Mobiuz
            "90", "91", "92",  # Beeline
            "93", "94",  # Ucell
            "95",  # Uzmobile CDMA
            "97",  # Mobiuz
            "98",  # Perfectum
            "99",  # Uzmobile
        ]:
            with self.subTest(code=code):
                res = self.client.post(
                    "/api/v1/auth/send-otp/", {"phone": f"+998{code}1234567"}
                )
                self.assertEqual(res.status_code, 200, f"Operator kodi {code} rad etildi")

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=0)
    def test_nonexistent_operator_codes_still_rejected(self):
        """Mavjud bo'lmagan kodlar rad qolinishi SHART (validatsiya susmasin)."""
        for code in ["00", "01", "10", "11", "12", "19", "40", "60", "81", "85", "96"]:
            with self.subTest(code=code):
                res = self.client.post(
                    "/api/v1/auth/send-otp/", {"phone": f"+998{code}1234567"}
                )
                self.assertEqual(res.status_code, 400, f"Bog'liq bo'lmagan {code} qabul qilindi")

    @override_settings(
        OTP_RESEND_COOLDOWN_SECONDS=0,
        PHONE_OPERATOR_CODES="21,22",
    )
    def test_operator_codes_extendable_via_env(self):
        """`.env` dagi `PHONE_OPERATOR_CODES` orqali yangi kod qo'shilishi kerak.

        Real hayotda yangi operator prefiksi chiqsa, kodga tegmasdan shu
        sozlamani o'zgartirish yetarli bo'lishi SHART.
        """
        for code in ["21", "22"]:
            res = self.client.post("/api/v1/auth/send-otp/", {"phone": f"+998{code}1234567"})
            self.assertEqual(res.status_code, 200, f"Sozlamadan qo'shilgan {code} rad etildi")
        # Default ro'yxat buzilmasligi kerak
        res = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998901234567"})
        self.assertEqual(res.status_code, 200, "Default operator kodi buzilgan")

    # --- Xato matnlari o'zbek tilida ---------------------------------------

    def test_phone_errors_are_in_uzbek_not_english(self):
        """DRF standart xatosi inglizcha chiqmasligi kerak.

        Foydalanuvchi inglizchani tushunmasligi mumkin, shuning uchun
        bo'sh/yo'q/noto'g'ri tur holatlarida o'zbekcha matn qaytariladi.
        """
        # Bo'sh string va butunlay yo'q maydon — ikkalasi ham o'zbekcha.
        for payload, expected in [
            ({"phone": ""}, "Telefon raqamni kiriting."),
            ({}, "Ushbu maydon to'ldirilishi shart."),
        ]:
            with self.subTest(payload=payload):
                res = self.client.post("/api/v1/auth/send-otp/", payload)
                self.assertEqual(res.status_code, 400)
                msg = str(res.json())
                self.assertIn(expected, msg, f"Inglizcha xato qaytarildi: {msg}")
                self.assertNotIn("This field", msg)

        # Noto'g'ri qiymat turlari (`None`, ro'yxat, obyekt) ham o'zbekcha
        # xato berishi kerak — inglizcha DRF matni chiqmasin.
        # JSON format ishlatiladi: `None` va dict qiymatlar multipart'da
        # qo'llab-quvvatlanmaydi.
        for payload in [{"phone": None}, {"phone": ["abc"]}, {"phone": {"a": 1}}]:
            with self.subTest(payload=payload):
                res = self.client.post(
                    "/api/v1/auth/send-otp/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                self.assertEqual(res.status_code, 400)
                msg = str(res.json())
                self.assertNotIn("may be blank", msg, f"Inglizcha xato: {msg}")
                self.assertNotIn("Not a valid", msg, f"Inglizcha xato: {msg}")
                self.assertIn("Telefon raqam", msg, f"O'zbekcha xato yo'q: {msg}")

    def test_otp_code_errors_in_uzbek(self):
        res = self.client.post(
            "/api/v1/auth/verify-otp/", {"phone": "+998901234567", "code": ""}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("Kodni kiriting", str(res.json()))

        res = self.client.post(
            "/api/v1/auth/verify-otp/", {"phone": "+998901234567", "code": "12"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("4 ta raqam", str(res.json()))

    # --- Foydalanuvchi mavjudligini oshkor qilish ---

    def test_send_otp_does_not_reveal_user_existence(self):
        """`register` va `login` uchun javob BIR XIL bo'lishi kerak."""
        User.objects.create_user(phone="+998901111111", password="pass12345")

        existing = self.client.post(
            "/api/v1/auth/send-otp/", {"phone": "+998901111111", "purpose": "register"}
        )
        new_one = self.client.post(
            "/api/v1/auth/send-otp/", {"phone": "+998909999999", "purpose": "register"}
        )
        self.assertEqual(existing.status_code, new_one.status_code)
        self.assertEqual(
            set(existing.data.keys()), set(new_one.data.keys()), "javob tuzilishi farq qildi"
        )

    # --- Throttle ---

    def test_otp_send_is_throttled(self):
        """OTP send limiti ishlashi kerak.

        Eslatma: rate `.env` orqali o'zgaradi (lokal rivojlash uchun yumshoq
        qo'yiladi). Test `.env` ga bog'liq bo'lib qolmasligi uchun throttle
        klassining `THROTTLE_RATES` ga aniq production qiymatini beradi —
        aks holda production himoyasi umuman tekshirilmasdi.
        """
        from rest_framework.throttling import ScopedRateThrottle

        production_rates = {
            **ScopedRateThrottle.THROTTLE_RATES,
            "otp_send": "5/hour",
            "otp_verify": "10/hour",
        }
        with mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", production_rates):
            cache.clear()
            statuses = []
            for i in range(8):
                res = self.client.post(
                    "/api/v1/auth/send-otp/", {"phone": f"+99890123456{i}"}
                )
                statuses.append(res.status_code)
            self.assertIn(429, statuses, "throttle ishlamadi")
            self.assertEqual(statuses[:5], [200] * 5)

    def test_resend_cooldown(self):
        first = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998905555555"})
        second = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998905555555"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_otp_attempts_not_reset_by_resend(self):
        """Avval har bir `send-otp` urinish limitini nolga tushirardi —
        haker shu bilan 5 urinish chekasini aylanib o'ta olardi."""
        self.client.post("/api/v1/auth/send-otp/", {"phone": "+998905555555"})
        for _ in range(5):
            self.client.post(
                "/api/v1/auth/verify-otp/",
                {"phone": "+998905555555", "code": "000000"},
            )
        res = self.client.post("/api/v1/auth/send-otp/", {"phone": "+998905555555"})
        self.assertEqual(res.status_code, 429, "cooldown ishladi, lekin limit tiklandi")
        # Yana urinish — limit tugagan bo'lishi kerak
        verify = self.client.post(
            "/api/v1/auth/verify-otp/", {"phone": "+998905555555", "code": "111111"}
        )
        self.assertIn("Urinishlar", str(verify.data))

    # --- Verifikatsiya ---
    # Eslatma: avval `f"@{d}" in email` ishlatilgan edi — `attacker@uzevil.com`
    # ham o'tib ketardi. Bundan tashqari, so'rov yuborish `is_verified`
    # darhol berardi, ya'ni foydalanuvchi o'z mailini tasdiqlamasdan
    # "o'z universiteti" deb e'lon qila olardi (privilege escalation).
    # Endi email alohida kod orqali tasdiqlanadi.

    def test_spoofed_university_domain_rejected(self):
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "attacker@uzevil.com"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)
        res = self.client.post(
            "/api/v1/verification/requests/",
            {"method": "university_email", "university_email": "attacker@uzevil.com"},
        )
        self.assertEqual(res.status_code, 400, "soxta domen qabul qilindi!")
        u.refresh_from_db()
        self.assertFalse(u.is_verified, "soxta domen bilan verifikatsiya o'tdi!")

    def test_request_alone_does_not_verify(self):
        """So'rov yuborish YOLI bilan tasdiqlanmadi."""
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "ali@ut.uz"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)
        res = self.client.post(
            "/api/v1/verification/requests/",
            {"method": "university_email", "university_email": "ali@ut.uz"},
        )
        self.assertEqual(res.status_code, 201)
        u.refresh_from_db()
        self.assertFalse(u.is_verified, "so'rov yuborish o'zi tasdiqlashga yetdi!")

    def test_email_domain_not_linked_to_account_rejected(self):
        """Profilga bog'lanmagan universitet emaili rad etiladi."""
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "ali@gmail.com"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)
        res = self.client.post(
            "/api/v1/verification/requests/",
            {"method": "university_email", "university_email": "boshqa@ut.uz"},
        )
        self.assertEqual(res.status_code, 400)
        u.refresh_from_db()
        self.assertFalse(u.is_verified)

    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def test_real_university_domain_verifies_via_email_code(self):
        """To'g'ri domen + inbox'da olgan kod -> tasdiqlangan."""
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "ali@ut.uz"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)

        send = self.client.post(
            "/api/v1/verification/email/send-code/", {"email": "ali@ut.uz"}
        )
        self.assertEqual(send.status_code, 200)
        code = send.data["debug_code"]

        bad = self.client.post(
            "/api/v1/verification/email/confirm/",
            {"email": "ali@ut.uz", "code": "000000"},
        )
        self.assertEqual(bad.status_code, 400)
        u.refresh_from_db()
        self.assertFalse(u.is_verified, "noto'g'ri kod bilan tasdiqlandi!")

        ok = self.client.post(
            "/api/v1/verification/email/confirm/", {"email": "ali@ut.uz", "code": code}
        )
        self.assertEqual(ok.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.is_verified)

    # --- OTP loglarida kod yozilmasligi ---

    @override_settings(DEBUG=False, OTP_DEBUG_RETURN_CODE=False)
    def test_otp_code_not_logged_in_production(self):
        """Production rejimida kod hech qanday log darajasida chiqmasin."""
        import logging

        from apps.users.services import send_otp

        with self.assertLogs("apps.users.services", level="DEBUG") as captured:
            send_otp("+998905555555", purpose="register")

        blob = "\n".join(captured.output)
        # 6 xonali kodni topishga urinish
        import re

        codes = re.findall(r"\b\d{6}\b", blob)
        self.assertEqual(
            [c for c in codes if c != "905555"], [], f"logda OTP kodi topildi: {codes}"
        )
        # Faqat maskalangan telefon ko'rinishi kerak
        self.assertIn("+9989*****55", blob)

    # --- Role ---

    def test_role_is_read_only(self):
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        self.assertNotEqual(u.role, "moderator")

        from apps.users.serializers import UserSerializer

        ser = UserSerializer(u, data={"role": "moderator"}, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        u.refresh_from_db()
        self.assertNotEqual(u.role, "moderator", "role yoziladigan qoldi!")

    # --- Telefon raqami maxfiyligi ---

    def test_listing_phone_is_masked(self):
        owner = User.objects.create_user(phone="+998901111111", password="pass12345")
        owner.is_verified = True
        owner.save()
        listing = Listing.objects.create(
            owner=owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        other = User.objects.create_user(phone="+998902222222", password="pass12345")
        self.client.force_authenticate(other)

        res = self.client.get(f"/api/v1/listings/{listing.id}/")
        self.assertNotIn("901111111", res.data["owner_phone"])

    def test_chat_partner_phone_is_masked(self):
        u1 = User.objects.create_user(phone="+998901111111", password="pass12345")
        u2 = User.objects.create_user(phone="+998902222222", password="pass12345")
        Conversation.get_or_create_pair(u1, u2)
        self.client.force_authenticate(u2)

        res = self.client.get("/api/v1/conversations/")
        self.assertNotIn("901111111", res.data["results"][0]["partner"]["phone"])

    # --- IDOR ---

    def test_cannot_read_other_users_notification(self):
        u1 = User.objects.create_user(phone="+998901111111", password="pass12345")
        u2 = User.objects.create_user(phone="+998902222222", password="pass12345")
        from apps.notifications.models import Notification

        notif = Notification.objects.create(user=u1, type="new_message", payload={})
        self.client.force_authenticate(u2)
        res = self.client.post(f"/api/v1/notifications/{notif.id}/read/")
        self.assertEqual(res.status_code, 404)
        notif.refresh_from_db()
        self.assertFalse(notif.is_read)


class ProfileTests(CacheResetMixin, APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="+998901234567", password="pass12345")
        self.client.force_authenticate(self.user)

    def test_get_profile_auto_creates(self):
        res = self.client.get("/api/v1/profile/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("full_name", res.data)

    def test_patch_profile(self):
        res = self.client.patch("/api/v1/profile/", {"city": "Toshkent", "course": 2})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["city"], "Toshkent")


class ListingTests(CacheResetMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(phone="+998901111111", password="pass12345")
        self.other = User.objects.create_user(phone="+998902222222", password="pass12345")
        # `housing.0003_seed_amenities` allaqachon "Wi-Fi" qatorini yaratadi,
        # shuning uchun `create` emas `get_or_create` ishlatamiz.
        self.amenity, _ = Amenity.objects.get_or_create(name="Wi-Fi")

    def _auth(self, user):
        self.client.force_authenticate(user)

    def test_create_requires_verification(self):
        self._auth(self.owner)
        res = self.client.post(
            "/api/v1/listings/",
            {"title": "Xona", "description": "Tavsif", "type": "room",
             "price": "1000000", "city": "Toshkent"},
        )
        self.assertEqual(res.status_code, 403)

    def test_verified_owner_creates_listing(self):
        self.owner.is_verified = True
        self.owner.save()
        self._auth(self.owner)
        res = self.client.post(
            "/api/v1/listings/",
            {"title": "Xona", "description": "Tavsif", "type": "room",
             "price": "1000000", "city": "Toshkent", "amenity_ids": [self.amenity.id]},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Listing.objects.count(), 1)
        listing = Listing.objects.first()
        self.assertEqual(listing.status, "active")
        self.assertIn(self.amenity, listing.amenities.all())

    def test_fourth_listing_goes_to_moderation(self):
        """TZ 5.3 — 3 ta faol e'londan keyingi moderatsiyaga tushadi."""
        self.owner.is_verified = True
        self.owner.save()
        for i in range(4):
            Listing.objects.create(
                owner=self.owner, title=f"Xona {i}", description="d", type="room",
                price=100 + i, city="Toshkent",
            )
        self.assertEqual(Listing.objects.filter(status="active").count(), 3)
        self.assertEqual(Listing.objects.filter(status="moderation").count(), 1)

    def test_update_does_not_push_listing_to_moderation(self):
        """Eski xato: `validate()` o'z e'lonini ham sanab, mavjud e'lonni
        PATCH qilishda moderatsiyaga tushirardi."""
        self.owner.is_verified = True
        self.owner.save()
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.owner)
        res = self.client.patch(
            f"/api/v1/listings/{listing.id}/", {"description": "yangi tavsif"}
        )
        self.assertEqual(res.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.status, "active")

    def test_image_upload_and_min_images(self):
        """Rasm yuklash ishlaydi va minimal rasm soni tekshiriladi."""
        import io

        from PIL import Image

        self.owner.is_verified = True
        self.owner.save()
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.owner)

        def png(name):
            buf = io.BytesIO()
            Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
            return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

        res = self.client.post(
            f"/api/v1/listings/{listing.id}/images/", {"images": [png("a.png")]}
        )
        self.assertEqual(res.status_code, 201, getattr(res, "data", res.content))
        self.assertEqual(listing.images.count(), 1)

        # E'lon kamida 3 rasm talab qiladi — 1 rasm bilan faol qolsa, xato.
        listing.refresh_from_db()
        self.assertNotEqual(listing.status, "active")

    def test_image_upload_rejects_non_image(self):
        self.owner.is_verified = True
        self.owner.save()
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.owner)
        bad = SimpleUploadedFile(
            "x.txt", b"salom", content_type="text/plain"
        )
        res = self.client.post(
            f"/api/v1/listings/{listing.id}/images/", {"images": [bad]}
        )
        self.assertEqual(res.status_code, 400)

    def test_other_user_cannot_upload_images(self):
        self.owner.is_verified = True
        self.other.is_verified = True
        self.owner.save()
        self.other.save()
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.other)
        res = self.client.post(f"/api/v1/listings/{listing.id}/images/", {"images": []})
        self.assertIn(res.status_code, (400, 403, 404))

    def test_filter_by_city_and_price(self):
        self.owner.is_verified = True
        self.owner.save()
        Listing.objects.create(
            owner=self.owner, title="Arzon", description="d", type="room",
            price=500000, city="Toshkent",
        )
        Listing.objects.create(
            owner=self.owner, title="Qimmat", description="d", type="whole_apartment",
            price=5000000, city="Samarqand",
        )
        self._auth(self.other)
        res = self.client.get("/api/v1/listings/?city=Toshkent&price__lte=1000000")
        self.assertEqual(len(res.data["results"]), 1)

    def test_favorite_toggle(self):
        self.owner.is_verified = True
        self.owner.save()
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.other)
        r1 = self.client.post(f"/api/v1/listings/{listing.id}/favorite/")
        r2 = self.client.post(f"/api/v1/listings/{listing.id}/favorite/")
        self.assertTrue(r1.data["favorited"])
        self.assertFalse(r2.data["favorited"])

    def test_owner_can_archive(self):
        self.owner.is_verified = True
        self.owner.save()
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.owner)
        res = self.client.post(f"/api/v1/listings/{listing.id}/archive/")
        self.assertEqual(res.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.status, "archived")

    def test_other_cannot_edit(self):
        listing = Listing.objects.create(
            owner=self.owner, title="Xona", description="d", type="room",
            price=100, city="Toshkent",
        )
        self._auth(self.other)
        res = self.client.patch(f"/api/v1/listings/{listing.id}/", {"price": 1})
        self.assertIn(res.status_code, (403, 404))

    def test_listing_list_is_paginated(self):
        self.owner.is_verified = True
        self.owner.save()
        for i in range(3):
            Listing.objects.create(
                owner=self.owner, title=f"Xona {i}", description="d", type="room",
                price=100 + i, city="Toshkent",
            )
        self._auth(self.other)
        res = self.client.get("/api/v1/listings/")
        self.assertIn("results", res.data)
        self.assertIn("count", res.data)


class RoommateTests(CacheResetMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.u1 = User.objects.create_user(phone="+998901111111", password="pass12345")
        self.u2 = User.objects.create_user(phone="+998902222222", password="pass12345")
        for u in (self.u1, self.u2):
            u.is_verified = True
            u.save()

    def test_matching_high_score_same_city(self):
        RoommateProfile.objects.create(
            user=self.u1, city="Toshkent", budget_min=500000, budget_max=1000000,
            sleep_schedule="early", cleanliness="tidy", smoking=False,
        )
        RoommateProfile.objects.create(
            user=self.u2, city="Toshkent", budget_min=600000, budget_max=1200000,
            sleep_schedule="early", cleanliness="tidy", smoking=False,
        )
        self.client.force_authenticate(self.u1)
        res = self.client.get("/api/v1/roommates/matches/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.data["results"]) >= 1)
        self.assertGreaterEqual(res.data["results"][0]["score"], 70)

    def test_matching_low_score_filtered(self):
        RoommateProfile.objects.create(
            user=self.u1, city="Toshkent", smoking=False,
            sleep_schedule="early", cleanliness="very_tidy", guests_ok=False,
        )
        RoommateProfile.objects.create(
            user=self.u2, city="Buxoro", budget_min=9000000, budget_max=9500000,
            smoking=True, sleep_schedule="late", cleanliness="relaxed", guests_ok=True,
        )
        self.client.force_authenticate(self.u1)
        res = self.client.get("/api/v1/roommates/matches/")
        self.assertEqual(len(res.data["results"]), 0)  # 30% dan past — chiqmaydi

    def test_matches_endpoint_does_not_write_to_db(self):
        """Eski xato: GET har safar `Match` qatori yaratardi (crawler ham yozardi)."""
        RoommateProfile.objects.create(user=self.u1, city="Toshkent")
        RoommateProfile.objects.create(user=self.u2, city="Toshkent")
        self.client.force_authenticate(self.u1)

        self.client.get("/api/v1/roommates/matches/")
        self.client.get("/api/v1/roommates/matches/")
        self.client.get("/api/v1/roommates/matches/")
        self.assertEqual(Match.objects.count(), 0, "GET so'rovi bazaga yozdi!")

    def test_match_pair_is_normalized(self):
        """Juftlik ikki yo'nalishda ham bitta qator bo'lishi kerak."""
        a, _ = Match.for_users(self.u1, self.u2, score=80)
        c, d = Match.for_users(self.u2, self.u1, score=80)
        self.assertEqual(a.id, c.id)
        self.assertFalse(d)
        self.assertEqual(Match.objects.count(), 1)
        self.assertEqual(a.user_a_id, min(self.u1.id, self.u2.id))
        self.assertEqual(a.user_b_id, max(self.u1.id, self.u2.id))

    def test_requires_verification(self):
        u3 = User.objects.create_user(phone="+998903333333", password="pass12345")
        self.client.force_authenticate(u3)
        res = self.client.get("/api/v1/roommates/matches/")
        self.assertEqual(res.status_code, 403)

    def test_accept_match_notifies(self):
        from apps.notifications.models import Notification

        RoommateProfile.objects.create(user=self.u1, city="Toshkent")
        RoommateProfile.objects.create(user=self.u2, city="Toshkent")
        match, _ = Match.for_users(self.u1, self.u2, score=90)

        self.client.force_authenticate(self.u1)
        res = self.client.post(
            f"/api/v1/roommates/matches/{match.id}/decision/", {"decision": "accept"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.u2, type="new_match").exists())

    def test_match_request_then_decide_full_flow(self):
        """`GET` yozmaydi -> `request/` yaratadi -> `decision/` qabul qiladi.

        Eslatma: `id: null` qatorlarni avval qabul/rad etib bo'lmasdi,
        chunki `MatchDecisionView` faqat saqlangan `Match` id'sini kutardi.
        """
        from apps.notifications.models import Notification

        RoommateProfile.objects.create(user=self.u1, city="Toshkent")
        RoommateProfile.objects.create(user=self.u2, city="Toshkent")

        self.client.force_authenticate(self.u1)
        req = self.client.post(
            "/api/v1/roommates/matches/request/", {"partner_id": self.u2.id}
        )
        self.assertEqual(req.status_code, 201, getattr(req, "data", req.content))
        match_id = req.data["id"]
        self.assertIsNotNone(match_id)
        self.assertTrue(Notification.objects.filter(user=self.u2, type="new_match").exists())

        self.client.force_authenticate(self.u2)
        dec = self.client.post(
            f"/api/v1/roommates/matches/{match_id}/decision/", {"decision": "accept"}
        )
        self.assertEqual(dec.status_code, 200, getattr(dec, "data", dec.content))
        self.assertEqual(dec.data["status"], "accepted")

    def test_match_request_is_idempotent(self):
        RoommateProfile.objects.create(user=self.u1, city="Toshkent")
        RoommateProfile.objects.create(user=self.u2, city="Toshkent")
        self.client.force_authenticate(self.u1)

        first = self.client.post(
            "/api/v1/roommates/matches/request/", {"partner_id": self.u2.id}
        )
        second = self.client.post(
            "/api/v1/roommates/matches/request/", {"partner_id": self.u2.id}
        )
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Match.objects.count(), 1)

    def test_match_request_rejected_when_blocked(self):
        from apps.reports.models import Block

        RoommateProfile.objects.create(user=self.u1, city="Toshkent")
        RoommateProfile.objects.create(user=self.u2, city="Toshkent")
        Block.objects.create(blocker=self.u2, blocked=self.u1)
        self.client.force_authenticate(self.u1)
        res = self.client.post(
            "/api/v1/roommates/matches/request/", {"partner_id": self.u2.id}
        )
        self.assertEqual(res.status_code, 400)

    def test_match_decision_invalid_value(self):
        match, _ = Match.for_users(self.u1, self.u2, score=90)
        self.client.force_authenticate(self.u1)
        res = self.client.post(
            f"/api/v1/roommates/matches/{match.id}/decision/", {"decision": "maybe"}
        )
        self.assertEqual(res.status_code, 400)


class ChatTests(CacheResetMixin, APITestCase):
    def setUp(self):
        # Muhim: `CacheResetMixin.setUp` ni chaqirish SHART — aks holda
        # LocMemCache'dagi throttle hisobi keyingi testlarga o'tib ketadi.
        super().setUp()
        self.u1 = User.objects.create_user(phone="+998901111111", password="pass12345")
        self.u2 = User.objects.create_user(phone="+998902222222", password="pass12345")

    def test_message_send_is_throttled(self):
        """`message_send` scope'i ishlashi kerak (60/soat).

        Eslatma: rate settings'da bor, lekin `throttle_scope` view'da
        ulanmagan edi — hech qanday cheklash amalga oshmagan.
        """
        conv_id = self._create_conv()
        self.client.force_authenticate(self.u1)

        rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["message_send"]
        num, _dur = ScopedRateThrottle().parse_rate(rate)

        statuses = []
        for i in range(num + 3):
            res = self.client.post(
                f"/api/v1/conversations/{conv_id}/messages/", {"text": f"x{i}"}
            )
            statuses.append(res.status_code)

        self.assertIn(429, statuses, "message_send throttle ishlamadi")
        # GET o'qish cheylanmasin
        self.client.get(f"/api/v1/conversations/{conv_id}/messages/")
        self.client.get("/api/v1/conversations/")
        # o'qish throttle'dan keyin ham ishlaydi
        res = self.client.get(f"/api/v1/conversations/{conv_id}/messages/")
        self.assertEqual(res.status_code, 200)

    def _create_conv(self):
        self.client.force_authenticate(self.u1)
        res = self.client.post("/api/v1/conversations/", {"user_id": self.u2.id})
        return res.data["id"]

    def test_create_conversation(self):
        conv_id = self._create_conv()
        self.client.force_authenticate(self.u2)
        res = self.client.get("/api/v1/conversations/")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["partner"]["id"], self.u1.id)

    def test_conversation_is_unique_per_pair(self):
        """Eski xato: unique constraint yo'q edi, parallel so'rovlar 2 ta suhbat
        yaratib qo'yardi."""
        conv_id = self._create_conv()
        res = self.client.post("/api/v1/conversations/", {"user_id": self.u2.id})
        self.assertEqual(res.data["id"], conv_id)
        self.assertEqual(res.status_code, 200)  # mavjudi — 201 emas
        self.assertEqual(Conversation.objects.count(), 1)

    def test_send_and_read_messages(self):
        conv_id = self._create_conv()
        self.client.force_authenticate(self.u2)
        res = self.client.get(f"/api/v1/conversations/{conv_id}/messages/")
        self.assertEqual(res.status_code, 200)

        res = self.client.post(
            f"/api/v1/conversations/{conv_id}/messages/", {"text": "Salom!"}
        )
        self.assertEqual(res.status_code, 201)

        # u1 xabarni ko'radi va o'qilgan bo'ladi
        self.client.force_authenticate(self.u1)
        res = self.client.get(f"/api/v1/conversations/{conv_id}/messages/")
        first = res.data["results"][0]
        self.assertEqual(first["text"], "Salom!")
        self.assertIsNotNone(first["read_at"])

    def test_message_too_long_rejected(self):
        conv_id = self._create_conv()
        self.client.force_authenticate(self.u1)
        res = self.client.post(
            f"/api/v1/conversations/{conv_id}/messages/", {"text": "x" * 5000}
        )
        self.assertEqual(res.status_code, 400)

    def test_conversation_list_shows_last_message_and_unread(self):
        """`last_message` va `unread_count` prefetch'dan kelishi kerak.

        Eslatma: view `Prefetch("messages")` (to_attr'siz) ishlatardi,
        serializer esa `messages_cache` ni kutardi — natijada har doim
        `last_message: null` va `unread_count: 0` qaytardi.
        """
        conv_id = self._create_conv()
        self.client.force_authenticate(self.u2)
        self.client.post(
            f"/api/v1/conversations/{conv_id}/messages/", {"text": "Birinchi xabar"}
        )
        self.client.post(
            f"/api/v1/conversations/{conv_id}/messages/", {"text": "Ikkinchi xabar"}
        )

        self.client.force_authenticate(self.u1)
        res = self.client.get("/api/v1/conversations/")
        row = res.data["results"][0]
        self.assertIsNotNone(row["last_message"], "last_message null qoldi")
        self.assertEqual(row["last_message"]["text"], "Ikkinchi xabar")
        self.assertEqual(row["unread_count"], 2, "o'qilmagan xabarlar sanalmadi")

        # O'qilgandan keyin 0 ga tushishi kerak
        self.client.get(f"/api/v1/conversations/{conv_id}/messages/")
        res = self.client.get("/api/v1/conversations/")
        self.assertEqual(res.data["results"][0]["unread_count"], 0)

    def test_conversation_list_pagination_count_excludes_blocked(self):
        """`count` metadata bloklangan suhbatlarni hisobga olmasin."""
        from apps.reports.models import Block

        # u1 bilan u2 va u3 bilan suhbatlar
        u3 = User.objects.create_user(phone="+998903333333", password="pass12345")
        self.client.force_authenticate(self.u1)
        self.client.post("/api/v1/conversations/", {"user_id": self.u2.id})
        c3 = self.client.post("/api/v1/conversations/", {"user_id": u3.id}).data["id"]
        Block.objects.create(blocker=self.u1, blocked=self.u2)

        self.client.force_authenticate(self.u1)
        res = self.client.get("/api/v1/conversations/")
        self.assertEqual(res.data["count"], 1, "bloklangan suhbat count'ga qo'shildi")
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["id"], c3)

    def test_blocked_conversation_hidden_from_list(self):
        from apps.reports.models import Block

        self._create_conv()
        Block.objects.create(blocker=self.u2, blocked=self.u1)
        self.client.force_authenticate(self.u1)
        res = self.client.get("/api/v1/conversations/")
        self.assertEqual(len(res.data["results"]), 0, "bloklangan suhbat ko'rinib turibdi")

    def test_blocked_user_cannot_message(self):
        from apps.reports.models import Block

        conv_id = self._create_conv()
        Block.objects.create(blocker=self.u2, blocked=self.u1)
        self.client.force_authenticate(self.u1)
        res = self.client.post(f"/api/v1/conversations/{conv_id}/messages/", {"text": "Salom"})
        self.assertEqual(res.status_code, 404)

    def test_blocked_user_cannot_read_messages(self):
        """Eski xato: bloklash faqat yuborishda tekshirilardi, o'qish
        erkin qoldi — bloklagan tomon barcha xabarni o'qiyverdi."""
        from apps.reports.models import Block

        conv_id = self._create_conv()
        self.client.force_authenticate(self.u1)
        self.client.post(f"/api/v1/conversations/{conv_id}/messages/", {"text": "Salom"})

        Block.objects.create(blocker=self.u2, blocked=self.u1)
        self.client.force_authenticate(self.u1)
        res = self.client.get(f"/api/v1/conversations/{conv_id}/messages/")
        self.assertEqual(res.status_code, 404)

    def test_blocked_user_cannot_open_conversation(self):
        from apps.reports.models import Block

        self._create_conv()
        Block.objects.create(blocker=self.u2, blocked=self.u1)
        self.client.force_authenticate(self.u1)
        res = self.client.post("/api/v1/conversations/", {"user_id": self.u2.id})
        self.assertEqual(res.status_code, 400)

    def test_notification_on_new_message(self):
        from apps.notifications.models import Notification

        conv_id = self._create_conv()
        self.client.force_authenticate(self.u1)
        self.client.post(f"/api/v1/conversations/{conv_id}/messages/", {"text": "Salom"})
        self.assertTrue(Notification.objects.filter(user=self.u2, type="new_message").exists())


class ReportTests(CacheResetMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.reporter = User.objects.create_user(phone="+998901111111", password="pass12345")
        self.target = User.objects.create_user(phone="+998902222222", password="pass12345")
        self.moderator = User.objects.create_user(phone="+998903333333", password="pass12345", role="moderator")
        self.moderator.is_staff = True
        self.moderator.save()

    def test_create_report(self):
        self.client.force_authenticate(self.reporter)
        res = self.client.post(
            "/api/v1/reports/",
            {"target_type": "user", "target_id": self.target.id, "reason": "spam"},
        )
        self.assertEqual(res.status_code, 201)

    def test_cannot_report_self(self):
        self.client.force_authenticate(self.reporter)
        res = self.client.post(
            "/api/v1/reports/",
            {"target_type": "user", "target_id": self.reporter.id, "reason": "spam"},
        )
        self.assertEqual(res.status_code, 400)

    def test_moderator_decision(self):
        self.client.force_authenticate(self.reporter)
        self.client.post(
            "/api/v1/reports/",
            {"target_type": "user", "target_id": self.target.id, "reason": "spam"},
        )
        self.client.force_authenticate(self.moderator)
        res = self.client.get("/api/v1/admin/reports/")
        self.assertEqual(len(res.data["results"]), 1)
        report_id = res.data["results"][0]["id"]
        res = self.client.post(f"/api/v1/admin/reports/{report_id}/decision/", {"decision": "resolve"})
        self.assertEqual(res.status_code, 200)

    def test_non_moderator_cannot_see_reports_queue(self):
        self.client.force_authenticate(self.reporter)
        res = self.client.get("/api/v1/admin/reports/")
        self.assertIn(res.status_code, (401, 403))

    def test_block_user(self):
        self.client.force_authenticate(self.reporter)
        res = self.client.post("/api/v1/users/blocks/", {"blocked_id": self.target.id})
        self.assertEqual(res.status_code, 201)
        res = self.client.get("/api/v1/users/blocks/")
        self.assertEqual(len(res.data["results"]), 1)


class VerificationTests(CacheResetMixin, APITestCase):
    # Django test runner `DEBUG=False` qo'yadi, shuning uchun debug kod
    # (real email provider yo'qligi sabab) faqat override bilan ko'rinadi.
    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def test_university_email_needs_confirmation(self):
        """`POST /verification/requests/` YOLI bilan tasdiqlanmadi."""
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "sardor@web.uz"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)
        res = self.client.post(
            "/api/v1/verification/requests/",
            {"method": "university_email", "university_email": "sardor@web.uz"},
        )
        self.assertEqual(res.status_code, 201)
        u.refresh_from_db()
        self.assertFalse(u.is_verified)

    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def test_university_email_confirmed_with_code(self):
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "sardor@web.uz"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)

        send = self.client.post(
            "/api/v1/verification/email/send-code/", {"email": "sardor@web.uz"}
        )
        self.assertEqual(send.status_code, 200)

        ok = self.client.post(
            "/api/v1/verification/email/confirm/",
            {"email": "sardor@web.uz", "code": send.data["debug_code"]},
        )
        self.assertEqual(ok.status_code, 200)
        u.refresh_from_db()
        self.assertTrue(u.is_verified)

    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def test_email_code_rejected_for_other_account_email(self):
        """Boshqa foydalanuvchining emailiga kod so'ranib bo'lmaydi."""
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        u.email = "men@web.uz"
        u.save(update_fields=["email"])
        self.client.force_authenticate(u)
        res = self.client.post(
            "/api/v1/verification/email/send-code/", {"email": "boshqa@web.uz"}
        )
        self.assertEqual(res.status_code, 400)

    def test_document_requires_images(self):
        u = User.objects.create_user(phone="+998901111111", password="pass12345")
        self.client.force_authenticate(u)
        res = self.client.post(
            "/api/v1/verification/requests/", {"method": "document"}
        )
        self.assertEqual(res.status_code, 400)


class HealthTests(CacheResetMixin, APITestCase):
    def test_health_ok(self):
        res = self.client.get("/health/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "ok")