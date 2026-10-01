from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.chat.models import Conversation, Message
from apps.roommates.serializers import mask_phone


class MessageSerializer(serializers.ModelSerializer):
    sender_phone = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "conversation", "sender", "sender_phone", "text", "image", "read_at", "created_at"]
        read_only_fields = ["id", "sender", "conversation", "read_at", "created_at"]

    def get_sender_phone(self, obj) -> str | None:
        # To'liq raqam suhbat ichida kerak emas — qisman ko'rsatiladi.
        return mask_phone(obj.sender.phone)


class UserBriefSerializer(serializers.Serializer):
    """Suhbatdagi sherik qisqa ma'lumotlari (telefon maskalangan holda).

    `full_name` va `avatar` alohida qo'shilgan: frontend (`renderChat`,
    `partnerName`) avval faqat maskalangan telefon ko'rsatardi —
    "+9989*****68" deb yozilgan suhbat ro'yxati foydalanuvchi uchun
    tushunarsiz edi. Endi ism (yoki avatar) ko'rinadi.
    """

    id = serializers.IntegerField()
    full_name = serializers.CharField(allow_blank=True)
    avatar = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    is_verified = serializers.BooleanField()


def _brief(user) -> dict:
    """`User` -> `UserBriefSerializer` ga mos ma'lumotlar.

    `user` ba'zan autentifikatsiya qilinmagan (o'chirilgan) foydalanuvchi
    bo'lishi mumkin — shunda `Profile` ham yo'q bo'ladi.
    """
    profile = getattr(user, "profile", None)
    return {
        "id": user.id,
        "full_name": (profile.full_name if profile else "") or "",
        "avatar": (profile.avatar.url if profile and profile.avatar else None),
        "phone": mask_phone(user.phone),
        "is_verified": user.is_verified,
    }


class ConversationSerializer(serializers.ModelSerializer):
    """Suhbat ro'yxati — qarama-qarshi ishtirokchi va oxirgi xabar bilan."""

    partner = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ["id", "partner", "last_message", "unread_count", "updated_at"]

    @extend_schema_field(UserBriefSerializer)
    def get_partner(self, obj):
        return _brief(obj.partner_for(self.context["request"].user))

    @extend_schema_field({"type": "object", "nullable": True})
    def get_last_message(self, obj):
        # N+1 oldini olish: `prefetch_related("messages")` ishlatiladi.
        msgs = getattr(obj, "messages_cache", None)
        msg = msgs[-1] if msgs else None
        if msg is None:
            return None
        text = (msg.text or "")[:80]
        return {
            "text": text,
            "has_image": bool(msg.image),
            "created_at": msg.created_at,
        }

    @extend_schema_field(serializers.IntegerField)
    def get_unread_count(self, obj):
        msgs = getattr(obj, "messages_cache", None)
        if msgs is None:
            return 0
        me = self.context["request"].user
        return sum(1 for m in msgs if m.read_at is None and m.sender_id != me.id)


class ConversationCreateSerializer(serializers.Serializer):
    """Yangi suhbat boshlash (yoki mavjudini qaytarish)."""

    user_id = serializers.IntegerField()

    def validate_user_id(self, value):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        request = self.context["request"]
        if not User.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Foydalanuvchi topilmadi.")
        if value == request.user.id:
            raise serializers.ValidationError("O'zingiz bilan suhbat ochib bo'lmaydi.")

        # Bloklash to'liq amalga oshishi uchun: bloklagan tomondan
        # murojaat qilish mumkin emas (avval faqat yuborish bloklangan edi).
        from apps.reports.models import Block

        blocked = Block.objects.filter(
            Q(blocker_id=request.user.id, blocked_id=value)
            | Q(blocker_id=value, blocked_id=request.user.id)
        )
        if blocked.exists():
            raise serializers.ValidationError("Bu foydalanuvchi bilan aloqa mumkin emas.")
        return value