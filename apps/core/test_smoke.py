"""To'liq API smoke testi — frontend integratsiyasidan oldin."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

User = get_user_model()


class SmokeTest(APITestCase):
    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def setUp(self):
        super().setUp()
        cache.clear()
        self.phone = "+998901111111"

    def _post(self, url, data=None):
        return self.client.post(url, data or {})

    def test_full_student_journey(self):
        # 1. OTP so'rash
        r = self._post("/api/v1/auth/send-otp/", {"phone": self.phone})
        assert r.status_code == 200, r.data
        code = r.data["debug_code"]

        # 2. Ro'yxatdan o'tish
        r = self._post(
            "/api/v1/auth/verify-otp/",
            {"phone": self.phone, "code": code, "purpose": "register",
             "full_name": "Ali Karimov"},
        )
        assert r.status_code in (200, 201), r.data
        access = r.data.get("access")
        refresh = r.data.get("refresh")
        assert access and refresh, r.data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        # 3. Profil
        r = self.client.get("/api/v1/profile/me/")
        assert r.status_code == 200, r.data

        # 4. Profil yangilash (user + profile maydonlari bir so'rovda)
        r = self.client.patch("/api/v1/profile/me/", {
            "full_name": "Ali Karimov", "city": "Toshkent",
            "university": "Toshkent Davlat Universiteti", "bio": "Dasturchi",
        })
        assert r.status_code == 200, r.data
        assert r.data["full_name"] == "Ali Karimov", r.data
        assert r.data["city"] == "Toshkent", r.data

        # 4b. Eskalatsiya urinishlari rad etilishi kerak
        r = self.client.patch("/api/v1/profile/me/", {
            "role": "moderator", "is_verified": True, "phone": "+998905555555"})
        assert r.data["role"] == "student", r.data
        assert r.data["is_verified"] is False, r.data
        assert r.data["phone"] == self.phone, r.data

        # 5. E'lon yaratish (verifikatsiya yo'q -> 403)
        r = self._post("/api/v1/listings/", {
            "title": "Xona", "description": "Toza xona", "type": "room",
            "price": "800000", "city": "Toshkent",
        })
        assert r.status_code == 403, r.data

        # 6. Roommate anketasi (verifikatsiya yo'q -> 403)
        r = self._post("/api/v1/roommates/profile/", {"city": "Toshkent"})
        assert r.status_code == 403, r.data

        # 7. O'z raqamimiz to'liq ko'rinadi (boshqalar uchun maskalanadi)
        r = self.client.get("/api/v1/profile/me/")
        assert r.data["phone"] == self.phone, r.data

        # 8. Token refresh
        r = self._post("/api/v1/auth/token/refresh/", {"refresh": refresh})
        assert r.status_code == 200 and "access" in r.data, r.data

        # 9. Ro'yxatlar
        for url in ("/api/v1/listings/", "/api/v1/conversations/",
                    "/api/v1/notifications/", "/api/v1/reports/mine/",
                    "/api/v1/verification/requests/"):
            r = self.client.get(url)
            assert r.status_code == 200, f"{url} -> {r.status_code} {r.data}"

        # 9b. Profil endpointi ham ishlaydi (GET)
        r = self.client.get("/api/v1/profile/")
        assert r.status_code == 200 and r.data["full_name"] == "Ali Karimov", r.data

        # 10. Amenities
        r = self.client.get("/api/v1/amenities/")
        assert r.status_code == 200, r.data

        # 11. Swagger
        r = self.client.get("/api/schema/")
        assert r.status_code == 200
        r = self.client.get("/health/")
        assert r.status_code == 200 and r.data["status"] == "ok"

    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def test_verified_user_full_journey(self):
        """Tasdiqlangan foydalanuvchi: e'lon, rasm, roommate, chat."""
        UserModel = User

        # Ikki foydalanuvchi
        for phone in ("+998901111111", "+998902222222"):
            r = self._post("/api/v1/auth/send-otp/", {"phone": phone})
            r = self._post("/api/v1/auth/verify-otp/", {
                "phone": phone, "code": r.data["debug_code"], "purpose": "register"})
            u = UserModel.objects.get(phone=phone)
            u.is_verified = True
            u.save(update_fields=["is_verified"])
            u.refresh_from_db()
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
            if phone.endswith("1111111"):
                self.token1 = r.data["access"]
            else:
                self.token2 = r.data["access"]

        # 1. E'lon yaratish
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token1}")
        r = self._post("/api/v1/listings/", {
            "title": "Toza xona", "description": "Yangi ta'mirdan",
            "type": "room", "price": "900000", "city": "Toshkent",
        })
        assert r.status_code == 201, f"{r.status_code} {r.data}"
        from apps.housing.models import Listing as _L
        assert _L.objects.filter(owner__phone="+998901111111").count() == 1

        # 2. Roommate anketasi
        r = self.client.patch("/api/v1/roommates/profile/", {
            "city": "Toshkent", "budget_min": 700000, "budget_max": 1200000,
            "sleep_schedule": "early", "cleanliness": "tidy", "smoking": False,
        }, format="json")
        assert r.status_code == 200, r.data

        # 3. Roommate mosliklar (GET bazaga yozmaydi)
        r = self.client.get("/api/v1/roommates/matches/")
        assert r.status_code == 200, r.data
        assert "count" in r.data, f"pagination kaliti yo'q: {list(r.data.keys())}"

        # 4. Suhbat ochish
        u2 = UserModel.objects.get(phone="+998902222222")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token2}")
        self.client.patch("/api/v1/roommates/profile/", {"city": "Toshkent"}, format="json")

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token1}")
        r = self._post("/api/v1/conversations/", {"user_id": u2.id})
        assert r.status_code in (200, 201), r.data
        assert "id" in r.data, f"suhbat javobida 'id' yo'q: {list(r.data.keys())}"
        conv_id = r.data["id"]

        # 5. Xabar yuborish
        r = self._post(f"/api/v1/conversations/{conv_id}/messages/",
                       {"text": "Salom, xona hali bormi?"})
        assert r.status_code == 201, r.data

        # 6. Xabar yetkazildi (notification)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token2}")
        r = self.client.get("/api/v1/notifications/")
        assert r.data["count"] >= 1, r.data

        # 7. E'lon muallifi telefon raqami ommaviy ro'yxatda MASKALANADI
        r = self.client.get("/api/v1/listings/")
        assert "901111111" not in str(r.data["results"]), "telefon ochiq ko'rindi!"

        # 8. Bloklash
        r = self._post("/api/v1/users/blocks/", {"blocked_id": self.token1 and UserModel.objects.get(phone='+998901111111').id})
        assert r.status_code in (200, 201), r.data

        # 9. Blokdan keyin xabar yuborib bo'lmaydi
        r = self._post(f"/api/v1/conversations/{conv_id}/messages/", {"text": "Yana bormi?"})
        assert r.status_code == 404, r.data
