"""Frontend (templates/index.html) bilan backend integratsiyasi testlari."""

import base64
import re

from django.core.cache import cache

from django.test import TestCase, override_settings
from django.urls import reverse


class HomePageTests(TestCase):
    """GET / — frontend sahifasi yuklanishi."""

    @override_settings(DEBUG=False)
    def test_home_serves_index_template(self):
        r = self.client.get("/")
        assert r.status_code == 200
        html = r.content.decode()
        assert "STUGO" in html
        assert "templates/index.html" not in html  # template xatosi yo'q

    def test_frontend_uses_real_api(self):
        html = self.client.get("/").content.decode()
        # Mock `fetch` yo'q — haqiqiy API ishlatiladi
        assert "/api/v1" in html or "API + " in html
        assert "var API = window.STUGO_API_BASE || '/api/v1'" in html

    def test_frontend_has_auth_flow(self):
        html = self.client.get("/").content.decode()
        for endpoint in ("/auth/send-otp/", "/auth/verify-otp/",
                         "/verification/email/send-code/", "/verification/email/confirm/"):
            assert endpoint in html, f"{endpoint} frontend'da yo'q"


@override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
class FrontendJourneyTests(TestCase):
    """Frontend ishlatadigan endpoint'lar ketma-ket ishlashi."""

    def setUp(self):
        super().setUp()
        cache.clear()

    def _register(self, phone, email=""):
        """Yangi foydalanuvchini ro'yxatdan o'tkazib, TOKENLI client qaytaradi.

        Muhim: har bir foydalanuvchi uchun alohida client — aks holda
        `self.client` tokenlari aralashib, "o'zingiz bilan suhbat" xatosi chiqadi.
        """
        from rest_framework.test import APIClient

        client = APIClient()
        r = client.post(
            "/api/v1/auth/send-otp/",
            {"phone": phone, "purpose": "register"},
            format="json",
        )
        assert r.status_code == 200, r.content
        code = r.json()["debug_code"]

        r = client.post(
            "/api/v1/auth/verify-otp/",
            {"phone": phone, "code": code, "purpose": "register", "email": email},
            format="json",
        )
        assert r.status_code == 200, r.content
        data = r.json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        return client, data

    def test_listings_feed_needs_auth_and_returns_fields(self):
        client, _ = self._register("+998901111111")

        r = client.get("/api/v1/listings/")
        assert r.status_code == 200, r.content
        rows = r.json().get("results", [])
        for row in rows:
            # Frontend shu maydonlarni ishlatadi
            for f in ("id", "title", "type", "price", "city", "owner_id", "main_image"):
                assert f in row, f"{f} javobda yo'q"

    def test_frontend_map_fields(self):
        """Xarita markerlari uchun lat/lng ommaviy ro'yxatda bo'lishi kerak."""
        from apps.housing.models import Listing
        from django.contrib.auth import get_user_model

        client, _ = self._register("+998901111111")
        owner = get_user_model().objects.get(phone="+998901111111")
        Listing.objects.create(
            owner=owner, title="Xarita testi", type="room",
            price=500000, city="Toshkent",
            status=Listing.Status.ACTIVE,
            lat=41.311081, lng=69.240562,
        )
        r = client.get("/api/v1/listings/")
        row = r.json()["results"][0]
        assert "lat" in row and "lng" in row
        assert row["lat"] and row["lng"]

    def test_favorites_flow(self):
        from django.contrib.auth import get_user_model

        client, _ = self._register("+998901111111")
        User = get_user_model()
        a = User.objects.get(phone="+998901111111")

        from apps.housing.models import Listing

        listing = Listing.objects.create(
            owner=a, title="Test xona", type="room", price=500000,
            city="Toshkent", status=Listing.Status.ACTIVE,
        )

        r = client.post(f"/api/v1/listings/{listing.id}/favorite/")
        assert r.status_code == 200 and r.json()["favorited"] is True
        r = client.post(f"/api/v1/listings/{listing.id}/favorite/")
        assert r.json()["favorited"] is False

    def test_chat_flow_from_card(self):
        from django.contrib.auth import get_user_model

        client, _ = self._register("+998901111111")
        self._register("+998902222222")
        b = get_user_model().objects.get(phone="+998902222222")

        # Frontend "Yozish" tugmasi conversation yaratadi
        r = client.post("/api/v1/conversations/", {"user_id": b.id}, format="json")
        assert r.status_code in (200, 201), r.content
        conv_id = r.json()["id"]

        r = client.post(
            f"/api/v1/conversations/{conv_id}/messages/", {"text": "Salom!"}, format="json"
        )
        assert r.status_code == 201, r.content

        r = client.get("/api/v1/conversations/")
        assert r.status_code == 200
        assert r.json()["results"][0]["last_message"]["text"] == "Salom!"

    def test_profile_patch_fields_used_by_frontend(self):
        client, _ = self._register("+998901111111", email="ali@tuit.uz")
        payload = {
            "full_name": "Ali Karimov", "city": "Toshkent",
            "university": "UzSWLU", "faculty": "Informatika", "bio": "Dasturchi",
        }
        r = client.patch("/api/v1/profile/me/", payload, format="json")
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["full_name"] == "Ali Karimov"
        assert body["city"] == "Toshkent"
        assert body["university"] == "UzSWLU"

    def test_verification_confirm(self):
        client, _ = self._register("+998901111111", email="ali@tuit.uz")
        r = client.post(
            "/api/v1/verification/email/send-code/", {"email": "ali@tuit.uz"}, format="json"
        )
        assert r.status_code == 200, r.content
        code = r.json()["debug_code"]

        r = client.post(
            "/api/v1/verification/email/confirm/",
            {"email": "ali@tuit.uz", "code": code}, format="json",
        )
        assert r.status_code == 200, r.content
        assert r.json()["is_verified"] is True

    def test_amenities_endpoint(self):
        client, _ = self._register("+998901111111")
        r = client.get("/api/v1/amenities/")
        assert r.status_code == 200

    def test_listing_create_with_multipart_images(self):
        """Frontend oqimi: verify -> listing create -> rasm upload."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        client, _ = self._register("+998901111111", email="ali@tuit.uz")

        # 1. Tasdiqlash
        code = client.post(
            "/api/v1/verification/email/send-code/",
            {"email": "ali@tuit.uz"}, format="json",
        ).json()["debug_code"]
        r = client.post(
            "/api/v1/verification/email/confirm/",
            {"email": "ali@tuit.uz", "code": code}, format="json",
        )
        assert r.status_code == 200, r.content

        # 2. E'lon yaratish
        r = client.post(
            "/api/v1/listings/",
            {
                "title": "Chilonzor metrosi yonida toza xona",
                "description": "Yangi ta'mirdan, 3-qavat",
                "type": "room", "price": "650000",
                "city": "Toshkent", "district": "Chilonzor", "rooms": 1,
            },
            format="json",
        )
        assert r.status_code == 201, r.content
        listing_id = r.json()["id"]

        # 3. Rasmlar alohida multipart so'rovda
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        img = SimpleUploadedFile("room.png", png, content_type="image/png")
        r = client.post(f"/api/v1/listings/{listing_id}/images/", {"images": img})
        assert r.status_code == 201, r.content

        # 4. Ro'yxatda ko'rinishi uchun `main_image` to'ldirilgan bo'lishi kerak
        from apps.housing.models import Listing

        listing = Listing.objects.get(pk=listing_id)
        assert listing.images.count() == 1
        r = client.get("/api/v1/listings/")
        row = next(x for x in r.json()["results"] if x["id"] == listing_id)
        assert row["main_image"], "main_image bo'sh"

    def test_listing_create_requires_verified_user(self):
        """Tasdiqlanmagan foydalanuvchi e'lon bera olmaydi."""
        client, _ = self._register("+998901111111")
        r = client.post(
            "/api/v1/listings/",
            {"title": "X", "type": "room", "price": "100", "city": "Toshkent"},
            format="json",
        )
        assert r.status_code == 403, r.content


