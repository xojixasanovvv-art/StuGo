"""Frontend statik tekshiruvlari: tema, profil rasmi, Telegram bloki.

Bu testlar `templates/index.html` ni **oddiy matn** sifatida o'qib,
ishlatilayotgan id / klass / kalit / CSS o'zgaruvchilarining
mavjudligini tekshiradi. Brauzer kerak emas — shuning uchun tez va
ishonchli.

Nima tekshiriladi
-----------------
1. **Qora/oq rejim** — `[data-theme="dark"]` blok, quyosh/oy tugmasi,
   `localStorage` da saqlash, FOUC ga qarshi `<head>` skripti.
2. **"Kirish" tugmasi** — yozuvli, til tugmasidan OLDIN, 3 tilda.
3. **Profil rasmi** — markup, CSS, yuklash (`FormData`) va o'chirish.
4. **Telegram bloki** — markup, funksiyalar, endpointlar, i18n kalitlari.
5. **Telegram i18n kalitlari** — 3 tilda bir xil to'plam.
"""

import json
import re
from pathlib import Path

from django.test import TestCase

from apps.core import i18n

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "index.html"
LANGS = ("uz", "ru", "en")

# Telegram/avatar uchun ishlatiladigan i18n kalitlari. Ularning barchasi
# 3 tilda ham bo'lishi shart — aks holda bitta tilda o'zbekcha qoladi.
NEW_I18N_KEYS = (
    "profile.pickPhoto",
    "profile.removePhoto",
    "profile.photoHint",
    "profile.photoBadType",
    "profile.photoTooBig",
    "profile.photoSaved",
    "profile.photoRemoved",
    "profile.telegram",
    "profile.telegramHint",
    "profile.telegramConnect",
    "profile.telegramConnected",
    "profile.telegramWaiting",
    "profile.telegramOpen",
    "profile.telegramNotFound",
    "profile.telegramNotReady",
    "profile.telegramError",
    "profile.telegramUnlink",
    "profile.telegramUnlinked",
    "profile.telegramUnlinkConfirm",
    "profile.telegramBadCode",
    "profile.telegramTimeout",
)


class TemplateMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.html = TEMPLATE.read_text(encoding="utf-8")
        cls.css = cls.html[cls.html.find("<style>") + 7 : cls.html.find("</style>")]


