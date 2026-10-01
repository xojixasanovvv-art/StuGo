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

    def test_cookie_beats_accept_language_header(self):
        """Regression: brauzer `Accept-Language` ni DOIM yuboradi.

        Agar u cookie'dan ustun bo'lsa, foydalanuvchi saytda rus tilini
        tanlab keyin sahifani yangilasa, `Accept-Language: en` tanlangan
        tilni ustidan yozib ketar edi va sayt o'z tiliga qaytardi.
        """
        for cookie, header, expected in [
            ("ru", "en-US,en;q=0.9", "ru"),
            ("en", "ru-RU,ru;q=0.9", "en"),
            ("uz", "en-US,en;q=0.9", "uz"),
        ]:
            with self.subTest(cookie=cookie, header=header):
                self.client.cookies["stugo_lang"] = cookie
                res = self.client.get("/", HTTP_ACCEPT_LANGUAGE=header)
                self.assertEqual(res["Content-Language"], expected)
                self.assertContains(res, f'<html lang="{expected}"')

    def test_header_beats_cookie(self):
        """`X-StuGo-Language` — aniq so'rov, shuning uchun cookie'dan ustun."""
        self.client.cookies["stugo_lang"] = "uz"
        res = self.client.get(
            "/api/v1/i18n/languages/", HTTP_X_STUGO_LANGUAGE="en"
        )
        self.assertEqual(res.json()["current"], "en")

    def test_accept_language_used_when_no_cookie(self):
        """Cookie yo'q bo'lsa `Accept-Language` ishlashda davom etadi."""
        res = self.client.get(
            "/api/v1/i18n/languages/", HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9"
        )
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


class ThirdPartyGlobalTests(TestCase):
    """Frontend'ning `window` global'ari CDN kutubxonalarini bosmasligi kerak.

    Nimani tekshiramiz
    -----------------
    Klassik `<script>` ichidagi `function foo() {}` deklaratsiyasi `window.foo`
    ga tushadi. Agar shu nom CDN kutubxonasi bilan bir xil bo'lsa (masalan
    Leaflet'ning global `L` obyekti), kutubxona jimgina qoladi.

    Bu hodisa sintaktik xato bermaydi — `node --check` ham, Django testlari ham
    uni ko'rmaydi. Faqat haqiqiy brauzerda "xarita chiqmaydi" deb namoyon
    bo'ladi. Shu sababdan nomlarni statik tekshiramiz.
    """

    #: CDN kutubxonalari `window` ga tashlaydigan global'lar.
    RESERVED = {
        "L": "Leaflet (xarita)",
        "turf": "turf.js",
        "Chart": "Chart.js",
        "Swiper": "Swiper",
        "moment": "Moment.js",
        "alert": "window.alert (brauzer)",
        "confirm": "window.confirm (brauzer)",
        "prompt": "window.prompt (brauzer)",
        "open": "window.open (brauzer)",
        "close": "window.close (brauzer)",
        "print": "window.print (brauzer)",
        "focus": "window.focus (brauzer)",
        "blur": "window.blur (brauzer)",
        "stop": "window.stop (brauzer)",
        "find": "window.find (brauzer)",
        "length": "window.length",
        "name": "window.name",
        "status": "window.status",
        "top": "window.top",
        "self": "window.self",
        "parent": "window.parent",
        "frames": "window.frames",
        "event": "window.event (eski IE)",
    }

    @classmethod
    def setUpTestData(cls):
        cls.raw = Client().get("/").content.decode()

    def _top_level_declarations(self):
        """Ikkinchi `<script>` blokidagi top-level `function` nomlari.

        Renderlangan sahifada funksiyalar 4 bo'shliq bilan indent qilingan
        (`    function foo()`) — bu ular klassik skriptning eng yuqori
        darajasida ekanini ko'rsatadi. Ichki funksiyalar 8+ bo'shliq oladi.
        """
        import re

        blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", self.raw, re.S)
        names = set()
        for block in blocks:
            if '"stugo-i18n-catalogs"' in block[:200]:
                continue  # JSON katalog bloki
            names.update(re.findall(r"^ {4}(?:async )?function ([A-Za-z_$][\w$]*)", block, re.M))
        return names

    def test_no_top_level_function_shadows_a_library_global(self):
        declared = self._top_level_declarations()
        self.assertGreater(len(declared), 30, "funksiya deklaratsiyalari topilmadi")

        clashes = sorted(declared & set(self.RESERVED))
        self.assertEqual(
            clashes,
            [],
            "Quyidagi funksiyalar CDN kutubxonasining global'ini "
            "almashtiradi: " + ", ".join(f"{n} ({self.RESERVED[n]})" for n in clashes),
        )

    def test_leaflet_namespace_is_not_redeclared(self):
        """Aynan `L` — Leaflet. Buni alohida tekshiramiz, chunki bu xarita.

        Belgilar: `function L(` yoki `const L =` / `let L =` / `var L =`.
        `L.map(...)` kabi *chaqiruv* xalq bo'lib qolishi kerak.
        """
        import re

        bad = re.findall(r"(?:^|\n)\s*(?:function\s+L\s*\(|(?:const|let|var)\s+L\s*=)", self.raw)
        self.assertEqual(bad, [], "Leaflet'ning `L` global'ini qayta e'lon qilgan kod bor")

        # Leaflet chaqiruvlari saqlanib qolgani. `initMap()` global'ni
        # `window.L` dan oladi (shunda CDN yuklanmasa jim qoladi), qolgan
        # funksiyalar to'g'ridan-to'g'ri `window.L.` ishlatadi.
        for call in ("window.L", "leaflet.map(", "leaflet.tileLayer(", "leaflet.layerGroup(",
                     "window.L.marker("):
            self.assertIn(call, self.raw, f"Leaflet chaqiruvi yo'qoldi: {call}")

    def test_t_is_not_shadowed_inside_any_function(self):
        """Hech qanday funksiya ichida `t` ni qayta e'lon qilmaslik kerak.

        Nima uchun bu jiddiy: `t` — global tarjima funksiyasi
        (`t('nav.login')`). Klassik skriptda top-level `const t` global
        *leksik* binding bo'ladi, `window.t` ga tushmaydi. Endi biron funksiya
        ichida `var t` yozilsa, `var` hoisting tufayli **butun** funksiya
        doirasida `t` `undefined` bo'ladi — shu funksiyadan `t(...)` chaqirilgan
        har qayerda "t is not a function" xatosi chiqadi.

        Sintaksis xatosi emas, `node --check` ham, Django testlari ham ko'rmaydi.
        Faqat foydalanuvchi kirish oynasini ochganda namoyon bo'ladi.
        """
        import re

        blocks = [
            b
            for b in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", self.raw, re.S)
            if '"stugo-i18n-catalogs"' not in b[:200]
        ]
        self.assertTrue(blocks, "inline <script> bloklari topilmadi")
        js = "\n".join(blocks)

        offenders = []
        for m in re.finditer(r"(?:^|\n)([ \t]+)(?:var|let|const)\s+t\s*[=;,)]", js):
            indent = len(m.group(1).expandtabs(4))
            if indent == 4:
                continue  # top-level `const t = I18N.t;` — bu o'zi, muvaffaqiyatli
            line_no = js[: m.start()].count("\n") + 1
            source_line = js[js.rfind("\n", 0, m.start()) + 1 : js.find("\n", m.start())]
            offenders.append(f"qator {line_no}: {source_line.strip()[:90]}")

        # funksiya parametri sifatida ham yashirilishi mumkin
        for m in re.finditer(r"function\s+\w+\s*\([^)]*?\bt\b[^)]*?\)", js):
            line_no = js[: m.start()].count("\n") + 1
            offenders.append(f"qator {line_no}: parametrda `t` — {m.group(0)[:70]}")

        self.assertEqual(
            offenders, [], "Global `t()` funksiyasi yashirilgan joylar:\n  " + "\n  ".join(offenders)
        )

    def test_t_is_reachable_from_inline_onclick_handlers(self):
        """`t` global leksik binding bo'lishi kerak — `onclick` undan foydalanadi.

        `var t` yoki `window.t = ...` bo'lsa, HTML atributidagi
        `onclick="... t('kalit') ..."` `ReferenceError` beradi.
        """
        import re

        self.assertRegex(self.raw, r"const\s+t\s*=\s*I18N\.t", "top-level `const t = I18N.t` yo'q")
        # `window.t` ga yozilishi global leksik binding'ni buzadi
        self.assertNotRegex(
            self.raw, r"window\.t\s*=", "`window.t` ga tayinlash leksik binding'ni buzadi"
        )

    def test_leaflet_loads_from_cdn_before_our_script(self):
        """Leaflet `<script src>` bizning skriptimizdan OLDIN bo'lishi kerak.

        Aks holda `initMap()` `L` hali yuklanmagan holda ishlaydi.
        """
        leaflet_at = self.raw.find("unpkg.com/leaflet")
        self.assertGreater(leaflet_at, -1, "Leaflet CDN havolasi topilmadi")

        init_at = self.raw.find("function initMap")
        self.assertGreater(init_at, -1, "initMap topilmadi")
        self.assertLess(
            leaflet_at, init_at, "Leaflet CDN havolasi `initMap` dan keyin kelishi kerak emas"
        )


