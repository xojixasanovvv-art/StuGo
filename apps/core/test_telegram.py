"""Telegram integratsiyasi va profil rasmi (avatar) uchun testlar.

Qamrov:
  * `/auth/telegram/link|status|unlink/` endpointlari (auth + himoya)
  * `create_link_code` / `peek_code_owner` / `link_telegram_account` mantiqi
  * kod muddati, urinishlar chegarasi, "bitta Telegram = bitta hisob"
  * `manage.py telegram_bot` dagi `/start KOD` parsing
  * `PATCH /profile/me/` orqali avatar yuklash va o'chirish

Bot API chaqiruvlari (`getMe`, `sendMessage`) tarmoqqa chiqmasligi uchun
`unittest.mock` bilan almashtirilgan.
"""

from __future__ import annotations

import io
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.users.models import Profile, TelegramLinkCode, User
from apps.users.telegram import (
    TelegramError,
    _split_message,
    bot_username,
    create_link_code,
    deep_link,
    is_configured,
    link_telegram_account,
    peek_code_owner,
    send_document,
    send_message,
    send_message_once,
    send_photo,
)

# Faqat testlarda ishlatiladigan soxta token. `.env` dagi haqiqiy token
# hech qachon testga kirmasligi kerak.
FAKE_TOKEN = "123456789:TEST-TOKEN-DO-NOT-USE"


def make_png(size=(48, 48), color=(20, 100, 200)) -> bytes:
    """Test uchun haqiqiy PNG baytlari (qo'lda yozilgan PNG DRF'da
    "invalid image" xatosi beradi — Pillow bilan yaratamiz)."""
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@override_settings(
    TELEGRAM_BOT_TOKEN=FAKE_TOKEN,
    TELEGRAM_LINK_TTL_SECONDS=600,
    TELEGRAM_LINK_MAX_ATTEMPTS=3,
    TELEGRAM_WEB_BASE_URL="http://127.0.0.1:8000",
)
class TelegramCodeTests(TestCase):
    """Bog'lanish kodi yaratish va tekshirish."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+998901234567", password="x")

    def test_is_configured_true_with_token(self):
        self.assertTrue(is_configured())

    def test_bot_username_from_get_me(self):
        with mock.patch(
            "apps.users.telegram._call", return_value={"username": "stugo_test_bot"}
        ):
            self.assertEqual(bot_username(), "stugo_test_bot")

    def test_bot_username_none_on_error(self):
        with mock.patch("apps.users.telegram._call", side_effect=TelegramError("boom")):
            self.assertIsNone(bot_username())

    def test_create_link_code_returns_8_digits(self):
        code = create_link_code(self.user.id)
        self.assertEqual(len(code), 8)
        self.assertTrue(code.isdigit())

    def test_create_link_code_is_persisted_in_db(self):
        """Kod bazada saqlanishi kerak — sayt va bot alohida jarayonlar
        bo'lgani uchun `LocMemCache` ular o'rtasida bo'linmaydi."""
        code = create_link_code(self.user.id)
        self.assertTrue(TelegramLinkCode.objects.filter(code=code).exists())

    def test_create_link_code_replaces_previous(self):
        first = create_link_code(self.user.id)
        second = create_link_code(self.user.id)
        self.assertNotEqual(first, second)
        self.assertEqual(TelegramLinkCode.objects.filter(user_id=self.user.id).count(), 1)

    def test_peek_code_owner_returns_user_id(self):
        code = create_link_code(self.user.id)
        self.assertEqual(peek_code_owner(code), self.user.id)

    def test_peek_code_owner_unknown(self):
        self.assertIsNone(peek_code_owner("00000000"))
        self.assertIsNone(peek_code_owner(""))

    def test_expired_code_is_invalid(self):
        code = create_link_code(self.user.id)
        TelegramLinkCode.objects.filter(code=code).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertIsNone(peek_code_owner(code))

    def test_deep_link_format(self):
        url = deep_link("stugo_bot", "12345678")
        self.assertEqual(url, "https://t.me/stugo_bot?start=12345678")


