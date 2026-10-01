import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import Profile, VerificationMethod, VerificationRequest, VerificationStatus
from apps.users.serializers import (
    MeSerializer,
    ProfileSerializer,
    SendOTPSerializer,
    UserSerializer,
    VerificationEmailCodeSerializer,
    VerificationRequestSerializer,
    VerifyEmailCodeSerializer,
    VerifyOTPSerializer,
    university_domain_allowed,
)
from apps.users import telegram
from apps.users.services import (
    cooldown_seconds_left,
    normalize_phone,
    send_email_otp,
    send_otp,
    verify_email_otp,
    verify_otp,
)

logger = logging.getLogger(__name__)

User = get_user_model()


class OTPThrottleMixin:
    """`throttle_scope` DRF ga rate'ni qo'llash uchun kerak.

    `DEFAULT_THROTTLE_RATES` alone ishlmaydi — viewda `throttle_classes`
    yoki `throttle_scope` bo'lishi shart.
    """

    throttle_classes = [ScopedRateThrottle]


class SendOTPView(OTPThrottleMixin, APIView):
    """POST /api/v1/auth/send-otp/ — SMS OTP yuborish."""

    permission_classes = [AllowAny]
    throttle_scope = "otp_send"

    @extend_schema(
        request=SendOTPSerializer,
        responses={200: OpenApiResponse(description="Kod yuborildi")},
    )
    def post(self, request):
        ser = SendOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        phone = ser.validated_data["phone"]
        purpose = ser.validated_data["purpose"]
        code = None

        try:
            code = send_otp(phone, purpose)
        except ValueError as exc:
            # Faqat cooldown xabari foydalanuvchiga ko'rsatiladi.
            #
            # `code` va `params` — mashinali o'qiladigan maydonlar.
            # Frontend shular orqali xabarni o'z tilida ko'rsatadi
            # (`apiError()`), `detail` esa eski mijozlarga mos kelish uchun
            # o'zbekcha qoladi. Sabab: server har doim bitta tilni
            # qaytarmaydi — mijoz 3 tilni qo'llaydi.
            wait = cooldown_seconds_left(phone, purpose)
            return Response(
                {
                    "detail": str(exc),
                    "code": "otp.cooldown",
                    "params": {"seconds": wait} if wait else {},
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Javob HAR doim bir xil. Foydalanuvchi mavjudligi oshkor qilinmaydi.
        data = {"detail": "Kod SMS orqali yuborildi."}
        if settings.OTP_DEBUG_RETURN_CODE:
            # FAQAT lokal rivojlash. Production'da settings OTP_DEBUG_RETURN_CODE
            # False bo'ladi (u DEBUG bilan AND qilingan).
            data["debug_code"] = code
        return Response(data)


class VerifyOTPView(OTPThrottleMixin, APIView):
    """POST /api/v1/auth/verify-otp/ — kodni tekshirib JWT berish."""

    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"

    @extend_schema(
        request=VerifyOTPSerializer,
        responses={200: OpenApiResponse(description="JWT tokenlar")},
    )
    def post(self, request):
        ser = VerifyOTPSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        phone = ser.validated_data["phone"]
        purpose = ser.validated_data["purpose"]

        ok, err = verify_otp(phone, ser.validated_data["code"], purpose)
        if not ok:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(phone=phone).first()
        if user is None:
            # `purpose="register"` bo'lishi kerak — login maqsadida
            # ro'yxatdan o'tmagan raqamga token berilmaydi.
            if purpose != "register":
                return Response(
                    {"detail": "Bu raqam tizimda ro'yxatdan o'tmagan."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            with transaction.atomic():
                user = User.objects.create_user(
                    phone=phone,
                    email=ser.validated_data.get("email", ""),
                )

        if not user.is_active:
            return Response(
                {"detail": "Hisobingiz bloklangan. Administratorga murojaat qiling."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class LoginPasswordView(OTPThrottleMixin, APIView):
    """POST /api/v1/auth/login/ — telefon + parol bilan kirish."""

    permission_classes = [AllowAny]
    throttle_scope = "otp_verify"

    @extend_schema(
        request=TokenObtainPairSerializer,
        responses={200: OpenApiResponse(description="JWT tokenlar")},
    )
    def post(self, request):
        raw_phone = request.data.get("phone", "")
        password = request.data.get("password", "")

        # Noto'g'ri format — xabar berilmaydi, umumiy "xato" qaytariladi.
        try:
            phone = normalize_phone(raw_phone)
        except ValueError:
            phone = None

        user = User.objects.filter(phone=phone).first() if phone else None
        if user is None or not user.check_password(password) or not user.is_active:
            return Response(
                {"detail": "Telefon raqam yoki parol xato."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class MeView(APIView):
    """GET/PATCH /api/v1/profile/me/ — joriy foydalanuvchi.

    PATCH orqali `full_name` va `email` yangilanadi. `role`, `is_verified`
    va `is_active` read-only (`UserSerializer` da) — foydalanuvchi o'zini
    tasdiqlangan qilib ko'rsata olmaydi.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=MeSerializer, responses=MeSerializer)
    def patch(self, request):
        serializer = MeSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ProfileViewSet(
    viewsets.GenericViewSet,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.UpdateModelMixin,
):
    """GET/PATCH /api/v1/profile/ — profil ko'rish va tahrirlash."""

    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Profil `post_save` signali bilan foydalanuvchi yaratilishida
        # avtomatik ochiladi (apps/users/signals.py). Shuning uchun bu yerda
        # `get_or_create` emas, `get_or_404` — GET so'rovi bazaga yozmasligi kerak.
        from django.shortcuts import get_object_or_404

        return get_object_or_404(Profile, user=self.request.user)

    @extend_schema(responses=ProfileSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=ProfileSerializer, responses=ProfileSerializer)
    def update(self, request, *args, **kwargs):
        # PUT va PATCH bir xil ishlaydi: faqat berilgan maydonlar yangilanadi.
        ser = self.get_serializer(self.get_object(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class VerificationRequestViewSet(
    viewsets.GenericViewSet,
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.ListModelMixin,
):
    """POST/GET /api/v1/verification/requests/ — verifikatsiya so'rovlari."""

    serializer_class = VerificationRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return VerificationRequest.objects.none()
        return VerificationRequest.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Verifikatsiya so'rovi.

        Muhim: `POST` so'rovi `is_verified` BERMAYDI. Avvalgi kodda email
        domeni to'g'ri bo'lsa so'rov darhol tasdiqlanardi — foydalanuvchi
        esa o'z maili borligini hech qanday tasdiqlamagan edi
        (privilege escalation).

        Endi universitet emaili uchun alohida tasdiqlash kodi yuboriladi
        (`POST /api/v1/verification/email/send-code/`), foydalanuvchi uni
        o'z inbox'ida olib `confirm-email/` orqali tasdiqlaydi.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        req = serializer.save(user=self.request.user)
        return Response(self.get_serializer(req).data, status=201)


class SendVerificationEmailCodeView(APIView):
    """POST /api/v1/verification/email/send-code/ — emailga kod yuborish."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=VerificationEmailCodeSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = VerificationEmailCodeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        try:
            code = send_email_otp(email)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=429)

        data = {"detail": "Tasdiqlash kodi emailingizga yuborildi."}
        if settings.DEBUG and settings.OTP_DEBUG_RETURN_CODE:
            data["debug_code"] = code
        return Response(data)


class ConfirmVerificationEmailView(APIView):
    """POST /api/v1/verification/email/confirm/ — kodni tekshirish.

    Faqat shu yerda `is_verified=True` beriladi.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=VerifyEmailCodeSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = VerifyEmailCodeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        ok, error = verify_email_otp(email, serializer.validated_data["code"])
        if not ok:
            return Response({"detail": error}, status=400)

        # So'rovni tasdiqlashga o'tkazamiz (yo'q bo'lsa yaratamiz)
        req = (
            VerificationRequest.objects.filter(
                user=request.user, method=VerificationMethod.UNIVERSITY_EMAIL
            )
            .order_by("-created_at")
            .first()
        )
        if req is None:
            req = VerificationRequest.objects.create(
                user=request.user,
                method=VerificationMethod.UNIVERSITY_EMAIL,
                university_email=email,
            )

        req.status = VerificationStatus.APPROVED
        req.save(update_fields=["status", "updated_at"])
        request.user.is_verified = True
        request.user.save(update_fields=["is_verified"])
        logger.info("Verifikatsiya: foydalanuvchi %s email orqali tasdiqlandi", req.user_id)

        return Response({"detail": "Tasdiqlandi.", "is_verified": True})


# =============================================================================
# TELEGRAM — hisobni bot orqali ulash
# =============================================================================
# Oqim (batafsil izoh `apps/users/telegram.py` da):
#   1. `POST /auth/telegram/link/`  → server 8 xonali kod beradi
#   2. frontend `https://t.me/BOT?start=KOD` havolasini ochadi
#   3. `manage.py telegram_bot` long polling bilan xabarni oladi va
#      `Profile.telegram_id` ni shu foydalanuvchiga bog'laydi
#   4. frontend `GET /auth/telegram/status/?code=KOD` bilan natijani tekshiradi


class TelegramLinkStartView(APIView):
    """POST /api/v1/auth/telegram/link/ — bog'lanish kodi va havolasi."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        if not telegram.is_configured():
            return Response(
                {"detail": "Telegram bot sozlanmagan.", "code": "not_configured"},
                status=503,
            )

        username = telegram.bot_username()
        if not username:
            return Response(
                {"detail": "Telegram botga ulanib bo'lmadi.", "code": "bot_unavailable"},
                status=503,
            )

        # Profilni oldindan mavjudligini ta'minlaymiz (signal ham qiladi,
        # lekin hisob eskiroq bo'lsa signal ishga tushmasligi mumkin).
        profile, _ = Profile.objects.get_or_create(user=request.user)
        code = telegram.create_link_code(request.user.id)
        return Response(
            {
                "code": code,
                "bot_username": username,
                "bot_url": telegram.deep_link(username, code),
                "expires_in": int(getattr(settings, "TELEGRAM_LINK_TTL_SECONDS", 600)),
                "is_telegram_linked": profile.is_telegram_linked,
                "telegram_username": profile.telegram_username,
            }
        )


class TelegramLinkStatusView(APIView):
    """GET /api/v1/auth/telegram/status/?code=KOD — bog'lanish natijasi.

    `code` berilmasa, joriy foydalanuvchining umumiy Telegram holati
    qaytariladi (profil modalida ochilganda shu yetarli).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        payload = {
            "is_telegram_linked": profile.is_telegram_linked,
            "telegram_username": profile.telegram_username,
            "telegram_linked_at": profile.telegram_linked_at,
        }

        code = (request.query_params.get("code") or "").strip()
        if code:
            # Kod endi "ishlatilgan" bo'lsa (bot konsum qilgan), `consume_code`
            # None qaytaradi — shuning uchun avval egalikini tekshiramiz.
            owner = telegram.peek_code_owner(code)
            payload["pending"] = owner == request.user.id
            if owner is not None and owner != request.user.id:
                # Boshqa foydalanuvchining kodi — hech narsa aytmaymiz.
                payload["pending"] = False

        return Response(payload)


class TelegramUnlinkView(APIView):
    """POST /api/v1/auth/telegram/unlink/ — bog'lanishni uzish."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.telegram_id = None
        profile.telegram_username = ""
        profile.telegram_linked_at = None
        profile.save(
            update_fields=["telegram_id", "telegram_username", "telegram_linked_at"]
        )
        return Response({"detail": "Telegram bog'lanishi uzildi.", "is_telegram_linked": False})