class FrontendMarkupTests(TestCase):
    """HTML/JS da backend bilan mos kelmay qolgan joylar bo'lmasligi kerak."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open("templates/index.html", encoding="utf-8") as f:
            cls.html = f.read()

    def test_no_broken_button_tags(self):
        """`< button` (bo'sh joy bilan) — HTML parser uni buzadi."""
        import re

        broken = re.findall(r"<\s+(button|i|div|span)\b", self.html)
        assert not broken, f"buzilgan teglar: {set(broken)}"

    def test_no_mock_fetch_data_only(self):
        """E'lonlar mock massivdan emas, API dan olinadi."""
        assert "var housingData = [" not in self.html
        assert "housingListContainer" in self.html

    def test_ws_url_matches_backend_routing(self):
        """Backend: /ws/chat/<conversation_id>/ + Sec-WebSocket-Protocol."""
        assert "'/ws/chat/' + convId + '/'" in self.html
        assert "new WebSocket(url, ['bearer', state.access])" in self.html
        # Eski (xavfsiz emas) usul qolmagan bo'lishi kerak
        assert "?token=" not in self.html

    def test_listing_type_values_match_backend_choices(self):
        """Frontend select qiymatlari backend enum'ga mos bo'lishi kerak."""
        for value in ("room", "bedspace", "whole_apartment"):
            assert f'value="{value}"' in self.html, f"{value} yo'q"

    def test_mock_data_only_for_sections_without_api(self):
        """Young Job/Skill/Market/Food hali backend'siz — demo ma'lumot."""
        assert "var jobsData = [" in self.html
        assert "var foodData = [" in self.html

    def test_api_endpoints_exist_in_backend_urls(self):
        """Frontend ishlatadigan endpoint'lar backend'da mavjud bo'lishi kerak."""
        from django.urls import resolve

        paths = [
            "/api/v1/auth/send-otp/",
            "/api/v1/auth/verify-otp/",
            "/api/v1/auth/token/refresh/",
            "/api/v1/listings/",
            "/api/v1/listings/favorites/",
            "/api/v1/amenities/",
            "/api/v1/conversations/",
            "/api/v1/profile/me/",
            "/api/v1/verification/email/send-code/",
            "/api/v1/verification/email/confirm/",
        ]
        for p in paths:
            try:
                resolve(p)
            except Exception as exc:  # noqa: BLE001
                raise AssertionError(f"{p} backend'da yo'q: {exc}") from exc

    def test_user_cannot_set_owner(self):
        """E'lon egasini o'zgartirish yozish orqali mumkin emas."""
        from apps.housing.serializers import ListingWriteSerializer

        assert "owner" not in ListingWriteSerializer().fields
        assert "owner_id" not in ListingWriteSerializer().fields

    def test_every_function_called_in_markup_exists(self):
        """`onclick="fn()"` da chaqirilgan funksiyalar JS da bo'lishi SHART."""
        import re

        # Faqat HTML atributlaridagi chaqiruvlar (JS ichidagi built-in'lar emas)
        handlers = set(re.findall(r'on(?:click|change|keyup|keydown|load)="(\w+)\(', self.html))
        defined = set(re.findall(r"function\s+(\w+)\s*\(", self.html))
        # `var debouncedLoad = debounce(...)` kabi o'zgaruvchida e'lon qilinganlar
        defined |= set(re.findall(r"var\s+(\w+)\s*=\s*(?:debounce|\{)", self.html))
        # `onkeyup="if (event.key==='Enter') sendMessage()"` — `if` shart operatori
        missing = handlers - defined - {"if"}
        assert not missing, f"HTML da chaqiriladigan, lekin yo'q funksiyalar: {missing}"

    def test_removed_mock_functions_not_referenced(self):
        """Mock data bilan ishlagan eski funksiyalar qolmasin."""
        body = self.html.split("<script>")[-1]
        for gone in ("filterHousing(", "submitVerification(", "renderHousing("):
            # Faqat oxirgi "eski funksiyalar" izohida eslatilishi mumkin
            if gone in body:
                assert f"function {gone[:-1]}" not in body, f"{gone} hali mavjud"

    def test_form_inputs_have_ids(self):
        """`$('id')` bilan olinadigan barcha id HTML da mavjud bo'lishi SHART."""
        import re

        used = set(re.findall(r"\$\('([\w-]+)'\)", self.html))
        present = set(re.findall(r'id="([\w-]+)"', self.html))
        missing = used - present
        assert not missing, f"JS da ishlatiladigan, lekin HTML da yo'q id: {missing}"

    def test_no_localhost_hardcoded_urls(self):
        """Frontend localhostga bog'lanmasin — o'z domainida ishlasin."""
        assert "localhost:8000" not in self.html
        assert "127.0.0.1:8000" not in self.html

    # --- Telefon kiritish qulayligi --------------------------------------
    #
    # Sabab: `send-otp` 400 qaytarib, foydalanuvchi nima xato qilganini
    # tushmasligi mumkin edi. Endi raqam avtomatik formatlanadi va
    # validatsiya serverga yuborilishidan OLDIN bajariladi.

    def test_phone_input_has_formatting_hooks(self):
        """Telefon maydoni formatlash va validatsiya hook'lariga ega bo'lishi SHART."""
        phone_input = self.html.split('id="aPhone"')[1].split(">")[0]
        assert "oninput" in phone_input, "oninput hook yo'q"
        assert "formatPhoneInput" in phone_input
        assert "onblur" in phone_input, "onblur hook yo'q"
        assert "validatePhoneField" in phone_input

    def test_phone_formatting_functions_exist(self):
        """JS da formatlash/validatsiya funksiyalari bor bo'lishi SHART."""
        for fn in ("formatPhoneInput", "validatePhoneField", "setAuthHint"):
            assert f"function {fn}(" in self.html, f"{fn} funksiyasi yo'q"

    def test_phone_validated_before_send_otp(self):
        """`sendOtp` so'rovni yubormasdan oldin raqamni tekshirishi SHART.

        Aks holda noto'g'ri formatdagi so'rov serverga boradi va foydalanuvchi
        faqat `400` ko'radi (chiqindi hech qanday ko'rsatma bermaydi).
        """
        body = self.html.split("function sendOtp()")[1].split("function verifyOtp()")[0]
        assert "validatePhoneField" in body, "sendOtp validatsiyasiz"
        # validatsiya API chaqiruvidan OLDIN bo'lishi kerak
        assert body.index("validatePhoneField") < body.index("send-otp")

    def test_operator_codes_match_backend(self):
        """Frontend operator kodlari backend ro'yxati bilan BIR XIL bo'lishi SHART.

        Aks holda frontend "to'g'ri" deb qabul qilib, backend rad qiladi —
        yoki aksincha, foydalanuvchi noto'g'ri deb o'ylab to'g'ri kodni
        kiritmaydi. Ikkala tomon ham `apps/users/services.py` dan olinadi.
        """
        from apps.users.services import _DEFAULT_OPERATOR_CODES

        body = self.html.split("var UZ_OPERATOR_CODES = [")[1].split("];")[0]
        frontend = set(re.findall(r"'(\d{2})'", body))
        assert frontend == _DEFAULT_OPERATOR_CODES, (
            "Frontend va backend operator kodlari farq qiladi. "
            f"Faqat frontendda: {frontend - _DEFAULT_OPERATOR_CODES}; "
            f"faqat backendda: {_DEFAULT_OPERATOR_CODES - frontend}"
        )

    def test_phone_hint_shows_example_format(self):
        """Foydalanuvchi formatni ko'riishi uchun namuna ko'rsatilishi SHART."""
        assert "id=\"aPhoneHint\"" in self.html
        assert "+998 90 123 45 67" in self.html, "Format namuna ko'rsatilmagan"

    def test_auth_hint_has_error_styling(self):
        """Xato matni ko'rinib turishi SHART (jim qolmasligi kerak)."""
        assert ".hint.error" in self.html, "`.hint.error` stili yo'q"
        assert "function setAuthHint(" in self.html
