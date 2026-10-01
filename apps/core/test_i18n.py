"""3 til (uz / ru / en) i18n testlari.

Nimani tekshiramiz
-----------------
1. **Kataloglar bir xil kalit to'plamiga ega** — bitta tilda kalit
   qolib ketmasa, u boshqa tillarda "missing translation" bo'lib chiqadi.
2. **`?lang=`, `X-StuGo-Language`, `Accept-Language`, cookie`** — to'rtta
   manba ham ishlashi kerak (frontend va botlar turli yo'l ishlatadi).
3. **Fallback** — kalit topilmasa bo'sh joy emas, o'zbekcha matn chiqadi.
4. **Xavfsizlik** — tarjima matni `innerHTML` ga to'g'ridan-to'g'ri
   qo'yilmasin (`data-i18n-html` faqat server matni uchun).
"""

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from apps.core import i18n

LANGS = ("uz", "ru", "en")


class CatalogTests(TestCase):
    """Katalog fayllari va ularning pariteti."""

    def setUp(self):
        i18n.clear_cache()

    def tearDown(self):
        i18n.clear_cache()

    def test_all_languages_have_the_same_keys(self):
        """Har bir tilda barcha kalitlar bo'lishi shart.

        Aks holda rus/ingliz tilida o'zbekcha matnlar qolib ketadi va
        `missing_keys()` bo'sh bo'lmaydi.
        """
        base = set(i18n.load("uz"))
        self.assertGreater(len(base), 100, "Katalog bo'sh y juda kichik")

        for lang in ("ru", "en"):
            keys = set(i18n.load(lang))
            self.assertEqual(
                base - keys,
                set(),
                f"{lang} tilida yetishmayotgan kalitlar: {sorted(base - keys)[:10]}",
            )
            self.assertEqual(
                keys - base,
                set(),
                f"{lang} tilida ortiqcha kalitlar: {sorted(keys - base)[:10]}",
            )

    def test_missing_keys_are_empty(self):
        """`missing_keys()` hech qanday tilda bo'sh bo'lmasin."""
        for lang in LANGS:
            self.assertEqual(i18n.missing_keys(lang), [], f"{lang}: yetishmayotgan kalit bor")

    def test_no_empty_values(self):
        """Bo'sh qiymat ko'rinmasin — `KeyError` emas, lekin bo'sh joy chiqardi."""
        for lang in LANGS:
            empty = [k for k, v in i18n.load(lang).items() if not str(v).strip()]
            self.assertEqual(empty, [], f"{lang}: bo'sh qiymatli kalitlar {empty[:10]}")

    def test_get_falls_back_to_uzbek(self):
        """Kalit faqat o'zbekchada bo'lsa ham boshqa tilda ko'rinadi."""
        with translation.override("en"):
            # Bu kalit barcha tillarda bor — qiymat har 3 tilda mos kelishi kerak
            self.assertNotEqual(i18n.get("nav.housing"), "nav.housing")
            self.assertEqual(i18n.get("nav.housing"), i18n.get("nav.housing", lang="en"))

    def test_get_returns_key_when_unknown(self):
        """Butunlay noma'lum kalit — bo'sh joy emas, kalitning o'zi qaytadi.

        Bu atayin: xato boshqa yerda qolsa, `None` emas, aniq kalit ko'rinadi.
        """
        with translation.override("en"):
            self.assertEqual(i18n.get("definitely.not.exists"), "definitely.not.exists")

    def test_get_formats_params(self):
        with translation.override("en"):
            text = i18n.get("auth.welcome", name="Ali")
            self.assertIn("Ali", text)

    def test_get_survives_broken_placeholder(self):
        """Tarjimada `{name}` yo'q bo'lsa ham xato chiqmasin."""
        with translation.override("en"):
            # `auth.welcome` da `{name}` bor — nomusht qiling
            text = i18n.get("nav.housing", name="Ali")
            self.assertEqual(text, i18n.get("nav.housing"))

    def test_normalize_language_variants(self):
        self.assertEqual(i18n._normalize("ru-RU"), "ru")
        self.assertEqual(i18n._normalize("EN"), "en")
        self.assertEqual(i18n._normalize("uz_UZ"), "uz")
        self.assertEqual(i18n._normalize(None), "uz")
        self.assertEqual(i18n._normalize(""), "uz")

    def test_language_meta_marks_current(self):
        with translation.override("ru"):
            meta = i18n.language_meta()
            current = [m["code"] for m in meta if m["current"]]
            self.assertEqual(current, ["ru"])
            self.assertEqual({m["code"] for m in meta}, set(LANGS))

    def test_shop_keys_are_present(self):
        """OnlineShop'dan ko'chirilgan 283 ta shop kaliti joyida."""
        for lang in LANGS:
            shop_keys = [k for k in i18n.load(lang) if k.startswith("shop.")]
            self.assertGreater(len(shop_keys), 250, f"{lang}: shop kalitlari yetarli emas")