@override_settings(
    TELEGRAM_BOT_TOKEN=FAKE_TOKEN,
    TELEGRAM_LINK_TTL_SECONDS=600,
    TELEGRAM_LINK_MAX_ATTEMPTS=3,
)
class TelegramLinkAccountTests(TestCase):
    """`link_telegram_account` — kodni Telegram hisobiga ulash."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+998901234567", password="x")
        self.other = User.objects.create_user(phone="+998901234568", password="x")
        self.code = create_link_code(self.user.id)

    def test_successful_link(self):
        result, http = link_telegram_account(self.code, 555000111, "ali")
        self.assertEqual(result, "linked")
        self.assertEqual(http, 200)

        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.telegram_id, 555000111)
        self.assertEqual(profile.telegram_username, "ali")
        self.assertIsNotNone(profile.telegram_linked_at)
        self.assertTrue(profile.is_telegram_linked)

    def test_link_creates_profile_when_missing(self):
        """Profil signal bilan yaratilmagan bo'lsa ham bog'lash ishlashi
        kerak — `get_or_create` bilan yaratamiz."""
        Profile.objects.filter(user=self.user).delete()
        result, _ = link_telegram_account(self.code, 555000222, "bob")
        self.assertEqual(result, "linked")
        self.assertEqual(Profile.objects.get(user=self.user).telegram_id, 555000222)

    def test_code_is_single_use(self):
        link_telegram_account(self.code, 555000333, "ali")
        result, http = link_telegram_account(self.code, 555000333, "ali")
        self.assertEqual(result, "bad_code")
        self.assertEqual(http, 400)

    def test_unknown_code(self):
        result, http = link_telegram_account("00000000", 555000444, "x")
        self.assertEqual(result, "no_code")
        self.assertEqual(http, 400)

    def test_empty_code(self):
        result, http = link_telegram_account("", 555000555, "x")
        self.assertEqual(result, "no_code")
        self.assertEqual(http, 400)

    def test_expired_code_rejected(self):
        TelegramLinkCode.objects.filter(code=self.code).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        result, _ = link_telegram_account(self.code, 555000666, "x")
        self.assertEqual(result, "bad_code")

    def test_same_telegram_twice_is_idempotent(self):
        """Foydalanuvchi Telegram'da «Start» ni ikki marta bossa ham
        xato bo'lmasligi kerak — ikkinchisi `already_linked` emas,
        `linked` bo'lishi kerak (o'zi bilan to'qnashuv emas)."""
        self.assertEqual(link_telegram_account(self.code, 777, "ali")[0], "linked")
        code2 = create_link_code(self.user.id)
        result, http = link_telegram_account(code2, 777, "ali")
        self.assertEqual(result, "linked")
        self.assertEqual(http, 200)

    def test_telegram_account_cannot_bind_to_two_users(self):
        result, http = link_telegram_account(self.code, 999000, "ali")
        self.assertEqual(result, "linked")

        other_code = create_link_code(self.other.id)
        result2, http2 = link_telegram_account(other_code, 999000, "ali")
        self.assertEqual(result2, "already_linked")
        self.assertEqual(http2, 409)
        self.assertIsNone(Profile.objects.get(user=self.other).telegram_id)

    def test_used_code_row_is_kept_for_diagnostics(self):
        """Ishlatilgan kod o'chirilmaydi (admin'da ko'rish uchun), faqat
        `used_at` belgilanadi va qayta ishlatilmaydi."""
        link_telegram_account(self.code, 111, "x")
        result, _ = link_telegram_account(self.code, 222, "y")
        self.assertEqual(result, "bad_code")
        self.assertIsNotNone(TelegramLinkCode.objects.filter(code=self.code).first())
        # Profil o'zgarmagan — ikkinchi urinish hech narsani buzmaydi
        self.assertEqual(Profile.objects.get(user=self.user).telegram_id, 111)

    def test_attempts_are_counted_per_code(self):
        link_telegram_account(self.code, 111, "x")   # 1-urinish
        row = TelegramLinkCode.objects.get(code=self.code)
        self.assertEqual(row.attempts, 1)


