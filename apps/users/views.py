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
from apps.users.services import (
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
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

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