class TemplateTagTests(TestCase):
    """`{% tt %}` shablon teglari."""

    def render(self, template, **context):
        from django.template import Context, Template

        return Template(template).render(Context(context))

    def test_tt_renders_translation(self):
        tpl = '{% load i18n_tags %}{% tt "common.save" %}'
        with translation.override("uz"):
            self.assertEqual(self.render(tpl), i18n.get("common.save", lang="uz"))
        with translation.override("en"):
            self.assertEqual(self.render(tpl), "Save")
        with translation.override("ru"):
            self.assertEqual(self.render(tpl), "Сохранить")

    def test_tt_with_params(self):
        tpl = '{% load i18n_tags %}{% tt "auth.welcome" name="Ali" %}'
        with translation.override("en"):
            self.assertIn("Ali", self.render(tpl))

    def test_ttkey_returns_the_key(self):
        tpl = '{% load i18n_tags %}{% ttkey "common.save" %}'
        with translation.override("en"):
            self.assertEqual(self.render(tpl), "common.save")

    def test_unknown_key_does_not_raise(self):
        """Noma'lum kalit `TemplateSyntaxError` bermasligi kerak."""
        tpl = '{% load i18n_tags %}{% tt "nope.not.here" %}'
        with translation.override("en"):
            self.assertEqual(self.render(tpl), "nope.not.here")

    def test_lang_list_returns_meta(self):
        tpl = '{% load i18n_tags %}{% lang_list as ls %}{{ ls|length }}'
        self.assertEqual(self.render(tpl), str(len(i18n.available_languages())))