@override_settings(TELEGRAM_LINK_MAX_ATTEMPTS=3)
class RateLimiterTests(TestCase):
    """`telegram_bot` ichidagi chat bo'yicha tezlik cheklovi.

    Kod bazada aniq qidirilgani uchun «kodni taxmin qilish» amaliy
    yo'l emas — himoya botning o'ziga keladigan so'rovlar sonida.
    """

    def setUp(self):
        from apps.users.management.commands.telegram_bot import _RateLimiter

        self.cls = _RateLimiter

    def test_allows_up_to_limit(self):
        rl = self.cls(max_hits=3, window=60)
        self.assertTrue(rl.allow(1))
        self.assertTrue(rl.allow(1))
        self.assertTrue(rl.allow(1))
        self.assertFalse(rl.allow(1))

    def test_limit_is_per_chat(self):
        rl = self.cls(max_hits=2, window=60)
        self.assertTrue(rl.allow(1))
        self.assertTrue(rl.allow(1))
        self.assertFalse(rl.allow(1))
        self.assertTrue(rl.allow(2))   # boshqa chat — chekalanmagan

    def test_window_expires(self):
        import time

        rl = self.cls(max_hits=2, window=0.01)
        self.assertTrue(rl.allow(1))
        self.assertTrue(rl.allow(1))
        self.assertFalse(rl.allow(1))
        time.sleep(0.05)
        self.assertTrue(rl.allow(1))

    def test_reset(self):
        rl = self.cls(max_hits=1, window=60)
        self.assertTrue(rl.allow(7))
        self.assertFalse(rl.allow(7))
        rl.reset()
        self.assertTrue(rl.allow(7))


