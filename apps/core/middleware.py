"""Tarjima bilan ishlovchi Django middleware va DRF integratsiyasi.

Muammo
-------
`LocaleMiddleware` tilni **cookie**, URL va `Accept-Language` dan o'qiydi.
Lekin DRF API so'rovlari uchun ikki holat bo'ladi:

1. Frontend `fetch()` bilan so'rov yuboradi — brauzer cookie'ni har doim
   yuboradi, shuning uchun `LocaleMiddleware` ishlaydi.
2. Hakatonalar (supabase/telegram bot, Postman, boshqa server) so'rovi —
   cookie yo'q. Ular `Accept-Language` yoki `?lang=ru` ishlatadi.

`LocaleMiddleware` `?lang=` parametrini **e'tibga olmaydi** (u faqat
`LANGUAGE_CODE`, cookie va sarlavhani qayta shakllantiradi). Shu sababli
API'da `?lang=` ishlashi uchun qo'shimcha middleware kerak.

Yechim
------
`ApiLocaleMiddleware` quyidagilarni ketma-ket tekshiradi:

    1. `?lang=` (URL parametri)     — eng aniq
    2. `X-StuGo-Language` sarlavhasi — frontend JS dan atayin yuboradi
    3. `Accept-Language` sarlavhasi   — brauzer yoki bot
    4. cookie / `LANGUAGE_CODE`       — Django'ning standart logikasi

Til o'zgarganda javobda `Content-Language` sarlavhasi qaytariladi —
frontend shundan bilib oladi va interfeysni darhol yangilaydi.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import translation
from django.utils.translation import get_supported_language_variant


class ApiLocaleMiddleware:
    """`?lang=` va `X-StuGo-Language` sarlavhasini qo'llab-quvvatlaydi.

    `LocaleMiddleware` dan KEYIN turishi SHART — u tilni birinchi o'rnatadi,
    biz esa faqat aniq so'rov bo'yicha ustidan yozamiz.
    """

    HEADER = "HTTP_X_STUGO_LANGUAGE"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # `get_supported_language_variant` LANGUAGES formatini kutadi:
        # [(kod, nom), ...] — shuning uchun to'g'ridan-to'g'ri beramiz.
        supported = list(getattr(settings, "LANGUAGES", []))

        requested = (
            request.GET.get("lang")  # 1) ?lang=ru
            or request.META.get(self.HEADER)  # 2) X-StuGo-Language
            or self._from_header(request)  # 3) Accept-Language
        )

        if requested:
            code = None
            try:
                # "ru-RU" -> "ru" kabi variantni moslashtiradi
                code = get_supported_language_variant(requested, supported)
            except Exception:
                code = None
            if not code:
                # `get_supported_language_variant` nomlarni ham tekshiradi va
                # nom bilan kelgan so'rovni rad qilishi mumkin ("O'zbekcha").
                # Faqat kodlarni qiyoslaymiz.
                wanted = str(requested).strip().lower().replace("_", "-").split("-")[0]
                code = next((c for c, _ in supported if c.lower() == wanted), None)
            if code:
                translation.activate(code)
                # View'lar ham shu tilni ko'rishi uchun
                request.LANGUAGE_CODE = code

        response = self.get_response(request)
        response.setdefault("Content-Language", translation.get_language() or settings.LANGUAGE_CODE)
        return response

    @staticmethod
    def _from_header(request) -> str | None:
        """`Accept-Language: ru-RU,ru;q=0.9,en;q=0.8` dan birinchi tilni oladi."""
        raw = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        for part in raw.split(","):
            code = part.split(";")[0].strip()
            if code:
                return code
        return None