class StaleResponseTests(TestCase):
    """Ro'yxat so'rovlari ketma-ketligi — eski javob yangisini ustiga yozmasin.

    Nimani tekshiramiz
    -----------------
    Filtr o'zgarganda `loadListings()` xomoni ishga tushadi. Foydalanuvchi
    shahar filtrini o'zgartirib, darhol qidiruv maydoniga yozsa, **ikki**
    so'rov bir vaqtda havada bo'ladi. Server ularni har doim tartibda
    qaytarmaydi, shuning uchun sekin qaytgan eski javob tez qaytgan
    yangisini ustidan yozib yuboradi.

    Natijada ro'yxat filtrga mos kelmaydi: `?city=Tashkent` javobi
    `?search=Samarkand` o'rniga chiziladi (4 ta Toshkent e'loni, 0 ta
    Samarkand kutilganida). Bu sintaksis xatosi emas — hech qanday test
    uni ko'rmaydi, faqat foydalanuvchi "qidiruv ishlamiyapti" deydi.

    Yechim: har so'rov monoton raqam oladi; javobda `reqId` ni tekshirib,
    eski javoblar butunlay tashlab yuboriladi.
    """

    @classmethod
    def setUpTestData(cls):
        cls.raw = Client().get("/").content.decode()

    def _body(self, name):
        import re

        i = self.raw.find(f"function {name}")
        self.assertGreater(i, -1, f"{name} topilmadi")
        m = re.search(r"\n {4}(?:async )?function ", self.raw[i + 1 :])
        end = i + 1 + (m.start() if m else len(self.raw))
        return self.raw[i:end]

    def test_state_has_request_sequence_counter(self):
        self.assertRegex(
            self.raw,
            r"listingsReq\s*:\s*0",
            "`state.listingsReq` hisoblagichi yo'q — so'rovlar tartibsiz qaytadi",
        )

    def test_request_id_is_captured_before_the_request(self):
        """So'rov yuborilishidan OLDIN raqam olinishi shart."""
        body = self._body("loadListings")
        capture = body.find("++state.listingsReq")
        self.assertNotEqual(capture, -1, "`++state.listingsReq` yo'q")
        call = body.find("api(")
        self.assertNotEqual(call, -1, "api() chaqiruvi yo'q")
        self.assertLess(capture, call, "raqam `api()` dan keyin olinadi — javob tartibsiz qaytadi")

    def test_stale_success_response_is_discarded(self):
        """`.then()` da eski javob tekshirilishi shart."""
        import re

        body = self._body("loadListings")
        success = body[body.index(".then(") : body.index(".catch(")]
        self.assertRegex(
            success,
            r"if\s*\(\s*reqId\s*!==\s*state\.listingsReq\s*\)\s*return",
            "`.then()` eski javobni tekshirmaydi",
        )
        # Tekshiruv `state.listings` yozilishidan OLDIN bo'lishi shart
        guard = success.index("reqId !== state.listingsReq")
        assign = success.index("state.listings =")
        self.assertLess(guard, assign, "tekshiruv `state.listings` yozilishidan keyin")

    def test_stale_error_response_is_discarded(self):
        """`.catch()` ham tekshirishi shart — eski xato yangi ro'yxatni tozalamasin."""
        body = self._body("loadListings")
        err = body[body.index(".catch(") :]
        self.assertRegex(
            err,
            r"if\s*\(\s*reqId\s*!==\s*state\.listingsReq\s*\)\s*return",
            "`.catch()` eski javobni tekshirmaydi",
        )

    def test_every_listings_render_is_guarded(self):
        """`state.listings =` yozilishidan oldin tekshiruv bo'lishi shart."""
        import re

        body = self._body("loadListings")
        for m in re.finditer(r"state\.listings\s*=", body):
            head = body[: m.start()]
            last_guard = head.rfind("reqId !== state.listingsReq")
            self.assertNotEqual(
                last_guard,
                -1,
                "`state.listings` yozilmoqda, lekin oldida so'rov tekshiruvi yo'q "
                f"(qator ~{body[:m.start()].count(chr(10)) + 1})",
            )

    def test_counter_is_monotonic(self):
        """`++` (prefiks) bo'lishi shart — `state.listingsReq = n` emas."""
        body = self._body("loadListings")
        self.assertRegex(body, r"\+\+\s*state\.listingsReq")

    def test_search_box_uses_oninput_not_onkeyup(self):
        """Qidiruv maydoni `oninput` bilan bog'lanishi shart, `onkeyup` emas.

        Nima uchun: `onkeyup` faqat klaviatura bilan yozilganda ishlaydi.
        Sichqoncha bilan **paste**, `cut`, matnni drag qilish yoki inputning
        o'zidagi tozalash tugmasi — bularning hech biri `keyup` hosil
        qilmaydi, ya'ni qidiruv umuman ishlamaydi. `oninput` barcha
        kirish usullarini qamrab oladi (va `keyup` o'rnini bosadi).
        """
        import re

        tag = re.search(r"<input[^>]*\bid=\"searchInput\"[^>]*>", self.raw, re.S)
        self.assertIsNotNone(tag, "searchInput topilmadi")
        markup = tag.group(0)

        self.assertRegex(markup, r"\boninput\s*=", "searchInput `oninput` bilan bog'lanmagan")
        self.assertNotRegex(
            markup, r"\bonkeyup\s*=", "searchInput `onkeyup` bilan bog'langan — paste ishlameydi"
        )
        self.assertIn("debouncedLoad()", markup, "searchInput `debouncedLoad()` ni chaqirmaydi")

    def test_search_handler_is_debounced(self):
        """`debouncedLoad` haqiqatan debounce bilan o'ralgan bo'lishi shart."""
        import re

        m = re.search(r"var\s+debouncedLoad[^\n]*", self.raw)
        self.assertIsNotNone(m, "debouncedLoad topilmadi")
        body = m.group(0)
        self.assertIn("loadListings()", body, "debouncedLoad `loadListings()` ni chaqirmaydi")

        # Debounce muddati — `debounce(fn, <ms>)` ikkinchi argumenti.
        ms = re.search(r",\s*(\d+)\s*\)\s*;\s*$", body)
        self.assertIsNotNone(ms, f"debounce muddati topilmadi: {body}")
        delay = int(ms.group(1))
        self.assertGreaterEqual(
            delay, 200, f"debounce {delay}ms — har bir tugma bosilishida so'rov yuboriladi"
        )
        self.assertLessEqual(delay, 1000, f"debounce {delay}ms — qidiruv sekin hisoblanadi")


