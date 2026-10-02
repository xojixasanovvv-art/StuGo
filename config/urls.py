"""
URL configuration for StuGo project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import (
    HealthView,
    HomeView,
    LanguagesView,
    SetLanguageView,
)

admin.site.site_header = "StuGo Admin"
admin.site.site_title = "StuGo"
admin.site.index_title = "Boshqaruv paneli"


urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    # Boshqaruv paneli — `/admin-panel/`. Faqat `is_staff` foydalanuvchilar
    # kiradi (`StaffRequiredMiddleware` + `StaffRequiredMixin`).
    path("admin-panel/", include("apps.administration.urls")),
    # Django admin — `/django-admin/`. Bu TEKNIK panel (modellar ro'yxati,
    # DB va tuzilma ko'rish uchun). Oddiy kundalik boshqaruv uchun
    # `/admin-panel/` ni ishlating.
    path("django-admin/", admin.site.urls),
    path("health/", HealthView.as_view(), name="health"),
    # Tilni o'zgartirish (cookie + JSON javob)
    path("i18n/setlang/", SetLanguageView.as_view(), name="set_language"),
    # API v1
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/i18n/", include("apps.core.urls")),
    path("api/v1/", include("apps.housing.urls")),
    path("api/v1/", include("apps.shop.urls")),
    path("api/v1/", include("apps.roommates.urls")),
    path("api/v1/", include("apps.chat.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.reports.urls")),
    # API hujjat (Swagger)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
