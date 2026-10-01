from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.reports.models import Block, Report


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id", "target_type", "target_id", "reason", "description",
            "status", "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate(self, attrs):
        # O'ziga shikoyat qilishni cheklash (user uchun)
        if attrs.get("target_type") == Report.TargetType.USER:
            if attrs.get("target_id") == self.context["request"].user.id:
                raise serializers.ValidationError("O'zingizga shikoyat qila olmaysiz.")
        return attrs


class BlockSerializer(serializers.ModelSerializer):
    blocked_id = serializers.IntegerField(write_only=True)
    blocked = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Block
        fields = ["id", "blocked_id", "blocked", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_blocked_id(self, value):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("Foydalanuvchi topilmadi.")
        if value == self.context["request"].user.id:
            raise serializers.ValidationError("O'zingizni bloklab bo'lmaydi.")
        return value

    @extend_schema_field(serializers.DictField)
    def get_blocked(self, obj):
        return {"id": obj.blocked.id, "phone": obj.blocked.phone}

    def create(self, validated_data):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        blocked = User.objects.get(id=validated_data.pop("blocked_id"))
        block, _ = Block.objects.get_or_create(
            blocker=self.context["request"].user, blocked=blocked
        )
        return block


class ReportDecisionSerializer(serializers.Serializer):
    """Moderator qarori: shikoyatni yopish yoki rad etish."""

    decision = serializers.ChoiceField(choices=["resolve", "dismiss"])