class MapWiringTests(TestCase):
    """Xarita markerlari e'lonlar yuklanganda chizilishi kerak.

    Bu sinov bir necha jim xatoni ushlaydi:

    * `renderMapMarkers()` faqat "kirishsiz" holatda chaqirilsa — ro'yxat
      to'ldiriladi, lekin xarita bo'sh qoladi;
    * `initMap()` `0x0` o'lchamdagi yashirin konteynerda ishga tushsa —
      plitkalar bir dona qoladi, markerlar ko'rinmaydi.

    Ikkalasi ham sintaksis xatosi emas — faqat foydalanuvchi ko'zida
    "xarita yo'q" deb namoyon bo'ladi.
    """

    @classmethod
    def setUpTestData(cls):
        cls.raw = Client().get("/").content.decode()

    def _body(self, name):
        import re

        i = self.raw.find(f"function {name}")
        self.assertGreater(i, -1, f"{name} topilmadi")
        # funksiya tanasi: keyingi top-level `    function ` gacha
        m = re.search(r"\n {4}(?:async )?function ", self.raw[i + 1 :])
        end = i + 1 + (m.start() if m else len(self.raw))
        return self.raw[i:end]

    def test_markers_rendered_after_listings_load(self):
        """`loadListings()` muvaffaqiyatli bo'lganda markerlar chizilishi shart."""
        import re

        body = self._body("loadListings")
        self.assertIn("renderMapMarkers(", body, "loadListings ichida renderMapMarkers yo'q")

        # Chaqiruv muvaffaqiyatli `.then(...)` ichida bo'lishi kerak,
        # `state.listings` to'ldirilgandan KEYIN.
        success = body.index(".then(")
        tail = body[success:]
        self.assertIn("renderMapMarkers(", tail, "renderMapMarkers .then() ichida emas")
        before = tail.index("renderMapMarkers(")
        assign = tail.find("state.listings =")
        self.assertLess(assign, before, "markerlar `state.listings` to'ldirilishidan OLDIN chizilmoqda")

    def test_invalidate_size_called_before_markers(self):
        """`invalidateSize()` markerlardan OLDIN — aks holda `fitBounds` noto'g'ri."""
        import re

        body = self._body("loadListings")
        success = body[body.index(".then(") :]
        inv = success.find("invalidateSize(")
        mk = success.find("renderMapMarkers(")
        self.assertNotEqual(inv, -1, "loadListings ichida invalidateSize() yo'q")
        self.assertLess(inv, mk, "invalidateSize() markerlardan keyin chaqirilmoqda")

    def test_markers_cleared_when_logged_out(self):
        """Chiqishda markerlar tozalanishi kerak (eski ma'lumot qolmasin)."""
        body = self._body("loadListings")
        logged_out = body.index("if (!state.user)")
        self.assertIn(
            "renderMapMarkers([])",
            body[logged_out : logged_out + 700],
            "kirishsiz holatda markerlar tozalanmaydi",
        )

    def test_map_resize_handled_on_section_switch(self):
        """Housing bo'limiga o'tganda xarita o'lchami yangilanadi.

        Boshlang'ich holatda `sec-housing` `display:none` — shuning uchun
        `initMap()` 0x0 konteynerda ishlaydi. `showSection('housing')` bu
        holatni tuzatishi shart.
        """
        import re

        body = self._body("showSection")
        self.assertIn("invalidateSize", body, "showSection xarita o'lchamini yangilamaydi")
        self.assertRegex(body, r"secName\s*===\s*'housing'")

    def test_telegram_button_shares_listing(self):
        """Har bir e'lon kartasida Telegram ulashish tugmasi bo'lishi shart.

        `.btn-telegram` (#0088cc) CSS'da belgilangan, lekin hech qayerda
        ishlatilmagan bo'lsa — foydalanuvchi uchun tegmali, ammo o'lik
        element qoladi. Haqiqiy havola `t.me/share/url` ga bo'lishi va
        `target="_blank"` + `rel="noopener noreferrer"` (tab-nabbing
        himoyasi) bilan ochilishi kerak.
        """
        import re

        body = self._body("buildListingCard")
        self.assertIn("btn-telegram", body, "kartada `.btn-telegram` tugmasi yo'q")

        m = re.search(r'<a class="btn btn-telegram"[^>]*>', body, re.S)
        self.assertIsNotNone(m, "Telegram tugmasi `<a>` elementi emas")
        tag = m.group(0)
        self.assertIn("https://t.me/share/url", tag, "noto'g'ri Telegram havolasi")
        self.assertIn('target="_blank"', tag, "telegram oynada ochilmayapti")
        self.assertIn(
            'rel="noopener noreferrer"', tag, "tab-nabbing himoyasi yo'q (`rel=noopener`)"
        )

    def test_telegram_url_and_text_are_encoded(self):
        """Sarlavha URL'ga `encodeURIComponent` bilan biriktirilishi shart."""
        body = self._body("buildListingCard")
        self.assertIn(
            "encodeURIComponent(item.title)",
            body,
            "Telegram matni encode qilinmagan — bo'shliq/& belgilar havola buzadi",
        )
        self.assertIn("encodeURIComponent(", body, "URL encode qilinmagan")

    def test_telegram_share_uses_translated_label(self):
        """Tugma matni qat'iy o'zbekcha emas — tarjima kaliti orqali."""
        body = self._body("buildListingCard")
        self.assertIn("t('housing.shareTelegram')", body, "Telegram matni tarjima qilinmagan")

    def test_share_labels_exist_in_all_catalogs(self):
        """Yangi kalit uch til katalogida ham bo'lishi shart."""
        i18n.clear_cache()
        for lang in LANGS:
            catalog = i18n.load(lang)
            for key in ("housing.shareTelegram", "housing.shareTelegramTooltip"):
                self.assertIn(key, catalog, f"{lang} katalogida {key} yo'q")
                self.assertTrue(catalog[key].strip(), f"{lang}/{key} bo'sh")

    def test_chat_list_and_thread_are_separate_containers(self):
        """Suhbatlar ro'yxati va xabarlajk bo'lishi kerak alohida konteynerda.

        Nima uchun: ilgari ikkalasi `#chatList` da edi. `sendMessage()`
        oxirida `loadConversations()` chaqiriladi, u esa `renderChat()` bilan
        ro'yxatni qayta chizadi — natijada foydalanuvchi **yozib yuborgan
        xabarini darhol ko'rmay qoladi**, chat ko'rinishi buziladi.
        """
        import re

        for cid in ("chatList", "chatThread", "chatThreadBody"):
            self.assertRegex(
                self.raw, rf'id="{cid}"', f"`#{cid}` konteyneri yo'q"
            )

    def test_messages_render_into_thread_body(self):
        """`appendMessage()` xabarlarni `#chatThreadBody` ga yozishi shart."""
        body = self._body("appendMessage")
        self.assertIn("$('chatThreadBody')", body, "xabarlar noto'g'ri konteynerga yozilmoqda")
        self.assertNotIn(
            "$('chatList')",
            body,
            "`appendMessage()` hali ham `#chatList` ga yozadi — xabar yo'qoladi",
        )

    def test_open_conversation_switches_to_thread_view(self):
        """`openConversation()` ro'yxatni yashirib, suhbatni ko'rsatishi shart."""
        body = self._body("openConversation")
        self.assertRegex(body, r"\$\('chatList'\)\.hidden\s*=\s*true")
        self.assertRegex(body, r"\$\('chatThread'\)\.hidden\s*=\s*false")
        self.assertIn("buildMessageRow(", body, "xabarlar chizilmayapti")

    def test_render_chat_keeps_open_thread_intact(self):
        """`renderChat()` ochiq suhbatni buzmasligi shart.

        Aks holda har bir yangi xabarda chat ko'rinishi o'z-o'zidan
        yopilib qoladi.
        """
        import re

        body = self._body("renderChat")
        guard = body.find("if (state.activeConv)")
        self.assertNotEqual(
            guard, -1, "renderChat() ochiq suhbatni tekshirmaydi — xabar ko'rinishi buziladi"
        )
        tail = body[guard:]
        self.assertIn(
            "return", tail[:400], "renderChat() ochiq suhbatda barqaror emas"
        )
        self.assertRegex(body, r"renderChat\(\)[\s\S]*?\$\('chatThread'\)\.hidden\s*=\s*true|"
                                r"\$\('chatThread'\)\.hidden\s*=\s*true")

    def test_placeholder_removed_on_first_message(self):
        """Birinchi xabar kelganda «Hali xabar yo'q» yozuvi tozalanishi shart."""
        body = self._body("appendMessage")
        self.assertIn(
            "empty-state",
            body,
            "bo'sh holat yozuvi birinchi xabardan keyin ham qoladi",
        )
        self.assertRegex(body, r"innerHTML\s*=\s*''")

    def test_close_conversation_restores_list(self):
        """`closeConversation()` ro'yxatga qaytarishi va yozishni yopishi shart."""
        body = self._body("closeConversation")
        self.assertIn("closeSocket()", body, "soket yopilmayapti — xabar oqadigan davom etadi")
        self.assertRegex(body, r"state\.activeConv\s*=\s*null")
        self.assertRegex(body, r"\$\('chatThread'\)\.hidden\s*=\s*true")
        self.assertRegex(body, r"\$\('chatList'\)\.hidden\s*=\s*false")
        self.assertRegex(body, r"chatInputRow'\)\.style\.display\s*=\s*'none'")
        # Ro'yxat qaytishda chizilishi shart: `renderChat()` ochiq suhbatda
        # `return` qiladi, shuning uchun o'zi yetarli emas.
        self.assertIn(
            "loadConversations()",
            body,
            "orqaga qaytganda suhbatlar ro'yxati bo'sh qoladi",
        )

    def test_back_button_exists_and_is_wired(self):
        """Orqaga tugmasi bo'lishi va `closeConversation()` ga ulangan bo'lishi shart."""
        import re

        m = re.search(
            r'<button[^>]*onclick="closeConversation\(\)"[^>]*>(.*?)</button>', self.raw, re.S
        )
        self.assertIsNotNone(m, "orqaga tugmasi yo'q")
        self.assertIn("data-i18n=\"chat.back\"", m.group(1), "tugma matni tarjima qilinmagan")

    def test_back_label_exists_in_all_catalogs(self):
        i18n.clear_cache()
        for lang in LANGS:
            catalog = i18n.load(lang)
            self.assertIn("chat.back", catalog, f"{lang} katalogida chat.back yo'q")
            self.assertTrue(catalog["chat.back"].strip())

    def test_logout_clears_thread_state(self):
        """Chiqishda suhbat holati tozalanishi shart (keyingi kirishga ta'sir qilmasin)."""
        body = self._body("logout")
        self.assertRegex(body, r"state\.activeConv\s*=\s*null")
        self.assertIn("chatThreadBody", body, "xabarlar paneli tozalanmayapti")

    def test_no_hardcoded_uz_in_js_strings(self):
        """JS da qat'iy o'zbekcha matn bo'lmasligi shart — hammasi `t()` orqali.

        Masalan `sendVerifyCode()` ichidagi `'Emailni kiriting'` rus va
        ingliz tillarida o'zbekcha ko'rinib turadi. Bu sintaksis xatosi
        emas va i18n testlari uni ko'rmaydi (faqat server-rendered
        `data-i18n` atributlarini tekshiradi).

        Qidiruv: `t('kalit')` yoki `tr3(...)` bilan emas, `textContent =
        '...'` / `textContent = "..."` shaklida berilgan qatorlar.
        """
        import re

        blocks = [
            b
            for b in re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", self.raw, re.S)
            if '"stugo-i18n-catalogs"' not in b[:200]
        ]
        self.assertTrue(blocks, "inline <script> bloklari topilmadi")
        js = "\n".join(blocks)

        # `textContent = '...'` — bunda matn **to'g'ridan-to'g'ri**
        # foydalanuvchiga ko'rsatiladi. `innerHTML` esa ko'pincha
        # `<div>`/`<span>` teglari yoki serverdan kelgan `t(...)`/`esc(...)`
        # qo'ng'iroqlaridan iborat, ularni bu qoida ushlab olmaydi.
        offenders = []
        for m in re.finditer(r"textContent\s*=\s*'([^'\n]+)'", js):
            value = m.group(1)
            # Faqat belgilar yoki inline CSS/HTML qoldig'i — tarjima emas
            if not re.search(r"[A-Za-zЀ-ӿ]{3}", value):
                continue
            if value.startswith("<") or "style=" in value or "<i class=" in value:
                continue
            line_no = js[: m.start()].count("\n") + 1
            source_line = js[js.rfind("\n", 0, m.start()) + 1 : js.find("\n", m.start())]
            offenders.append(f"qator {line_no}: {source_line.strip()[:90]}")

        self.assertEqual(
            offenders,
            [],
            "JS'da `textContent` ga tarjimasiz matn qo'yilgan "
            "(i18n kaliti `t(...)` ishlatilishi kerak):\n  " + "\n  ".join(offenders),
        )

    def test_verify_flow_uses_catalog_keys(self):
        """Tasdiqlash oqimidagi xabarlar `t()` orqali olinishi shart."""
        import re

        for name in ("sendVerifyCode", "confirmVerifyCode"):
            body = self._body(name)
            for m in re.finditer(
                r"verifyHint'\)\.textContent\s*=\s*'([^']+)'", body
            ):
                self.fail(
                    f"{name}(): '{m.group(1)}' qat'iy o'zbekcha — "
                    "i18n kaliti (`t(...)`) ishlatilishi kerak"
                )

    def test_verify_email_falls_back_to_profile(self):
        """`sendVerifyCode()` profil emailidan foydalanishi shart.

        Modal yopiq holatda `#vEmail` bo'sh bo'lishi mumkin (masalan
        `saveProfile()` dan keyin). Foydalanuvchi profilda allaqachon
        email kiritgan bo'lsa, uni qayta kiritish majburiy bo'lmasin.
        """
        body = self._body("sendVerifyCode")
        self.assertIn("state.user.email", body, "profil emailidan zaxira sifatida foydalanilmayapti")
        self.assertRegex(
            body, r"if\s*\(\s*!email\s*&&\s*state\.user", "email zaxirasi `!email` shartiga bog'lanmagan"
        )

    def test_verify_keys_exist_in_all_catalogs(self):
        i18n.clear_cache()
        keys = ("verify.needEmail", "verify.sending", "verify.codeSent",
                "verify.needCode", "verify.checking")
        for lang in LANGS:
            catalog = i18n.load(lang)
            for key in keys:
                self.assertIn(key, catalog, f"{lang} katalogida {key} yo'q")
                self.assertTrue(catalog[key].strip(), f"{lang}/{key} bo'sh")

    def test_placeholder_image_is_svg_data_uri(self):
        """Rasm yo'q e'lon uchun placeholder — tashqi so'rovsiz, `data:image/svg+xml`.

        Aks holda `onerror`/`alt` matni `esc()` bilan chiqishi kerak.
        """
        import re

        body = self._body("placeholderImg")
        self.assertIn("data:image/svg+xml", body, "placeholder SVG data URI emas")
        # Tashqi yuklama bo'lmasin. `xmlns="http://www.w3.org/2000/svg"` — bu
        # SVG nomlar maydoni, so'rov emas; shuning uchun `src=`/`href=`/`url()`
        # orqali qidiriladi.
        import re

        self.assertNotRegex(body, r"(?:src|href)\s*=\s*['\"]https?://", "placeholder tashqi URL ishlatmoqda")
        self.assertNotRegex(body, r"url\(\s*['\"]?https?://", "placeholder tashqi URL ishlatmoqda")
        # Matn foydalanuvchi/katalogdan keladi — escape qilinishi shart
        self.assertIn("esc(", body, "placeholder matni escape qilinmagan")


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


