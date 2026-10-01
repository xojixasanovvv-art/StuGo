from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.models import Profile, VerificationMethod, VerificationRequest
from apps.users.services import normalize_phone

User = get_user_model()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class PhoneMixin:
    """Telefon raqamni E.164 ko'rinishiga keltiradi, xatoni 400 qiladi."""

    def validate_phone(self, value):
        # DRF standart xatosi inglizcha ("This field may not be blank.").
        # Platforma o'zbek tilida — foydalanuvchi tushunishi uchun o'zbekchaga
        # o'tkazamiz.
        if value is None or not str(value).strip():
            raise serializers.ValidationError("Telefon raqamni kiriting.")
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


def phone_field(**kwargs) -> serializers.CharField:
    """Telefon maydoni — barcha xatolari o'zbek tilida.

    DRF `CharField` bo'sh/null qiymatni `validate_<field>` dan O'TKAZIB
    yuboradi va o'z inglizcha xatosini qaytaradi ("This field may not be
    blank.", "Not a valid string."). Platforma o'zbekchani talab qilgani
    uchun `allow_blank`/`allow_null` ni o'chirib, validatsiyani
    `PhoneMixin.validate_phone` ga yo'naltiramiz.
    """
    return serializers.CharField(
        max_length=20,
        allow_blank=False,
        allow_null=False,
        trim_whitespace=True,
        error_messages={
            "blank": "Telefon raqamni kiriting.",
            "null": "Telefon raqamni kiriting.",
            "max_length": "Telefon raqam juda uzun.",
            "invalid": "Telefon raqam matn emas.",
        },
        **kwargs,
    )


class SendOTPSerializer(PhoneMixin, serializers.Serializer):
    phone = phone_field()
    purpose = serializers.ChoiceField(choices=["register", "login"], default="register")

    def validate(self, attrs):
        """Foydalanuvchi mavjudligini oshkor QILMAYDI.

        Aks holda `AllowAny` endpoint haker uchun telefon ro'yxatini
        tekshirish (enumeration) vositasiga aylanadi. Shu sababli bu yerda
        hech qanday "allaqachon ro'yxatdan o'tgan" xatosi qaytarilmaydi —
        bir xil javob har ikkala holatda ham beriladi.
        """
        return attrs


class VerifyOTPSerializer(PhoneMixin, serializers.Serializer):
    phone = phone_field()
    code = serializers.CharField(
        max_length=8,
        min_length=4,
        write_only=True,
        error_messages={
            "blank": "Kodni kiriting.",
            "null": "Kodni kiriting.",
            "min_length": "Kod kamida 4 ta raqamdan iborat bo'lishi kerak.",
            "max_length": "Kod juda uzun.",
        },
    )
    purpose = serializers.ChoiceField(choices=["register", "login"], default="register")
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        default="",
        error_messages={"invalid": "Email noto'g'ri. Namuna: ali@tuit.uz"},
    )


class UserSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    has_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "phone", "email", "role", "gender", "is_verified", "has_profile", "date_joined"]
        # `role` yoziladigan maydon bo'lsa — moderator/owner huquqlariga
        # o'tish mumkin. Faqat server tomonidan o'zgarishi kerak.
        read_only_fields = ["id", "date_joined", "role", "is_verified"]

    def get_has_profile(self, obj) -> bool:
        return hasattr(obj, "profile")


class ProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Profile
        fields = [
            "user", "full_name", "avatar", "birth_date", "gender", "city",
            "university", "faculty", "course", "bio", "languages", "interests",
        ]
        read_only_fields = ["user"]


class MeSerializer(serializers.ModelSerializer):
    """`/profile/me/` — foydalanuvchi + uning profili bitta javobda.

    Eslatma: `full_name`, `avatar`, `city` `Profile` modelida,
    `email`/`gender` esa `User` modelida. Frontend uchun ikkita alohida
    endpoint qilish chalkash edi, shuning uchun bu yerda bitta
    serializer birlashtirilgan.
    """

    profile = ProfileSerializer(read_only=True)
    has_profile = serializers.SerializerMethodField()
    full_name = serializers.CharField(source="profile.full_name", required=False)
    avatar = serializers.ImageField(source="profile.avatar", required=False)
    city = serializers.CharField(source="profile.city", required=False)
    university = serializers.CharField(source="profile.university", required=False)
    faculty = serializers.CharField(source="profile.faculty", required=False)
    bio = serializers.CharField(source="profile.bio", required=False)

    class Meta:
        model = User
        fields = [
            "id", "phone", "email", "role", "gender", "is_verified",
            "has_profile", "full_name", "avatar", "city", "university",
            "faculty", "bio", "profile", "date_joined",
        ]
        read_only_fields = ["id", "phone", "date_joined", "role", "is_verified"]

    def get_has_profile(self, obj) -> bool:
        return hasattr(obj, "profile")

    def update(self, instance, validated_data):
        # `source="profile.*"` bo'lgani uchun DRF `validated_data` da
        # ular `{"profile": {...}}` ko'rinishida yig'iladi va
        # `super().update()` "writable dotted-source fields" xatosini beradi.
        # Shuning uchun ularni avval ajratib, `Profile` ga o'zimiz yozamiz.
        profile_data = validated_data.pop("profile", {}) or {}

        instance = super().update(instance, validated_data)

        if profile_data:
            profile, _ = Profile.objects.get_or_create(user=instance)
            for key, value in profile_data.items():
                setattr(profile, key, value)
            profile.save(update_fields=list(profile_data.keys()))

        return instance


