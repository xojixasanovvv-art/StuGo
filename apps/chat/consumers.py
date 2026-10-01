"""TZ 5.5 — Real vaqt chat (WebSocket /ws/chat/)."""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

MAX_TEXT_LENGTH = 4000
RATE_LIMIT_WINDOW = 10.0  # soniya
RATE_LIMIT_MESSAGES = 10  # shu oynada


class ChatConsumer(AsyncWebsocketConsumer):
    """1-ga-1 suhbat uchun WebSocket.

    Ulanish (TARXIYA: query param emas):
        ws://host/ws/chat/<conversation_id>/
        `Authorization: Bearer <access_token>` header yoki
        `Sec-WebSocket-Protocol: bearer, <access_token>`

    Eslatma: eski versiya `?token=` ni qabul qilardi. Query string token
    nginx access log'iga, brauzer history'siga va monitoring tizimlariga
    yozilib ketadi — xabar o'rniga to'g'ridan-to'g'ri kirish kaliti.

    Yuborish: {"text": "Salom"}
    Qabul: {"id": 1, "text": "Salom", "sender_id": 1, "created_at": "..."}
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.conversation = None
        self.conversation_id = None
        self._sent_times = []

    async def connect(self):
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import AccessToken

        token = self._get_token()
        if token is None:
            await self.close(code=4401)
            return

        try:
            access = AccessToken(token)
            user_id = access["user_id"]
        except TokenError:
            await self.close(code=4401)
            return

        self.user = await self._get_user(user_id)
        if self.user is None or not self.user.is_active:
            await self.close(code=4403)
            return

        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.conversation = await self._get_conversation()
        if self.conversation is None:
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(f"chat_{self.conversation_id}", self.channel_name)
        # Subprotocol'ni qaytarish SHART (RFC 6455): mijoz `bearer, <token>`
        # taklif qilgan — server tanlaganini `Sec-WebSocket-Protocol` da
        # e'lon qilishi kerak. Aks holda qat'iy WS kutubxonalari
        # ("Invalid WebSocket Header") ulanishni rad qiladi.
        await self.accept(subprotocol="bearer")

    def _get_token(self) -> str | None:
        """Token faqat header'dan olinadi (subprotocol orqali).

        `Sec-WebSocket-Protocol: bearer, <token>` — brauzer WebSocket API
        header qo'yishga yo'l qo'ymaydi, shuning uchun bu standart usul.
        """
        for name, value in self.scope.get("headers") or []:
            lname = name.lower()
            if lname == b"authorization":
                raw = value.decode(errors="ignore")
                if raw.lower().startswith("bearer "):
                    return raw.split(" ", 1)[1].strip()
            elif lname == b"sec-websocket-protocol":
                parts = [p.strip() for p in value.decode(errors="ignore").split(",")]
                if len(parts) == 2 and parts[0].lower() in {"bearer", "jwt"}:
                    return parts[1]
        return None

    @database_sync_to_async
    def _get_user(self, user_id):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.filter(pk=user_id).first()

    @database_sync_to_async
    def _get_conversation(self):
        """Suhbatni bir marta yuklaydi va bloklashni ham tekshiradi."""
        from apps.chat.models import Conversation
        from apps.chat.services import participants_blocked

        conv = (
            Conversation.objects.filter(pk=self.conversation_id, participants=self.user)
            .select_related("user_low", "user_high")
            .first()
        )
        if conv is None:
            return None
        if participants_blocked(conv, self.user):
            return None
        return conv

    async def disconnect(self, code):
        if self.conversation_id:
            await self.channel_layer.group_discard(
                f"chat_{self.conversation_id}", self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self._error("JSON formati noto'g'ri.")
            return

        if not isinstance(data, dict):
            await self._error("JSON formati noto'g'ri.")
            return

        text = (data.get("text") or "").strip() if isinstance(data.get("text"), str) else ""
        if not text:
            await self._error("Xabar bo'sh.")
            return

        # Uzunlikni WebSocket darajasida tekshiramiz — aks holda model
        # chegarasi `DataError` berib, 500 qaytarardi.
        if len(text) > MAX_TEXT_LENGTH:
            await self._error(f"Xabar {MAX_TEXT_LENGTH} belgidan uzun bo'lmasligi kerak.")
            return

        if not self._within_rate_limit():
            await self._error("Juda tez yuborilmoqda. Biroz kutib turing.")
            return

        message = await self._save_message(text)
        if "error" in message:
            await self.send(text_data=json.dumps(message))
            return

        await self.channel_layer.group_send(
            f"chat_{self.conversation_id}",
            {"type": "chat.message", "message": message},
        )

    def _within_rate_limit(self) -> bool:
        now = timezone.now().timestamp()
        self._sent_times = [t for t in self._sent_times if now - t < RATE_LIMIT_WINDOW]
        if len(self._sent_times) >= RATE_LIMIT_MESSAGES:
            return False
        self._sent_times.append(now)
        return True

    async def _error(self, message: str) -> None:
        await self.send(text_data=json.dumps({"error": message}))

    @database_sync_to_async
    def _save_message(self, text: str) -> dict:
        from apps.chat.services import create_message

        # `self.conversation` `connect()` da bir marta yuklangan — har bir
        # xabar uchun qayta so'rov yuborilmaydi.
        message = create_message(self.conversation, self.user, text=text)
        if message is None:
            return {"error": "Xabar yuborilmadi."}

        return {
            "id": message.pk,
            "conversation_id": self.conversation.pk,
            "sender_id": self.user.pk,
            "text": message.text,
            "created_at": timezone.localtime(message.created_at).isoformat(),
        }

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"]))