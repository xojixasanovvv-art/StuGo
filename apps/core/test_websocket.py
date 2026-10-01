"""WebSocket chat — frontend bilan mos kelishi tekshiriladi.

Frontend (`templates/index.html`) backend protokolini shu tarzda ishlatadi:
    - URL:   ``/ws/chat/<conversation_id>/``
    - Token: ``Sec-WebSocket-Protocol: bearer, <access_token>``

Bu test aynan shu e'lonlarni tekshiradi — agar backend tomonda routing
yoki token olish tarxi o'zgarsa, frontend darhol ishlamay qoladi.
"""

import json

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from config.asgi import application

User = get_user_model()


@override_settings(
    DEBUG=True,
    OTP_DEBUG_RETURN_CODE=True,
    ALLOWED_HOSTS=["testserver", "localhost"],
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class WebSocketChatTests(TransactionTestCase):
    """TransactionTestCase — channel layer va transaction mos kelishi uchun."""

    reset_sequences = True

    def setUp(self):
        super().setUp()
        # Throttle hisoblari keshda — har testda tozalash SHART, aks holda
        # "Expected available in 3600 seconds" xatosi chiqadi.
        cache.clear()

    def _register(self, phone):
        c = APIClient()
        r = c.post(
            "/api/v1/auth/send-otp/",
            {"phone": phone, "purpose": "register"},
            format="json",
        )
        assert r.status_code == 200, r.content
        code = r.json()["debug_code"]
        r = c.post(
            "/api/v1/auth/verify-otp/",
            {"phone": phone, "code": code, "purpose": "register"},
            format="json",
        )
        assert r.status_code == 200, r.content
        data = r.json()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {data['access']}")
        return c, data["access"]

    def _conversation(self, client, other_id):
        r = client.post("/api/v1/conversations/", {"user_id": other_id}, format="json")
        assert r.status_code in (200, 201), r.content
        return r.json()["id"]

    def _connect(self, conv_id, token, origin=b"http://testserver"):
        """Frontend `new WebSocket(url, ['bearer', token])` ga mos ulanish."""
        comm = WebsocketCommunicator(
            application,
            f"/ws/chat/{conv_id}/",
            headers=[
                (b"sec-websocket-protocol", f"bearer, {token}".encode()),
                (b"origin", origin),
            ],
        )
        return comm

    def test_message_roundtrip(self):
        client_a, token_a = self._register("+998901111111")
        client_b, token_b = self._register("+998902222222")
        a = User.objects.get(phone="+998901111111")
        b = User.objects.get(phone="+998902222222")

        conv_id = self._conversation(client_b, a.id)

        async def run():
            comm = self._connect(conv_id, token_b)
            connected, code = await comm.connect()
            assert connected, f"Ulanish rad etildi: code={code}"

            await comm.send_to(text_data=json.dumps({"text": "Salom, xona bormi?"}))
            decoded = await comm.receive_from(timeout=5)

            await comm.disconnect()
            return json.loads(decoded)

        resp = async_to_sync(run)()
        assert resp["text"] == "Salom, xona bormi?"
        assert resp["sender_id"] == b.id
        assert resp["conversation_id"] == conv_id

        # Xabar bazaga ham yozilgan bo'lishi kerak
        r = client_b.get(f"/api/v1/conversations/{conv_id}/messages/")
        assert r.status_code == 200
        assert r.json()["results"][0]["text"] == "Salom, xona bormi?"
        del client_a, token_a

    def test_no_token_rejected(self):
        """Token berilmasa — ulanish yopiladi (frontend kabi 4401)."""
        self._register("+998901111111")
        client_b, _ = self._register("+998902222222")
        a = User.objects.get(phone="+998901111111")
        conv_id = self._conversation(client_b, a.id)

        async def run():
            comm = WebsocketCommunicator(
                application,
                f"/ws/chat/{conv_id}/",
                headers=[(b"origin", b"http://testserver")],
            )
            return await comm.connect()

        connected, code = async_to_sync(run)()
        assert connected is False
        assert code == 4401

    def test_participant_can_connect_own_conversation(self):
        """Suhbat ishtirokchisi o'z suhbatiga ulanishi MUMKIN."""
        client_a, _ = self._register("+998901111111")
        client_b, token_b = self._register("+998902222222")
        a = User.objects.get(phone="+998901111111")

        conv_id = self._conversation(client_b, a.id)

        async def run():
            comm = self._connect(conv_id, token_b)
            connected, code = await comm.connect()
            if connected:
                await comm.disconnect()
            return connected, code

        connected, _ = async_to_sync(run)()
        assert connected is True

    def test_outsider_cannot_connect(self):
        """Suhbatga tegishli bo'lmagan foydalanuvchi ulanish olmaydi."""
        client_a, _ = self._register("+998901111111")
        client_b, _ = self._register("+998902222222")
        _, token_c = self._register("+998903333333")
        a = User.objects.get(phone="+998901111111")
        c = User.objects.get(phone="+998903333333")

        # A-B suhbati
        conv_id = self._conversation(client_b, a.id)

        async def run():
            comm = self._connect(conv_id, token_c)
            return await comm.connect()

        connected, code = async_to_sync(run)()
        assert connected is False
        assert code == 4403
        del c

    def test_blocked_user_cannot_connect(self):
        """Bloklangan ishtirokchi ulanish olmaydi."""
        client_a, _ = self._register("+998901111111")
        client_b, token_b = self._register("+998902222222")
        a = User.objects.get(phone="+998901111111")
        b = User.objects.get(phone="+998902222222")

        conv_id = self._conversation(client_b, a.id)

        # A bloklaydi
        r = client_a.post("/api/v1/users/blocks/", {"blocked_id": b.id}, format="json")
        assert r.status_code in (200, 201), r.content

        async def run():
            comm = self._connect(conv_id, token_b)
            return await comm.connect()

        connected, code = async_to_sync(run)()
        assert connected is False
        assert code == 4403

    def test_empty_text_rejected(self):
        client_a, _ = self._register("+998901111111")
        client_b, token_b = self._register("+998902222222")
        a = User.objects.get(phone="+998901111111")
        conv_id = self._conversation(client_b, a.id)

        async def run():
            comm = self._connect(conv_id, token_b)
            connected, _ = await comm.connect()
            assert connected
            await comm.send_to(text_data=json.dumps({"text": "   "}))
            decoded = await comm.receive_from(timeout=5)
            await comm.disconnect()
            return json.loads(decoded)

        resp = async_to_sync(run)()
        assert "error" in resp