def _validate_image(image, field_name: str) -> None:
    """Rasmlar uchun hajm va tur tekshiruvi (storage amplification ga qarshi)."""
    if image is None:
        raise serializers.ValidationError({field_name: "Rasm yuklanishi shart."})
    if image.size > MAX_UPLOAD_BYTES:
        raise serializers.ValidationError(
            {field_name: f"Rasm hajmi {MAX_UPLOAD_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."}
        )
    content_type = (getattr(image, "content_type", "") or "").lower()
    name = (getattr(image, "name", "") or "").lower()
    ext_ok = any(name.endswith(e) for e in ALLOWED_EXTENSIONS)
    if content_type not in ALLOWED_IMAGE_TYPES or not ext_ok:
        raise serializers.ValidationError(
            {field_name: "Faqat JPG, PNG yoki WEBP formatdagi rasm qabul qilinadi."}
        )


class VerificationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerificationRequest
        fields = [
            "id", "method", "document_image", "selfie", "university_email",
            "status", "reject_reason", "created_at",
        ]
        read_only_fields = ["id", "status", "reject_reason", "created_at"]

    def validate(self, attrs):
        method = attrs.get("method")
        if method == VerificationMethod.DOCUMENT:
            _validate_image(attrs.get("document_image"), "document_image")
            _validate_image(attrs.get("selfie"), "selfie")
        if method == VerificationMethod.UNIVERSITY_EMAIL:
            email = (attrs.get("university_email") or "").strip().lower()
            if not email:
                raise serializers.ValidationError("Universitet emaili kiritilishi shart.")

            # Faqat ro'yxatdagi universitet domeni
            if not university_domain_allowed(email):
                raise serializers.ValidationError(
                    {"university_email": "Bu universitet domeni ro'yxatda yo'q."}
                )

            # Email hisobga bog'langan bo'lishi shart. Aks holda foydalanuvchi
            # o'z mailini "o'zining" deb e'lon qilib, tasdiqlanganlikka
            # erishardi (privilege escalation).
            request = self.context.get("request")
            if request and not request.user.is_anonymous:
                if not request.user.email:
                    raise serializers.ValidationError(
                        {
                            "university_email": "Avval profilga universitet emailingizni "
                            "qo'ying, keyin tasdiqlang."
                        }
                    )
                if request.user.email.strip().lower() != email:
                    raise serializers.ValidationError(
                        {"university_email": "Bu email sizning hisobingizga bog'lanmagan."}
                    )
        return attrs


class UniversityEmailCodeMixin:
    """Email hisobga bog'langan va universitet domenida ekanini tekshiradi."""

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if not email:
            raise serializers.ValidationError("Email kiritilishi shart.")
        if not university_domain_allowed(email):
            raise serializers.ValidationError("Bu universitet domeni ro'yxatda yo'q.")

        request = self.context.get("request")
        if request and not request.user.is_anonymous:
            if not request.user.email:
                raise serializers.ValidationError(
                    "Avval profilga universitet emailingizni qo'ying, keyin tasdiqlang."
                )
            if request.user.email.strip().lower() != email:
                raise serializers.ValidationError("Bu email sizning hisobingizga bog'lanmagan.")
        return email


class VerificationEmailCodeSerializer(
    UniversityEmailCodeMixin, serializers.Serializer
):
    """Universitet emailiga tasdiqlash kodi yuborish."""

    email = serializers.EmailField()


class VerifyEmailCodeSerializer(UniversityEmailCodeMixin, serializers.Serializer):
    """Emailga yuborilgan kodni tekshirish."""

    email = serializers.EmailField()
    code = serializers.CharField(min_length=4, max_length=8)


def university_domain_allowed(email: str) -> bool:
    """Email domeni universitet ro'yxatida borligini ANIQ tekshiradi.

    Avvalgi kodda `f"@{d}" in email` ishlatilgan bo'lib, `attacker@uzevil.com`
    kabi soxta domenlar ham o'tib ketardi. Endi domen '@' dan keyingi qism
    sifatida ajratib olinadi va ro'yxat bilan to'liq solishtiriladi.
    """
    if email.count("@") != 1:
        return False
    domain = email.rsplit("@", 1)[-1].strip().lower()
    allowed = {d.strip().lower().lstrip("@").lstrip(".") for d in settings.UNIVERSITY_EMAIL_DOMAINS}
    return domain in allowed