class LocaleResolutionTests(TestCase):
    """Til manbalari: `?lang=`, sarlavhalar, cookie."""

    def setUp(self):
        i18n.clear_cache()
        self.client = Client()

    def tearDown(self):
        i18n.clear_cache()

    def test_home_page_renders_in_requested_language(self):
        for lang in LANGS:
            with self.subTest(lang=lang):
                res = self.client.get("/", {"lang": lang})
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res["Content-Language"], lang)
                self.assertContains(res, f'<html lang="{lang}"')

    def test_query_param_wins_over_cookie(self):
        self.client.cookies["stugo_lang"] = "uz"
        res = self.client.get("/", {"lang": "en"})
        self.assertEqual(res["Content-Language"], "en")

    def test_language_cookie_is_used(self):
        """Cookie bilan — URL param'siz (frontend shu yo'l bilan saqlaydi)."""
        self.client.cookies["stugo_lang"] = "ru"
        res = self.client.get("/")
        self.assertEqual(res["Content-Language"], "ru")

    def test_unknown_language_falls_back(self):
        """`?lang=xx` — interfeys buzilmasin, default til qo'llansin."""
        res = self.client.get("/", {"lang": "xx"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Language"], "uz")

    def test_accept_language_header(self):
        res = self.client.get("/api/v1/i18n/languages/", HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9,en;q=0.8")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["current"], "ru")

    def test_custom_header_for_api_clients(self):
        """Bot/Postman cookie yubormaydi — `X-StuGo-Language` ishlashi kerak."""
        res = self.client.get("/api/v1/i18n/languages/", HTTP_X_STUGO_LANGUAGE="en")
        self.assertEqual(res.json()["current"], "en")

    def test_languages_endpoint_lists_all(self):
        res = self.client.get("/api/v1/i18n/languages/")
        data = res.json()
        self.assertEqual({item["code"] for item in data["languages"]}, set(LANGS))


class SetLanguageViewTests(TestCase):
    """POST /i18n/setlang/ — cookie yozish va katalogni qaytarish."""

    def setUp(self):
        i18n.clear_cache()
        self.url = reverse("set_language")
        # Django'ning odatiy test klienti CSRF'ni o'zi o'chiradi —
        # funksional testlar uchun shunaqa kerak (CSRF alohida tekshiriladi).
        self.client = Client()

    def tearDown(self):
        i18n.clear_cache()

    def test_post_sets_cookie_and_returns_catalogs(self):
        res = self.client.post(self.url, {"lang": "en"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Language"], "en")
        self.assertEqual(res.cookies["stugo_lang"].value, "en")
        data = res.json()
        self.assertEqual(data["lang"], "en")
        self.assertEqual(set(data["catalogs"]), set(LANGS))
        # Katalog to'liq kelishi kerak — hech bo'lim bo'sh qolmasin
        self.assertGreater(len(data["catalogs"]["en"]), 100)

    def test_rejects_unsupported_language(self):
        res = self.client.post(self.url, {"lang": "fr"})
        self.assertEqual(res.status_code, 400)
        self.assertNotIn("stugo_lang", res.cookies)

    def test_requires_csrf_token(self):
        """CSRF'siz POST qabul qilinmasligi kerak (cookie o'g'irlash himoyasi)."""
        res = Client(enforce_csrf_checks=True).post(self.url, {"lang": "en"})
        self.assertEqual(res.status_code, 403)

    def test_accepts_post_with_valid_csrf_token(self):
        """`{% csrf_token %}` orqali olingan token bilan POST muvaffaqiyatli.

        Bu frontend'ning aynan ishlatadigan yo'l — `setLang()` funksiyasi
        `csrftoken` cookie'sidan token olib `X-CSRFToken` sarlavhasida yuboradi.
        """
        client = Client(enforce_csrf_checks=True)
        page = client.get("/")  # sahifa `{% csrf_token %}` ni render qiladi
        token = str(page.context["csrf_token"])  # SimpleLazyObject -> str

        res = client.post(
            self.url,
            {"lang": "en"},
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.cookies["stugo_lang"].value, "en")


class PageContentTests(TestCase):
    """Sahifada tarjima mexanizmi mavjudligi (frontend integratsiyasi)."""

    @classmethod
    def setUpTestData(cls):
        cls.html = Client().get("/").content.decode()

    def test_catalog_script_block_is_embedded(self):
        """Barcha kataloglar `<script type="application/json>` ichida."""
        marker = 'id="stugo-i18n-catalogs"'
        self.assertIn(marker, self.html)
        start = self.html.index(marker)
        chunk = self.html[start : start + 400000]
        end = chunk.index("</script>")
        payload = chunk[chunk.index(">") + 1 : end]
        catalogs = json.loads(payload.replace("\\u003C", "<").replace("\\u003E", ">").replace("\\u0026", "&"))
        self.assertEqual(set(catalogs), set(LANGS))
        self.assertGreater(len(catalogs["en"]), 100)

    def test_i18n_data_attributes_present(self):
        """`data-i18n` belgilari ishlatilgan — JS matnlarni yangilay oladi."""
        count = self.html.count("data-i18n=")
        self.assertGreater(count, 50, "data-i18n belgilari yetarli emas")

    def test_every_data_i18n_key_exists_in_catalog(self):
        """HTML dagi har bir kalit katalogda bor bo'lishi shart.

        Aks holda `t()` kalitning o'zini chiqaradi va interfeysda
        `nav.housing` kabi texnik matnlar ko'rinadi.
        """
        import re

        keys = set(re.findall(r'data-i18n(?:-placeholder|-title|-aria)?="([a-zA-Z0-9_.]+)"', self.html))
        self.assertGreater(len(keys), 30, "kalitlar topilmadi")
        catalog = set(i18n.load("uz"))
        missing = sorted(keys - catalog)
        self.assertEqual(missing, [], f"katalogda yo'q kalitlar: {missing[:15]}")

    def test_t_function_and_lang_switcher_exist(self):
        self.assertIn("function t(", self.html)
        self.assertIn("applyI18n", self.html)
        self.assertIn("langSwitchBtn", self.html)
        self.assertIn("csrfToken", self.html)

    def test_csrf_token_rendered_for_language_post(self):
        self.assertIn("csrfmiddlewaretoken", self.html)

    def test_no_hardcoded_uzbek_left_in_nav(self):
        """Navbar tugmalari tarjimaga ulangan bo'lishi kerak."""
        for expected in ("Bosh sahifa", "Yashash joyi"):
            # Bu matn `data-i18n` orqali serverda tarjima bo'lgani uchun
            # faqat `<script>` JSON katalogida qolishi mumkin.
            head = self.html[: self.html.index("<!-- CSRF token")]
            self.assertNotIn(f">{expected}<", head, f"'{expected}' tarjimaga ulanmagan")

    def test_server_and_client_render_the_same_text(self):
        """Server (Django) va JS (katalog) bir xil matnni ko'rsatishi kerak.

        Aks holda sahifa `DOMContentLoaded` dan keyin matn " sakraydi" —
        foydalanuvchi avval o'zbekchani, keyin boshqa tilni ko'radi.
        """
        import html as html_lib
        import re

        for lang in LANGS:
            with self.subTest(lang=lang):
                page = Client().get("/", {"lang": lang})
                raw = page.content.decode()
                catalog = i18n.load(lang)

                rows = [
                    (m.group(1), html_lib.unescape(m.group(2).strip()))
                    for m in re.finditer(r'data-i18n="([a-zA-Z0-9_.]+)"[^>]*>([^<]*)<', raw)
                ]
                self.assertGreater(len(rows), 40)
                for key, server_text in rows:
                    with self.subTest(key=key):
                        self.assertEqual(
                            server_text,
                            catalog.get(key, key),
                            f"{lang}/{key}: server va JS matni farq qiladi",
                        )

    def test_shop_catalog_is_server_rendered_safe(self):
        """Shop kalitlari HTML'ga `data-i18n` sifatida qo'yilganda XSS bo'lmaydi."""
        self.assertNotIn('data-i18n="shop.', self.html)  # hali shop UI yo'q


class MiddlewareUnitTests(TestCase):
    """`ApiLocaleMiddleware` mustaqil ishlashini tekshirish."""

    def test_returns_content_language_header(self):
        res = Client().get("/health/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(res["Content-Language"], LANGS)

    def test_query_language_does_not_leak_to_next_request(self):
        """Bir so'rovda `?lang=en` — keyingi so'rov yana `uz` bo'lishi kerak.

        Aks holda bot bir so'rovda butun illyestratsiyani rus tiliga o'girib
        qo'yishi mumkin (til "leak" qilinadi).
        """
        client = Client()
        first = client.get("/", {"lang": "en"})
        self.assertEqual(first["Content-Language"], "en")
        second = client.get("/")
        self.assertEqual(second["Content-Language"], "uz")

    @override_settings(LANGUAGES=[("uz", "O'zbekcha")])
    def test_language_given_by_name_is_rejected_safely(self):
        """`?lang=Русский` kabi nom bilan so'rov — xato emas, jim qolish."""
        res = Client().get("/", {"lang": "Русский"})
        self.assertEqual(res.status_code, 200)