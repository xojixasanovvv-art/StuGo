from django.http import JsonResponse
from django.utils import translation
from django.views.generic import TemplateView, View
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.i18n import all_catalogs, language_meta


class HomeView(TemplateView):
    """GET / — taqdimot sahifasi (frontend shu yerdan yuklanadi)."""

    template_name = "index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # JS uchun barcha tillarni bir marta beramiz: tilni brauzerda
        # serverga so'rov yubormasdan almashtirish mumkin bo'ladi.
        ctx["i18n_catalogs"] = all_catalogs()
        ctx["languages"] = language_meta()
        ctx["current_language"] = translation.get_language()
        return ctx


class SetLanguageView(View):
    """POST /i18n/setlang/ — tilni o'zgartiradi.

    Tanlangan til `stugo_lang` cookie'siga yoziladi (Django'ning
    `LANGUAGE_COOKIE_NAME` sozlamasi bo'yicha, 1 yil muddatga) va
    `response.set_cookie` orqali javobga qaytariladi.

    Savol: nima uchun Django'ning o'z `set_language` view'i emas?
    Javob: u `/` ga redirect qilinadi va `next` parametri talab qiladi —
    frontend esa sahifani qayta yuklamasdan, faqat `t()` orqali matnlarni
    yangilashni xohlaydi. Bu view JSON qaytaradi va frontend'ga qulay.
    """

    def post(self, request):
        from django.conf import settings

        code = (request.POST.get("lang") or "").strip()
        allowed = {c for c, _ in settings.LANGUAGES}

        if code not in allowed:
            return JsonResponse(
                {"detail": "Bu til qo'llab-quvvatlanmaydi.", "allowed": sorted(allowed)},
                status=400,
            )

        translation.activate(code)
        request.LANGUAGE_CODE = code

        response = JsonResponse(
            {"lang": code, "catalogs": all_catalogs(), "languages": language_meta()},
            json_dumps_params={"ensure_ascii": False},
        )
        # Cookie'ni qo'lda yozamiz — frontend sahifani qayta yuklamaydi,
        # lekin keyingi so'rovlarda ham tanlangan til saqlanishi kerak.
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            code,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            samesite="Lax",
        )
        response["Content-Language"] = code
        return response


class LanguagesView(APIView):
    """GET /api/v1/i18n/languages/ — mavjud tillar ro'yxati."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "current": translation.get_language(),
                "languages": language_meta(),
            }
        )


class HealthView(APIView):
    """GET /health/ — server holati."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({"status": "ok"})