from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users import views

urlpatterns = [
    path("auth/send-otp/", views.SendOTPView.as_view(), name="send-otp"),
    path("auth/verify-otp/", views.VerifyOTPView.as_view(), name="verify-otp"),
    path("auth/login/", views.LoginPasswordView.as_view(), name="login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("profile/me/", views.MeView.as_view(), name="me"),
    path(
        "profile/",
        views.ProfileViewSet.as_view({"get": "retrieve", "patch": "update", "put": "update"}),
        name="profile-detail",
    ),
    path(
        "verification/requests/",
        views.VerificationRequestViewSet.as_view({"post": "create", "get": "list"}),
        name="verification",
    ),
    path(
        "verification/email/send-code/",
        views.SendVerificationEmailCodeView.as_view(),
        name="verification-email-send-code",
    ),
    path(
        "verification/email/confirm/",
        views.ConfirmVerificationEmailView.as_view(),
        name="verification-email-confirm",
    ),
    # --- Telegram ---
    path(
        "auth/telegram/link/",
        views.TelegramLinkStartView.as_view(),
        name="telegram-link",
    ),
    path(
        "auth/telegram/status/",
        views.TelegramLinkStatusView.as_view(),
        name="telegram-status",
    ),
    path(
        "auth/telegram/unlink/",
        views.TelegramUnlinkView.as_view(),
        name="telegram-unlink",
    ),
]