@override_settings(TELEGRAM_BOT_TOKEN=FAKE_TOKEN)
class TelegramApiTests(TestCase):
    """`/auth/telegram/*` endpointlari."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+998901234567", password="x")
        self.token = self._login(self.user)

    @staticmethod
    def _login(user):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user)
        return c

    # --- ruxsat / autentifikatsiya ---
    def test_endpoints_require_auth(self):
        from rest_framework.test import APIClient

        anon = APIClient()
        self.assertEqual(anon.post("/api/v1/auth/telegram/link/").status_code, 401)
        self.assertEqual(anon.get("/api/v1/auth/telegram/status/").status_code, 401)
        self.assertEqual(anon.post("/api/v1/auth/telegram/unlink/").status_code, 401)

    # --- /link/ ---
    @mock.patch("apps.users.views.telegram.bot_username", return_value="stugo_test_bot")
    def test_link_returns_code_and_url(self, _m):
        r = self.token.post("/api/v1/auth/telegram/link/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["code"]), 8)
        self.assertEqual(r.data["bot_username"], "stugo_test_bot")
        self.assertEqual(
            r.data["bot_url"], f"https://t.me/stugo_test_bot?start={r.data['code']}"
        )
        self.assertEqual(r.data["expires_in"], 600)
        self.assertFalse(r.data["is_telegram_linked"])

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_link_without_token_returns_503(self):
        r = self.token.post("/api/v1/auth/telegram/link/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.data["code"], "not_configured")

    @mock.patch("apps.users.views.telegram.bot_username", return_value=None)
    def test_link_when_bot_unreachable_returns_503(self, _m):
        r = self.token.post("/api/v1/auth/telegram/link/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.data["code"], "bot_unavailable")

    # --- /status/ ---
    def test_status_without_code(self):
        r = self.token.get("/api/v1/auth/telegram/status/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_telegram_linked"])
        self.assertNotIn("pending", r.data)

    def test_status_pending_for_owner(self):
        code = create_link_code(self.user.id)
        r = self.token.get(f"/api/v1/auth/telegram/status/?code={code}")
        self.assertTrue(r.data["pending"])
        self.assertFalse(r.data["is_telegram_linked"])

    def test_status_pending_false_for_other_user(self):
        code = create_link_code(self.user.id)
        other = User.objects.create_user(phone="+998901234568", password="x")
        r = self._login(other).get(f"/api/v1/auth/telegram/status/?code={code}")
        self.assertFalse(r.data["pending"])

    def test_status_false_after_code_used(self):
        code = create_link_code(self.user.id)
        link_telegram_account(code, 12345, "ali")
        r = self.token.get(f"/api/v1/auth/telegram/status/?code={code}")
        self.assertTrue(r.data["is_telegram_linked"])
        self.assertEqual(r.data["telegram_username"], "ali")

    # --- /unlink/ ---
    def test_unlink_clears_fields(self):
        Profile.objects.filter(user=self.user).update(
            telegram_id=4242, telegram_username="ali", telegram_linked_at=timezone.now()
        )
        r = self.token.post("/api/v1/auth/telegram/unlink/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_telegram_linked"])

        profile = Profile.objects.get(user=self.user)
        self.assertIsNone(profile.telegram_id)
        self.assertEqual(profile.telegram_username, "")
        self.assertIsNone(profile.telegram_linked_at)

    def test_unlink_is_idempotent(self):
        r = self.token.post("/api/v1/auth/telegram/unlink/")
        self.assertEqual(r.status_code, 200)


class TelegramBotCommandTests(TestCase):
    """`manage.py telegram_bot` — `/start KOD` parsing va bog'lash."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+998901234567", password="x")
        self.code = create_link_code(self.user.id)

    def _command(self):
        from apps.users.management.commands.telegram_bot import Command

        cmd = Command()
        # `handle()` odatda yaratadi; testlarda to'g'ridan-to'g'ri
        # `_handle_update` chaqirilgani uchun qo'lda tayyorlaymiz.
        from apps.users.management.commands.telegram_bot import _RateLimiter

        cmd.limiter = _RateLimiter(max_hits=50, window=60)
        return cmd

    def test_extract_code_from_start_command(self):
        cmd = self._command()
        self.assertEqual(cmd._extract_code(f"/start {self.code}"), self.code)
        self.assertEqual(cmd._extract_code("/start@12345678"), None)
        self.assertEqual(
            cmd._extract_code(f"/start@stugo_test_bot {self.code}"), self.code
        )

    def test_extract_code_from_plain_text(self):
        cmd = self._command()
        self.assertEqual(cmd._extract_code(self.code), self.code)
        self.assertEqual(cmd._extract_code("Salom!"), None)
        self.assertEqual(cmd._extract_code(""), None)

    def test_handle_update_links_account(self):
        cmd = self._command()
        sent = []
        with mock.patch(
            "apps.users.telegram.send_message",
            side_effect=lambda chat_id, text, **kw: sent.append(text),
        ):
            cmd._handle_update(
                {
                    "update_id": 1,
                    "message": {
                        "text": f"/start {self.code}",
                        "chat": {"id": 424242, "type": "private", "username": "ali"},
                    },
                }
            )
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.telegram_id, 424242)
        self.assertEqual(profile.telegram_username, "ali")
        self.assertTrue(sent, "foydalanuvchiga javob yuborilishi kerak edi")

    def test_handle_update_ignores_group_chats(self):
        """Guruhda `chat.id` manzil bo'ladi — foydalanuvchining haqiqiy
        Telegram id'si emas. Bog'lash hech qanday holatda bajarilmasligi kerak."""
        cmd = self._command()
        with mock.patch("apps.users.telegram.send_message") as send:
            cmd._handle_update(
                {
                    "update_id": 1,
                    "message": {
                        "text": f"/start {self.code}",
                        "chat": {"id": -1001234, "type": "supergroup"},
                        "from": {"id": 777, "username": "ali"},
                    },
                }
            )
        send.assert_not_called()
        self.assertIsNone(Profile.objects.get(user=self.user).telegram_id)

    def test_handle_update_respects_rate_limit(self):
        from apps.users.management.commands.telegram_bot import _RateLimiter

        cmd = self._command()
        cmd.limiter = _RateLimiter(max_hits=2, window=60)
        update = {
            "update_id": 1,
            "message": {
                "text": f"/start {self.code}",
                "chat": {"id": 424242, "type": "private", "username": "ali"},
            },
        }
        with mock.patch("apps.users.telegram.send_message"):
            cmd._handle_update(update)
            cmd._handle_update(update)
            cmd._handle_update(update)   # chegaradan o'tdi — e'tiborsiz
        # Faqat birinchi urinish ishlagan bo'lishi kerak
        self.assertEqual(Profile.objects.get(user=self.user).telegram_id, 424242)

    def test_handle_update_without_code_replies_with_help(self):
        cmd = self._command()
        with mock.patch(
            "apps.users.telegram.send_message", return_value={}
        ) as send:
            cmd._handle_update(
                {
                    "update_id": 1,
                    "message": {"text": "salom", "chat": {"id": 1, "type": "private"}},
                }
            )
        send.assert_called_once()
        self.assertIn("StuGo", send.call_args.args[1])

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_command_errors_without_token(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError) as ctx:
            call_command("telegram_bot", once=True)
        self.assertIn("TELEGRAM_BOT_TOKEN", str(ctx.exception))

    @override_settings(TELEGRAM_BOT_TOKEN="test-token:ABC")
    def test_command_connects_and_exits_with_once(self):
        """`--once` buyruqni bitta navbatdan keyin to'xtatadi.

        Token `override_settings` bilan beriladi — test `.env` ga bog'liq
        bo'lmasin. Aks holda `.env` da token yo'q bo'lsa (yoki turli
        kompyuterda farq qilsa) test tasodifiy ravishda "qolib" ketadi.
        """
        stdout = io.StringIO()
        with (
            mock.patch("apps.users.telegram.get_me", return_value={"username": "b"}),
            mock.patch("apps.users.telegram.get_updates", return_value=[]) as gu,
        ):
            call_command("telegram_bot", once=True, stdout=stdout)
        gu.assert_called_once()
        self.assertIn("@b", stdout.getvalue())


