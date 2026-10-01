from django.db import models
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.roommates.models import Match, RoommateProfile


def mask_phone(phone: str | None) -> str | None:
    """Telefon raqamni qisman yashiradi: +998901234567 -> +998*****67.

    To'liq raqam faqat `accept` qilingan match'da ochiladi.
    """
    if not phone:
        return None
    digits = str(phone)
    if len(digits) < 6:
        return "***"
    return f"{digits[:5]}*****{digits[-2:]}"


class RoommateProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.profile.full_name", read_only=True)
    is_verified = serializers.BooleanField(source="user.is_verified", read_only=True)

    class Meta:
        model = RoommateProfile
        fields = [
            "id", "user", "full_name", "is_verified", "looking_for",
            "budget_min", "budget_max", "city", "district", "move_in_date",
            "gender_pref", "sleep_schedule", "cleanliness", "smoking",
            "guests_ok", "pets", "about", "is_active", "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]


class MatchSerializer(serializers.ModelSerializer):
    partner = serializers.SerializerMethodField()
    partner_profile = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = ["id", "partner", "partner_profile", "score", "status", "created_at"]

    @extend_schema_field(serializers.DictField)
    def get_partner(self, obj):
        partner = obj.partner_for(self.context["request"].user)
        # To'liq telefon raqami faqat qabul qilingan match'da ochiladi.
        phone = partner.phone if obj.status == Match.Status.ACCEPTED else None
        return {
            "id": partner.id,
            "phone": phone,
            "phone_masked": mask_phone(partner.phone),
            "is_verified": partner.is_verified,
        }

    @extend_schema_field({"type": "object", "nullable": True})
    def get_partner_profile(self, obj):
        partner = obj.partner_for(self.context["request"].user)
        prof = getattr(partner, "roommate_profile", None)
        if prof is None:
            return None
        return RoommateProfileSerializer(prof, context=self.context).data


class MatchRequestSerializer(serializers.Serializer):
    """Yangi roommate so'rovi yaratish uchun."""

    partner_id = serializers.IntegerField()

    def validate_partner_id(self, value):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        request = self.context["request"]
        if value == request.user.id:
            raise serializers.ValidationError("O'zingizga so'rov yubora olmaysiz.")
        if not User.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Foydalanuvchi topilmadi.")
        return value

    def validate(self, attrs):
        from django.contrib.auth import get_user_model

        from apps.reports.models import Block

        User = get_user_model()
        request = self.context["request"]
        partner = User.objects.filter(id=attrs["partner_id"]).first()
        if partner is None:
            raise serializers.ValidationError({"partner_id": "Foydalanuvchi topilmadi."})

        # Ikki tomonlama bloklash tekshiruvi
        if Block.objects.filter(
            models.Q(blocker=request.user, blocked=partner)
            | models.Q(blocker=partner, blocked=request.user)
        ).exists():
            raise serializers.ValidationError("Bu foydalanuvchi bilan muloqot cheklangan.")

        # View `validated_data["partner"]` ni ishlatadi
        attrs["partner"] = partner
        return attrs

    def create(self, validated_data):
        return validated_data["partner_id"]


class MatchDecisionSerializer(serializers.Serializer):
    """accept yoki reject."""

    decision = serializers.ChoiceField(choices=["accept", "reject"])