class NavbarResponsiveTests(TestCase):
    """Navbar til tugmasi hech qanday ekran kengligida yashirilmasin.

    Muammo tarixi
    --------------
    `.navbar` `flex-wrap: nowrap` (standart) va `.nav-tabs` da `overflow`
    yo'q edi. Bo'lim matnlari uzunlashganda (masalan rus tilida
    "Студенческий маркет") butun navbar kengayib, o'ng tomondagi til va
    kirish tugmalari ekran tashqarisiga surilib, bosib bo'lmas edi.

    Brauzerda o'lchangan holat: viewport 800px, navbar 785px, ammo
    ichidagi kontent 1674px — til tugmasi `x=1441` da, ya'ni ko'rinmas.

    Keyinroq aniqlan-di: `.navbar` `max-width: 1440px` (ichida 1392px), ammo
    to'liq nomlar RU 1880px | UZ 1631px | EN 1502px kerak — ya'ni **birorta
    tilda ham sig'maydi**. Shuning uchun tugma katta ekrandagi
    kompyuterlarda ham ko'rinmas edi. Yechim: (1) `.nav-tabs` ga
    `min-width: 0` + `overflow-x: auto` — qat'iy kafolat; (2) to'liq nomlar
    faqat 1600px+ ekranda, aks holda qisqa nomlar.
    """

    @classmethod
    def setUpTestData(cls):
        cls.html = Client().get("/").content.decode()

    def _media_block(self, query):
        """`@media (<query>) { ... }` ichidagi CSS blokini qaytaradi.

        `{}` juftligini sanab, ichki media query'lar ham to'g'ri
        kesilishini ta'minlaydi.
        """
        import re

        m = re.search(r"@media\s*\(" + re.escape(query) + r"\)\s*\{", self.html)
        if not m:
            return ""
        start = m.end() - 1
        depth = 0
        for i in range(start, len(self.html)):
            if self.html[i] == "{":
                depth += 1
            elif self.html[i] == "}":
                depth -= 1
                if depth == 0:
                    return self.html[start + 1 : i]
        return self.html[start + 1 :]

    # ------------------------------------------------------------------
    # QAT'IY KAFOLAT: bo'limlar hech qachon qo'shnisini surmasin
    # ------------------------------------------------------------------
    def test_nav_tabs_can_shrink_and_scroll(self):
        """`.nav-tabs` ga `min-width: 0` + `overflow-x: auto` shart.

        Bu — til tugmasi ko'rinmasligining **asosiy** sababini yo'q
        qiladigan qoida. Sukut bo'yicha `min-width: auto` bo'lgani uchun
        bo'limlar siqilmaydi, o'sib qo'shnisini (til + kirish tugmalarini)
        surib ekrandan tashqariga chiqaradi.
        """
        import re

        m = re.search(r"\.nav-tabs\s*\{([^}]*)\}", self.html)
        self.assertIsNotNone(m, ".nav-tabs qoidasi yo'q")
        decls = m.group(1)
        self.assertIn("min-width: 0", decls, "min-width: 0 yo'q — bo'limlar surib ketadi")
        self.assertIn("overflow-x: auto", decls, "overflow-x: auto yo'q")
        # Bu qoidalar MEDIA QUERY ichida bo'lsa, desktopda ishlamaydi
        self.assertIsNone(
            re.search(r"@media[^{]*\{\s*\.nav-tabs\s*\{[^}]*min-width:\s*0", self.html),
            "min-width: 0 faqat media query ichida — desktopda himoya yo'q",
        )

    def test_action_buttons_never_shrink(self):
        """`.nav-actions` va `.lang-switch` siqilmasin (`flex-shrink: 0`)."""
        import re

        m = re.search(r"\.nav-actions,\s*\.lang-switch\s*\{([^}]*)\}", self.html)
        self.assertIsNotNone(m, ".nav-actions, .lang-switch qoidasi yo'q")
        self.assertIn("flex-shrink: 0", m.group(1))

    def test_unread_badge_is_not_hidden(self):
        """Regression: `#chatUnreadBadge` ham `span` bo'lgani uchun yashirilmasin.

        Tugma matnlarini yashirish qoidasi badge'ni ham yashirib, o'qilmagan
        xabar soni ko'rinmay qolardi.
        """
        import re

        m = re.search(
            r"(\.nav-actions \.btn > span[^{]*)\{[^}]*display:\s*none",
            self.html,
        )
        self.assertIsNotNone(m, "tugma matnini yashirish qoidasi yo'q")
        self.assertIn("#chatUnreadBadge", m.group(1))
        self.assertIn("#navAuthName", m.group(1))

    def test_buttons_are_icon_only_at_every_width(self):
        """Tugma matnlari barcha ekranlarda yashirilgan bo'lishi kerak.

        To'liq matn bilan RU da navbar 1880px kerak bo'lardi, `.navbar`
        esa 1440px bilan cheklangan — shuning uchun matn doim yashiriladi.
        """
        import re

        self.assertRegex(
            self.html, r"\.nav-actions \.btn > span[^{]*\{[^}]*display:\s*none"
        )
        # Hech qanday media query ichida emas — hamma ekran uchun
        self.assertIsNone(
            re.search(
                r"@media[^{]*\{[^}]*\.nav-actions \.btn > span[^{]*\{[^}]*display:\s*none",
                self.html,
            ),
            "qoida media query ichida — katt ekranda tugmalar sig'maydi",
        )

    # ------------------------------------------------------------------
    # Ekran kengligi bo'yicha zaxira ("ladder")
    # ------------------------------------------------------------------
    def test_two_row_mode_exists_and_wraps(self):
        """Tor ekranda navbar ikki qatorga bo'linishi kerak."""
        block = self._media_block("max-width: 1180px")
        self.assertTrue(block, "@media (max-width: 1180px) topilmadi")
        self.assertRegex(block, r"\.navbar\s*\{[^}]*flex-wrap:\s*wrap")
        self.assertRegex(block, r"\.nav-tabs\s*\{[^}]*order:\s*2")
        self.assertRegex(block, r"\.nav-tabs\s*\{[^}]*width:\s*100%")
        self.assertRegex(block, r"\.nav-actions\s*\{[^}]*order:\s*1")

    def test_all_breakpoint_tiers_exist(self):
        """Barcha zaxira pog'onalari (`ladder`) mavjud bo'lishi kerak.

        Har bir pog'ona oldingisidan torroq bo'lishi shart — aks holda
        oralig'da (masalan 500px) hech qanday qoida ishlamaydi.
        """
        import re

        found = sorted(int(w) for w in re.findall(r"@media\s*\(max-width:\s*(\d+)px\)", self.html))
        for tier in (1180, 480, 360):
            self.assertIn(tier, found, f"@media (max-width: {tier}px) topilmadi")
        self.assertEqual(found, sorted(set(found)), "bir xil breakpoint bir necha marta")

    def test_full_labels_only_on_wide_screens(self):
        """To'liq nomlar faqat keng ekranda — aks holda sig'maydi.

        To'liq nomlar RU 1880px kerak. `.navbar` esa `max-width: 1440px`
        bilan cheklangan, ya'ni 1600px dan kichik ekranda ular sig'maydi
        va oxirgi bo'lim yashirin qoladi.
        """
        import re

        m = re.search(r"@media\s*\(min-width:\s*(\d+)px\)\s*\{", self.html)
        self.assertIsNotNone(m, "@media (min-width: ...) topilmadi")
        self.assertGreaterEqual(
            int(m.group(1)),
            1600,
            "to'liq nomlar 1600px dan kichik ekranda ko'rinadi va sig'maydi",
        )
        # Sukut holat — qisqa nomlar
        self.assertRegex(self.html, r"\.nav-tabs \.nav-full\s*\{\s*display:\s*none")
        self.assertRegex(self.html, r"\.nav-tabs \.nav-short\s*\{\s*display:\s*inline")

    def test_phone_tier_shows_two_letter_code(self):
        """Telefon ekranida til nomi o'rniga 2 harfli kod ko'rinadi."""
        import re

        block = self._media_block("max-width: 480px")
        self.assertTrue(block, "@media (max-width: 480px) topilmadi")
        self.assertRegex(block, r"#langCurrentLabel\s*\{\s*display:\s*none")
        self.assertRegex(block, r"#langCurrentCode\s*\{\s*display:\s*inline")
        # Sukut holatda kod yashirin
        base = re.search(r"#langCurrentCode\s*\{([^}]*)\}", self.html)
        self.assertIn("display: none", base.group(1))

    def test_tiny_phone_tier_tightens_spacing(self):
        """320px da 6px yetishmay qolardi — <=360px da oraliq qisqartiriladi."""
        block = self._media_block("max-width: 360px")
        self.assertTrue(block, "@media (max-width: 360px) topilmadi")
        self.assertRegex(block, r"\.nav-actions\s*\{[^}]*gap:\s*\d+px")
        self.assertRegex(block, r"\.nav-actions \.btn\s*\{[^}]*padding:\s*\d+px")

    def test_lang_code_is_filled_by_js(self):
        """`#langCurrentCode` JS tomondan to'ldirilishi shart."""
        self.assertIn('id="langCurrentCode"', self.html)
        self.assertRegex(
            self.html,
            r"codeEl\.textContent\s*=\s*String\(current\)\.toUpperCase\(\)",
            "JS til kodi elementini to'ldirmayapti",
        )

    # ------------------------------------------------------------------
    # Bo'lim nomlari
    # ------------------------------------------------------------------
    def test_nav_has_full_and_short_labels(self):
        """Har bir bo'limda to'liq va qisqa nom bor bo'lishi kerak."""
        import re

        buttons = re.findall(r'<button class="nav-btn[^"]*" id="btn-\w+".*?</button>', self.html, re.S)
        self.assertEqual(len(buttons), 6, "6 ta bo'lim tugmasi kutilgan edi")
        for html in buttons:
            self.assertIn('class="nav-full"', html, f"to'liq nom yo'q: {html[:60]}")
            self.assertIn('class="nav-short"', html, f"qisqa nom yo'q: {html[:60]}")
            self.assertRegex(html, r'data-i18n="nav\.\w+"')
            self.assertRegex(html, r'data-i18n="nav\.\w+\.short"')

    def test_short_labels_are_translated(self):
        """`nav.*.short` kalitlari 3 tilda ham bor va qisqa bo'lishi kerak."""
        for lang in LANGS:
            catalog = i18n.load(lang)
            for full in ("home", "housing", "jobs", "skills", "market", "food"):
                key = f"nav.{full}.short"
                self.assertIn(key, catalog, f"{lang}: {key} yo'q")
                # Qisqa nom to'liq nomdan uzun bo'lmasin
                self.assertLessEqual(
                    len(catalog[key]),
                    len(catalog[f"nav.{full}"]),
                    f"{lang}: {key} to'liq nomdan uzun",
                )

    def test_short_labels_fit_in_single_row_tier(self):
        """Qisqa nomlar bilan bir qator 1181px da sig'ishi kerak.

        1180px dan kichikda ikki qatorga bo'linadi, shuning uchun 1181px —
        bir qatorli rejimning eng tor nuqtasi. U yerda ham oxirgi bo'lim
        ko'rinmasa, foydalanuvchi "Talaba bozori"ga kira olmaydi.

        Brauzerdagi haqiqiy o'lchov: RU 1053px | UZ 1077px | EN 1017px.
        Bu test esa eng uzun tarjimani (RU) ishlatib, po'lat chegarasini
        tekshiradi — 1133px (1181px - 2*24px padding).
        """
        ru = i18n.load("ru")  # eng uzun tarjima
        # logo(48) + 6 ikonka(14) + 6 gap(8) + 5 gap(6) + 6*2*14 padding
        fixed = 48 + 6 * 14 + 6 * 8 + 5 * 6 + 6 * 2 * 14
        total = fixed + sum(
            len(ru[f"nav.{n}.short"])
            for n in ("home", "housing", "jobs", "skills", "market", "food")
        )
        self.assertLessEqual(
            total,
            1133,
            f"qisqa nomlar 1181px da sig'maydi (~{total}px kerak)",
        )

    # ------------------------------------------------------------------
    # Vizual nozikliklar
    # ------------------------------------------------------------------
    def test_active_tab_shadow_is_not_clipped(self):
        """`.nav-btn.active` da `box-shadow` bor — uni kesib qo'yma.

        `.nav-tabs` da `overflow-x: auto` shadow'ni kesadi. `padding-bottom`
        shuncha bo'lishi kerakki soya (4px offset + 14px blur) to'liq
        ko'rinsin, va manfiy margin bilan vizual balandlik tiklansin.
        """
        import re

        m = re.search(r"\.nav-btn\.active\s*\{[^}]*box-shadow:\s*([^;]+);", self.html)
        self.assertIsNotNone(m, ".nav-btn.active da box-shadow yo'q")
        nums = re.findall(r"(\d+)px", m.group(1))
        self.assertGreaterEqual(len(nums), 2, f"shadow parse qilinmadi: {m.group(1)}")
        offset, blur = int(nums[0]), int(nums[1])
        needed = blur + offset

        base = re.search(r"\.nav-tabs\s*\{([^}]*)\}", self.html).group(1)
        pad = re.search(r"padding-bottom:\s*(\d+)px", base)
        self.assertIsNotNone(pad, ".nav-tabs da padding-bottom yo'q")
        self.assertGreaterEqual(
            int(pad.group(1)),
            needed,
            f"padding-bottom {pad.group(1)}px < shadow uchun kerak {needed}px",
        )
        # Manfiy margin balandlikni tiklaydi
        self.assertRegex(base, r"margin-bottom:\s*-\d+px")