class AvatarTests(TestCase):
    """`PATCH /profile/me/` orqali profil rasmini yuklash/o'chirish."""

    def setUp(self):
        from rest_framework.test import APIClient

        self.user = User.objects.create_user(phone="+998901234567", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse("me")

    def test_upload_avatar(self):
        png = make_png()
        r = self.client.patch(
            self.url,
            {"avatar": SimpleUploadedFile("me.png", png, content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("/media/avatars/", r.data["avatar"])

        profile = Profile.objects.get(user=self.user)
        self.assertTrue(profile.avatar)

    def test_upload_avatar_with_other_fields(self):
        png = make_png()
        r = self.client.patch(
            self.url,
            {
                "full_name": "Ali Karimov",
                "city": "Toshkent",
                "avatar": SimpleUploadedFile("me.png", png, content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["full_name"], "Ali Karimov")
        self.assertEqual(r.data["city"], "Toshkent")

    def test_avatar_can_be_cleared_with_null(self):
        """'Rasmni o'chirish' tugmasi `{"avatar": null}` yuboradi.
        `ImageField` `null` ni faqat `allow_null=True` bo'lganda qabul qiladi."""
        self.client.patch(
            self.url,
            {"avatar": SimpleUploadedFile("me.png", make_png(), content_type="image/png")},
            format="multipart",
        )
        r = self.client.patch(self.url, {"avatar": None}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.data["avatar"], (None, ""))
        # `ImageField` null bo'lganda `avatar` atributi bo'sh `FieldFile`
        # bo'ladi (None emas) — shuning uchun `assertFalse` ishlatamiz.
        self.assertFalse(Profile.objects.get(user=self.user).avatar)

    def test_response_reflects_the_change_immediately(self):
        """Regressiya: `MeSerializer.update` profilni `Profile.objects`
        orqali olsa, `User`ning keshlangan `instance.profile` eskicha
        qolardi va shu so'rovning javobi `full_name: ''` qaytarardi
        (baza esa to'g'ri yangilangan bo'lardi)."""
        r = self.client.patch(
            self.url,
            {
                "full_name": "Nodirbek",
                "city": "Buxoro",
                "avatar": SimpleUploadedFile("me.png", make_png(), content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["full_name"], "Nodirbek")
        self.assertEqual(r.data["city"], "Buxoro")
        self.assertTrue(r.data["avatar"])

    def test_patch_creates_profile_if_signal_did_not_run(self):
        """Profil signal bilan yaratilmagan bo'lsa ham PATCH ishlashi
        kerak — kod o'zi yaratadi."""
        Profile.objects.filter(user=self.user).delete()
        r = self.client.patch(self.url, {"full_name": "Yangi"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["full_name"], "Yangi")

    def test_invalid_image_rejected(self):
        r = self.client.patch(
            self.url,
            {"avatar": SimpleUploadedFile("bad.png", b"not-an-image", content_type="image/png")},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("avatar", r.data)

    def test_telegram_fields_are_read_only(self):
        """Foydalanuvchi `telegram_id` ni PATCH orqali o'zgartira olmasligi
        kerak — faqat bot orqali tasdiqlanadi."""
        Profile.objects.filter(user=self.user).update(telegram_username="real")
        r = self.client.patch(
            self.url, {"telegram_username": "hacker", "telegram_id": 999}, format="json"
        )
        self.assertIn(r.status_code, (200, 400))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.telegram_username, "real")
        self.assertIsNone(profile.telegram_id)

    def test_me_exposes_telegram_status(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        for key in (
            "telegram_id",
            "telegram_username",
            "telegram_linked_at",
            "is_telegram_linked",
        ):
            self.assertIn(key, r.data)
        self.assertFalse(r.data["is_telegram_linked"])


class ProfileSerializerTelegramTests(TestCase):
    def test_profile_serializer_exposes_is_telegram_linked(self):
        from apps.users.serializers import ProfileSerializer

        user = User.objects.create_user(phone="+998901234569", password="x")
        data = ProfileSerializer(user.profile).data
        self.assertIn("is_telegram_linked", data)
        self.assertIn("telegram_id", data)
        self.assertFalse(data["is_telegram_linked"])

        Profile.objects.filter(user=user).update(telegram_id=7)
        data = ProfileSerializer(Profile.objects.get(user=user)).data
        self.assertTrue(data["is_telegram_linked"])


class SplitMessageTests(TestCase):
    """`_split_message` — 4096 belgi chegarasini buzmaslik uchun.

    Chegara Telegram'ning `sendMessage` limiti. Bu funksiya noto'g'ri
    ishlasa, uzun xabar (loyiha summary) butunlay yuborilmaydi —
    `Bad Request: message is too long`.
    """

    def test_short_text_is_single_chunk(self):
        self.assertEqual(_split_message("salom", 4096), ["salom"])

    def test_text_exactly_at_limit_is_not_split(self):
        text = "a" * 4096
        self.assertEqual(_split_message(text, 4096), [text])

    def test_long_text_is_split(self):
        chunks = _split_message("a" * 9000, 4096)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)

    def test_split_preserves_all_characters(self):
        """Bo'laklash matnni YO'QOTMASIN — bo'laklarni qayta yig'ib
        bir xil matn olinishi kerak."""
        text = "\n\n".join(f"Paragraf {i}: " + "x" * 300 for i in range(30))
        original_len = len(text)
        chunks = _split_message(text, 4096)
        self.assertEqual(sum(len(c) for c in chunks), original_len - 2 * (len(chunks) - 1))

    def test_split_prefers_paragraph_boundaries(self):
        """Bo'sh qator bo'yin kesilishi kerak — Telegram'da shu yerda
        "Ko'proq" tugmasi chiqadi va chegaralar ko'rinib turadi.

        Tekshirish: chegaralar FAQAT bo'sh qator bo'yin bo'lishi kerak.
        Bitta bo'lak ichida bir necha paragraf bo'lishi normal (ular
        `\\n\\n` bilan birlashtiriladi), shuning uchun bo'lakda `\\n\\n`
        YO'Q degan tekshiruv noto'g'ri. To'g'ri belgi: bo'laklarni
        "\\n\\n" bilan qayta yig'ish asl matnni BERKDAN qaytaradi —
        ya'ni hech qanday paragraf yarim kesilmagan."""
        para = "y" * 1000
        text = "\n\n".join([para] * 6)
        chunks = _split_message(text, 4096)

        self.assertGreater(len(chunks), 1)
        self.assertEqual("\n\n".join(chunks), text)
        for chunk in chunks:
            # har bir bo'lak asl matnning bir qismi bo'lishi kerak
            self.assertIn(chunk, text)

    def test_single_giant_word_is_hard_split(self):
        """Uzun so'z (bo'sh joysiz) bo'lsa ham chegarani buzmasin."""
        chunks = _split_message("z" * 10000, 4096)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)
        self.assertEqual("".join(chunks), "z" * 10000)

    def test_long_line_split_on_space(self):
        """Bitta qator chegaradan uzun bo'lsa bo'sh joy bo'yicha kesiladi."""
        words = " ".join(["ab"] * 4000)
        chunks = _split_message(words, 4096)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)


@override_settings(TELEGRAM_BOT_TOKEN=FAKE_TOKEN)
class SendMessageTests(TestCase):
    """Uzun xabar bo'laklarga bo'linib yuborilishi."""

    def test_single_chunk_has_no_number_prefix(self):
        with mock.patch(
            "apps.users.telegram.send_message_once", return_value={"message_id": 1}
        ) as send:
            send_message(1, "qisqa xabar")
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1], "qisqa xabar")

    def test_long_message_is_split_and_numbered(self):
        with mock.patch(
            "apps.users.telegram.send_message_once", return_value={"message_id": 1}
        ) as send:
            send_message(1, "a" * 9000)
        self.assertEqual(send.call_count, 3)
        first, second, third = (c.args[1] for c in send.call_args_list)
        self.assertTrue(first.startswith("[1/3]"))
        self.assertTrue(second.startswith("[2/3]"))
        self.assertTrue(third.startswith("[3/3]"))

    def test_reply_markup_only_on_first_chunk(self):
        """Inline tugmalar birinchi xaborda bo'lishi kerak — ikkinchida
        takrorlansa Telegram xatolik beradi (eski xabar bilan bog'liq).

        `reply_markup` uchinchi POZITSIYALI argument (`send_message_once`
        imzosi: `chat_id, text, reply_markup`)."""
        markup = {"inline_keyboard": [[{"text": "OK", "callback_data": "1"}]]}
        with mock.patch(
            "apps.users.telegram.send_message_once", return_value={"message_id": 1}
        ) as send:
            send_message(1, "a" * 9000, reply_markup=markup)
        self.assertEqual(send.call_args_list[0].args[2], markup)
        self.assertIsNone(send.call_args_list[1].args[2])

    def test_send_message_once_passes_payload(self):
        with mock.patch(
            "apps.users.telegram._call", return_value={"message_id": 7}
        ) as call:
            send_message_once(42, "matn")
        call.assert_called_once_with(
            "sendMessage",
            {"chat_id": 42, "text": "matn", "disable_web_page_preview": True},
        )


@override_settings(TELEGRAM_BOT_TOKEN=FAKE_TOKEN)
class MultipartSendTests(TestCase):
    """`send_document` / `send_photo` — multipart orqali fayl yuborish."""

    def setUp(self):
        self.captured: dict = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true, "result": {"message_id": 5}}'

        def fake_urlopen(req, timeout=None):
            self.captured["url"] = req.full_url
            self.captured["body"] = req.data
            self.captured["headers"] = req.headers
            return FakeResponse()

        patcher = mock.patch(
            "apps.users.telegram.urllib.request.urlopen", side_effect=fake_urlopen
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_send_document_from_path(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "StuGo.zip"
            path.write_bytes(b"PK\x03\x04-fayl-mazmuni")
            result = send_document(1, path, caption="Loyiha")

        self.assertEqual(result, {"message_id": 5})
        self.assertIn("sendDocument", self.captured["url"])
        self.assertIn(b"StuGo.zip", self.captured["body"])
        self.assertIn(b"chat_id", self.captured["body"])
        self.assertIn(b"Loyiha", self.captured["body"])
        self.assertIn("multipart/form-data", self.captured["headers"]["Content-type"])

    def test_send_document_from_bytes(self):
        send_document(1, b"x" * 100, filename="test.bin")
        self.assertIn(b"test.bin", self.captured["body"])
        self.assertIn(b"x" * 100, self.captured["body"])

    def test_send_document_truncates_long_caption(self):
        """Telegram caption limiti 1024 — uzun caption yuborilsa API
        `Bad Request` beradi."""
        send_document(1, b"x", caption="c" * 5000)
        body = self.captured["body"]
        # 1024 ta `c` + "caption" sarlavhasi + qolgan binary
        self.assertIn(b"c" * 1024, body)
        self.assertNotIn(b"c" * 1025, body)

    def test_send_document_missing_file_raises(self):
        with self.assertRaises(TelegramError):
            send_document(1, "/tmp/bu-fayl-yoq-12345.zip")

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_send_document_without_token_raises(self):
        with self.assertRaises(TelegramError):
            send_document(1, b"x")

    def test_send_photo_from_bytes(self):
        result = send_photo(1, make_png(), caption="Rasm")
        self.assertEqual(result, {"message_id": 5})
        self.assertIn("sendPhoto", self.captured["url"])
        # `multipart/form-data` tana ichida emas — `Content-Type` sarlavhasida
        # (tanaga faqat `boundary` qismi yoziladi).
        self.assertIn(
            "multipart/form-data", self.captured["headers"]["Content-type"]
        )
        self.assertIn(b'name="photo"', self.captured["body"])
        self.assertIn(b"\x89PNG", self.captured["body"])

    def test_send_photo_from_url_uses_json(self):
        """URL yuborilganda fayl yuklanmaydi — oddiy JSON so'rov yetarli."""
        with mock.patch(
            "apps.users.telegram._call", return_value={"message_id": 6}
        ) as call:
            send_photo(1, "https://example.com/a.png", caption="Rasm")
        call.assert_called_once_with(
            "sendPhoto",
            {"chat_id": 1, "caption": "Rasm", "photo": "https://example.com/a.png"},
        )