class ThemeTests(TemplateMixin, TestCase):
    """Qora/oq rejim (tema) — CSS o'zgaruvchilari va tugma."""

    def test_dark_theme_block_exists(self):
        self.assertIn('[data-theme="dark"]', self.css)

    def test_root_defines_light_theme(self):
        """:root = oq rejim. `data-theme="light"` ham shu qiymatlarni oladi,
        shuning uchun `:root` blok bo'lishi shart."""
        self.assertRegex(self.css, r":root\s*\{[^}]*--bg:")

    def test_theme_variables_are_defined_in_both_blocks(self):
        """O'zgaruvchilar ikkala rejimda ham bo'lishi shart — aks holda
        qora rejimda element oq qoladi."""
        root = re.search(r":root\s*\{([^}]*)\}", self.css).group(1)
        dark = re.search(r'\[data-theme="dark"\]\s*\{([^}]*)\}', self.css).group(1)
        root_vars = set(re.findall(r"(--[a-z0-9-]+)\s*:", root))
        dark_vars = set(re.findall(r"(--[a-z0-9-]+)\s*:", dark))
        missing = dark_vars - root_vars
        self.assertEqual(
            missing,
            set(),
            f"faqat qora rejimda bor, oq rejimda yo'q: {sorted(missing)}",
        )

    def test_body_uses_theme_variables_not_hardcoded(self):
        """`body` foni `var(--bg)` bo'lishi shart — aks holda rejim
        almashtirilganda oq qoladi."""
        m = re.search(r"(^|\n)\s*body\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(m, "body qoidasi topilmadi")
        self.assertIn("var(--bg)", m.group(2))

    def test_theme_toggle_button_exists(self):
        self.assertIn('id="themeToggleBtn"', self.html)

    def test_theme_toggle_has_sun_and_moon_icons(self):
        m = re.search(
            r'id="themeToggleBtn".*?</button>', self.html, re.S
        )
        self.assertIsNotNone(m, "#themeToggleBtn tugmasi topilmadi")
        block = m.group(0)
        self.assertIn("fa-sun", block)
        self.assertIn("fa-moon", block)

    def test_theme_toggle_has_aria_pressed(self):
        """Ekran o'quvchilar uchun holat bildirilishi shart."""
        self.assertRegex(self.html, r'id="themeToggleBtn"[^>]*aria-pressed=')

    def test_antifouc_script_runs_before_body(self):
        """`localStorage` dan tema birinchi chizilishdan OLDIN
        o'qilishi kerak — aks holda oq sahifada bir zum qora chaqnash
        bo'ladi (FOUC)."""
        head = self.html[: self.html.find("</head>")]
        script = re.search(
            r'<script>(.*?)</script>', head, re.S
        )
        self.assertIsNotNone(script, "<head> ichida inline <script> yo'q")
        code = script.group(1)
        self.assertIn("localStorage", code)
        self.assertIn("stugo_theme", code)
        self.assertIn("data-theme", code)
        self.assertLess(
            head.index("<body"),
            len(head),
            "body <head> ichidan tashqarida bo'lishi kerak",
        )

    def test_theme_module_exists_and_toggles_attribute(self):
        self.assertIn("const Theme = (function", self.html)
        self.assertRegex(self.html, r"setAttribute\('data-theme'")

    def test_toggle_theme_is_globally_available(self):
        """`onclick="toggleTheme()"` ishlatiladi — funksiya `window` da
        bo'lishi shart (`const Theme` esa yo'q)."""
        self.assertRegex(self.html, r"function toggleTheme\(\)")

    def test_theme_init_runs_on_dom_ready(self):
        self.assertRegex(self.html, r"Theme\.init\(\)")

    def test_theme_uses_prefers_color_scheme_for_system(self):
        """`system` qiymati tanlangan bo'lsa brauzer sozlamasiga o'tishi
        kerak."""
        self.assertIn("prefers-color-scheme", self.html)

    def test_no_plus_minus_buttons(self):
        """Foydalanuvchi so'ragan: bitta quyosh/oy tugmasi, `+`/`-` yo'q."""
        theme_block = re.search(
            r'id="themeToggleBtn".*?</button>', self.html, re.S
        ).group(0)
        for icon in ("fa-plus", "fa-minus"):
            self.assertNotIn(icon, theme_block)


class AuthButtonTests(TemplateMixin, TestCase):
    """Yozuvli "Kirish" tugmasi va uning joylashuvi."""

    def _nav_actions(self) -> str:
        m = re.search(r'<div class="nav-actions"[^>]*>(.*?)\n\s*</div>', self.html, re.S)
        self.assertIsNotNone(m, ".nav-actions topilmadi")
        return m.group(1)

    def test_auth_text_span_is_written(self):
        """Tugma yozuvli bo'lishi shart — `data-i18n="nav.login"`.

        `id` va `data-i18n` atributlari qanday tartibda yozilganidan
        qat'i narsa — ikkalasini ham bitta `<span>` da topamiz.
        """
        m = re.search(r"<span[^>]*id=\"navAuthText\"[^>]*>", self.html)
        self.assertIsNotNone(m, "#navAuthText topilmadi")
        self.assertIn('data-i18n="nav.login"', m.group(0))

    def test_auth_text_is_not_hidden_by_css(self):
        """`.nav-actions .btn > span` yashirish qoidasi `#navAuthText` ni
        istisno qilishi kerak."""
        m = re.search(
            r"\.nav-actions \.btn > span[^{]*\{[^}]*display:\s*none", self.css
        )
        self.assertIsNotNone(m, "span yashirish qoidasi topilmadi")
        self.assertIn(":not(#navAuthText)", m.group(0))

    def test_auth_button_precedes_language_switch(self):
        """Foydalanuvchi so'ragan: «Kirish» til tugmasidan OLDIN."""
        block = self._nav_actions()
        i_auth = block.find('id="navAuthBtn"')
        i_lang = block.find('id="langSwitch"')
        self.assertNotEqual(i_auth, -1, "#navAuthBtn topilmadi")
        self.assertNotEqual(i_lang, -1, "#langSwitch topilmadi")
        self.assertLess(
            i_auth, i_lang, "'Kirish' til tugmasidan keyin turibdi"
        )

    def test_theme_button_sits_between_auth_and_language(self):
        """Tartib: ... Kirish -> tema -> til."""
        block = self._nav_actions()
        i_auth = block.find('id="navAuthBtn"')
        i_theme = block.find('id="themeToggleBtn"')
        i_lang = block.find('id="langSwitch"')
        self.assertLess(i_auth, i_theme)
        self.assertLess(i_theme, i_lang)

    def test_only_one_auth_button(self):
        self.assertEqual(self.html.count('id="navAuthBtn"'), 1)

    def test_login_label_is_translated_in_all_languages(self):
        for lang in LANGS:
            catalog = i18n.load(lang)
            self.assertIn("nav.login", catalog)
            self.assertTrue(catalog["nav.login"].strip(), f"{lang}: bo'sh matn")


class AvatarTests(TemplateMixin, TestCase):
    """Profil rasmi (avatar) — markup, CSS va JS."""

    def test_avatar_markup_exists(self):
        for el_id in ("avatarPreview", "avatarImg", "avatarIcon", "avatarInput"):
            self.assertIn(f'id="{el_id}"', self.html)

    def test_avatar_input_accepts_only_images(self):
        m = re.search(r'<input type="file" id="avatarInput"[^>]*>', self.html)
        self.assertIsNotNone(m)
        self.assertIn("accept=", m.group(0))
        self.assertIn("image/png", m.group(0))
        self.assertIn("image/jpeg", m.group(0))

    def test_avatar_input_is_hidden(self):
        """Fayl tanlagich yashirin — tugma orqali ochiladi."""
        self.assertRegex(self.css, r"#avatarInput\s*\{[^}]*display:\s*none")

    def test_avatar_css_is_round(self):
        self.assertRegex(self.css, r"\.avatar-preview\s*\{[^}]*border-radius:\s*50%")
        self.assertRegex(self.css, r"\.nav-avatar\s*\{[^}]*border-radius:\s*50%")

    def test_avatar_preview_functions_exist(self):
        for fn in (
            "function previewAvatar(",
            "function removeAvatar(",
            "function renderAvatar(",
            "function renderAvatarPreview(",
            "function avatarUrl(",
        ):
            self.assertIn(fn, self.html)

    def test_avatar_upload_uses_formdata(self):
        """Fayl JSON da yuborilmaydi — multipart (`FormData`) shart."""
        m = re.search(r"function saveProfile\(\)\s*\{(.*?)\n    \}", self.html, re.S)
        self.assertIsNotNone(m, "saveProfile() topilmadi")
        body = m.group(1)
        self.assertIn("new FormData()", body)
        self.assertIn("fd.append('avatar'", body)

    def test_avatar_removal_sends_json_null(self):
        """Multipart'da bo'sh satr DRF'da «empty file» xatosi beradi —
        o'chirish `avatar: null` orqali JSON'da yuborilishi shart."""
        m = re.search(r"function saveProfile\(\)\s*\{(.*?)\n    \}", self.html, re.S)
        self.assertIn("body.avatar = null", m.group(1))

    def test_object_url_is_revoked(self):
        """`URL.createObjectURL` qarzini to'ldirish shart — aks holda
        tanlangan har bir rasm sessiya davomida xotirada qoladi.

        Soni teng bo'lishi shart emas (tanlangan rasm bir necha marta
        ko'rsatilishi mumkin), lekin `createObjectURL` bitta joyda
        ishlatilishi va bir necha joyda `revokeObjectURL` borligi kerak:
        faylni almashtirish, o'chirish, saqlash, chiqish.
        """
        self.assertIn(
            "url: URL.createObjectURL(file)",
            self.html,
            "avatar uchun object URL yaratilmayapti",
        )
        revokes = re.findall(r"URL\.revokeObjectURL\(([^)]*)\)", self.html)
        avatar_releases = [r for r in revokes if "pendingAvatar" in r or "pending" in r]
        self.assertGreaterEqual(
            len(avatar_releases),
            3,
            f"avatar object URL faqat {len(avatar_releases)} joyda bo'shiriladi",
        )

    def test_avatar_has_size_limit(self):
        self.assertIn("AVATAR_MAX_BYTES", self.html)
        self.assertIn("AVATAR_MIME", self.html)

    def test_logout_clears_avatar(self):
        """Chiqishda rasm ham tozalanadi — aks holda kirish tugmasida
        eski foydalanuvchining surati qoladi."""
        m = re.search(r"function logout\(\)\s*\{(.*?)\n    \}", self.html, re.S)
        self.assertIn("renderAvatar()", m.group(1))

    def test_navbar_has_avatar_image(self):
        m = re.search(r'<button class="btn btn-outline" id="navAuthBtn".*?</button>', self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn('id="navAvatar"', m.group(0))


class TelegramBoxTests(TemplateMixin, TestCase):
    """Profil modalidagi Telegram bog'lanish bloki."""

    def test_markup_ids_exist(self):
        for el_id in (
            "tgBox",
            "tgIdleActions",
            "tgWaiting",
            "tgCode",
            "tgOpenLink",
            "tgLinkedBox",
            "tgBadge",
            "tgUsername",
            "tgHint",
        ):
            self.assertIn(f'id="{el_id}"', self.html, f"#{el_id} topilmadi")

    def test_link_button_is_telegram_branded(self):
        self.assertRegex(self.html, r"btn-telegram[^>]*>\s*<i class=\"fa-brands fa-telegram")

    def test_open_link_is_an_anchor_with_target_blank(self):
        m = re.search(r'<a class="btn btn-telegram" id="tgOpenLink"[^>]*>', self.html)
        self.assertIsNotNone(m)
        self.assertIn('target="_blank"', m.group(0))
        # `rel="noopener"` ochilgan oynaning `window.opener` ga kirishini
        # cheklaydi — `?start=KOD` oynasi xavfsiz bo'lishi uchun.
        self.assertIn("noopener", m.group(0))

    def test_functions_exist(self):
        for fn in (
            "function tgLinkTelegram(",
            "function tgCancelLink(",
            "function tgPollStatus(",
            "function tgStartPoll(",
            "function tgStopPoll(",
            "function tgUnlink(",
            "function renderTelegramBox(",
        ):
            self.assertIn(fn, self.html)

    def test_endpoints_are_called(self):
        for endpoint in (
            "/auth/telegram/link/",
            "/auth/telegram/status/",
            "/auth/telegram/unlink/",
        ):
            self.assertIn(endpoint, self.html)

    def test_status_poll_sends_code(self):
        """Holat tekshiruvi kod bilan chaqirilishi shart — aks holda
        boshqa foydalanuvchining kodi ham ko'rindi."""
        self.assertRegex(self.html, r"/auth/telegram/status/\?code=' \+ encodeURIComponent")

    def test_polling_is_stopped_on_modal_close(self):
        """Modal yopilsa tekshiruv to'xtashi shart — aks holda yashirin
        `setTimeout` serverga so'rov yuborib turadi."""
        m = re.search(r"function closeModal\(id\)\s*\{(.*?)\n    \}", self.html, re.S)
        self.assertIn("tgStopPoll()", m.group(1))

    def test_polling_has_attempt_limit(self):
        """Chegara bo'lmasa `setTimeout` zanjiri abadiy davom etadi."""
        self.assertIn("TG_POLL_MAX", self.html)
        self.assertIn("attempts >= TG_POLL_MAX", self.html)

    def test_503_is_reported_as_not_configured(self):
        """Token yo'q bo'lsa `503` keladi — foydalanuvchiga «bot topilmadi»
        deb ko'rsatish kerak, texnik xato emas."""
        self.assertIn("e.status === 503", self.html)

    def test_logout_resets_telegram_state(self):
        m = re.search(r"function logout\(\)\s*\{(.*?)\n    \}", self.html, re.S)
        self.assertIn("state.telegram", m.group(1))

    def test_state_has_telegram_field(self):
        self.assertRegex(self.html, r"telegram:\s*\{\s*code:\s*null")

    def test_box_is_initialised_when_profile_opens(self):
        m = re.search(r"function openProfileModal\(\)\s*\{(.*?)\n    \}", self.html, re.S)
        self.assertIn("renderTelegramBox()", m.group(1))

    def test_telegram_css_exists(self):
        self.assertRegex(self.css, r"\.tg-box\s*\{")
        self.assertRegex(self.css, r"\.tg-code\s*\{[^}]*letter-spacing")

    def test_ok_colors_exist_for_badge(self):
        """`.tg-badge` `--ok-soft` / `--ok-border` ishlatadi — ikkala
        rejimda ham ta'rif bo'lishi shart."""
        root = re.search(r":root\s*\{([^}]*)\}", self.css).group(1)
        dark = re.search(r'\[data-theme="dark"\]\s*\{([^}]*)\}', self.css).group(1)
        for var in ("--ok-soft:", "--ok-border:"):
            self.assertIn(var, root, f"{var} :root da yo'q")
            self.assertIn(var, dark, f"{var} qora rejimda yo'q")


class NewI18nKeysTests(TestCase):
    """Yangi kalitlar 3 tilda ham mavjud va bo'sh emas."""

    def setUp(self):
        i18n.clear_cache()
        self.catalogs = {lang: i18n.load(lang) for lang in LANGS}

    def tearDown(self):
        i18n.clear_cache()

    def test_all_keys_exist_in_every_language(self):
        for key in NEW_I18N_KEYS:
            for lang in LANGS:
                self.assertIn(key, self.catalogs[lang], f"{lang}: '{key}' yo'q")

    def test_no_key_is_blank(self):
        for key in NEW_I18N_KEYS:
            for lang in LANGS:
                self.assertTrue(
                    self.catalogs[lang][key].strip(),
                    f"{lang}: '{key}' bo'sh",
                )

    def test_translations_differ_between_languages(self):
        """Kalit mavjudligi emas, haqiqiy tarjima qilinganligi muhim —
        aks holda bitta tilda boshqasi qolib ketsa foydalanuvchi
        chalkashadi."""
        for key in NEW_I18N_KEYS:
            values = {self.catalogs[lang][key] for lang in LANGS}
            self.assertGreater(
                len(values), 1, f"'{key}' uchta tilda bir xil matn"
            )

    def test_photo_hint_mentions_size_limit(self):
        for lang in LANGS:
            self.assertIn("5", self.catalogs[lang]["profile.photoHint"])

    def test_catalogs_are_valid_json_files(self):
        base = TEMPLATE.parents[1] / "locale" / "frontend"
        for lang in LANGS:
            path = base / f"{lang}.json"
            self.assertTrue(path.exists(), f"{path} yo'q")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict)
            for key in NEW_I18N_KEYS:
                self.assertIn(key, data)
