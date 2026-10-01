"""Lokal demo e'lonnlarini yaratadi.

Ishga tushirish:

    python manage.py seed_demo_listings

Nima qiladi:
  * 3 ta tasdiqlangan demo foydalanuvchi yaratadi;
  * 5 ta e'lon yaratadi, har biriga 3 ta rasm va bir nechta jihoz bog'laydi;
  * rasmlarni `Pillow` bilan generatsiya qiladi (tashqi fayl kerak emas).

Nima uchun 3 ta foydalanuvchi: `Listing.save()` bitta egaga 3 ta faol e'londan
ko'pini avtomatik `moderation` holatiga o'tkazadi. Agar barcha e'lon bir
egaga tegishli bo'lsa, 4- va 5-e'lon ro'yxatda ko'rinmasdi.

Idempotent: mavjud e'lonlar o'zgartirilmaydi, faqat topilmasa yaratiladi.
"""

from __future__ import annotations

import io
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw

from apps.housing.models import Amenity, Listing, ListingImage

User = get_user_model()

DEMO_EMAILS = ["demo.alisher@tuit.uz", "demo.zarnigor@tuit.uz", "demo.bekzod@tuit.uz"]
DEMO_PHONES = ["+998901234567", "+998901234568", "+998901234569"]

PALETTE = [
    ((30, 58, 95), (56, 130, 246)),
    ((15, 66, 54), (34, 197, 94)),
    ((76, 29, 29), (248, 113, 113)),
    ((59, 33, 84), (168, 85, 247)),
    ((17, 63, 78), (34, 211, 238)),
]


def _placeholder_image(seed: int, size: tuple[int, int] = (1000, 700)) -> ContentFile:
    """Gradient fonli oddiy "uy" silueti — tashqi rasm fayli kerak qilmaydi."""
    top, bottom = PALETTE[seed % len(PALETTE)]
    w, h = size
    img = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        draw.line(
            [(0, y), (w, y)],
            fill=tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)),
        )
    draw.rectangle([w * 0.18, h * 0.52, w * 0.82, h * 0.86], outline="white", width=5)
    draw.polygon([(w * 0.14, h * 0.52), (w * 0.5, h * 0.26), (w * 0.86, h * 0.52)],
                 outline="white", width=5)
    draw.rectangle([w * 0.44, h * 0.66, w * 0.56, h * 0.86], outline="white", width=5)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return ContentFile(buf.getvalue(), name=f"demo-{seed}.jpg")


# `owner` — DEMO_EMAILS dagi indeks.
LISTINGS = [
    {
        "owner": 0,
        "title": "Chilonzor metro yaqinida toza xona",
        "description": (
            "Yangi ta'mirlangan xona. Metro 5 daqiqa piyoda masofada. "
            "Kvartira toza va yorug', yon qo'shnilar tinch."
        ),
        "type": Listing.Type.ROOM, "price": Decimal("650000"), "city": "Tashkent",
        "district": "Chilonzor", "rooms": 1, "area": 18, "floor": 3, "total_floors": 9,
        "lat": Decimal("41.337079"), "lng": Decimal("69.278322"),
        "amenities": ["Wi-Fi", "Konditsioner", "Muzlatgich", "Kitob javoni"],
    },
    {
        "owner": 1,
        "title": "Yunusobod markazida qulay kvartira",
        "description": "Butun kvartira — bitta yoki ikki talaba. Mebellarning hammasi mavjud.",
        "type": Listing.Type.WHOLE_APARTMENT, "price": Decimal("3200000"),
        "city": "Tashkent", "district": "Yunusobod", "rooms": 2, "area": 54,
        "floor": 7, "total_floors": 12,
        "lat": Decimal("41.326673"), "lng": Decimal("69.300317"),
        "amenities": ["Wi-Fi", "Konditsioner", "Kir yuvish mashinasi", "Televizor", "Lift",
                      "Avtoturargoh"],
    },
    {
        "owner": 2,
        "title": "Sergelida arzon joy (bedspace)",
        "description": "Yotoq joyi, umumiy oshxona va sanitariya. Talaba uchun arzon variant.",
        "type": Listing.Type.BEDSPACE, "price": Decimal("450000"),
        "city": "Tashkent", "district": "Sergeli", "rooms": 1, "area": 8, "floor": 2,
        "total_floors": 5,
        "lat": Decimal("41.314044"), "lng": Decimal("69.223281"),
        "amenities": ["Wi-Fi", "24/7 suv", "Gaz", "Isitgich"],
    },
    {
        "owner": 0,
        "title": "Yakkasaroyda internet tez, ofis uchun qulay",
        "description": "Optik internet 500 Mbps. Ish uchun ham, o'qish uchun ham qulay.",
        "type": Listing.Type.ROOM, "price": Decimal("780000"), "city": "Tashkent",
        "district": "Yakkasaroy", "rooms": 1, "area": 22, "floor": 4, "total_floors": 8,
        "lat": Decimal("41.345362"), "lng": Decimal("69.326561"),
        "amenities": ["Wi-Fi", "Ofis stoli", "Kitob javoni", "Kafedekinet komp yotagi"],
    },
    {
        "owner": 1,
        "title": "Samarkandda universitet yonida xona",
        "description": "Termiz universiteti filialiga 10 daqiqa. Yangi uy, yaxshi jamiyat.",
        "type": Listing.Type.ROOM, "price": Decimal("520000"), "city": "Samarkand",
        "district": "Registon", "rooms": 1, "area": 16, "floor": 1, "total_floors": 3,
        "lat": Decimal("39.627800"), "lng": Decimal("66.959700"),
        "amenities": ["Wi-Fi", "Balcon", "Xavfsizlik"],
    },
]

PROFILES = [
    {"full_name": "Alisher Karimov", "university": "TUIT", "faculty": "Informatika", "course": 3},
    {"full_name": "Zarnigor Aliyeva", "university": "UzSWLU", "faculty": "Filologiya", "course": 2},
    {"full_name": "Bekzod Nurmatov", "university": "INHA", "faculty": "Ekonomiya", "course": 4},
]


class Command(BaseCommand):
    help = "Lokal demo e'lonlarini yaratadi (takror ishga tushirsa xato bermaydi)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Avval yaratilgan demo e'lonlarini o'chirib, qaytadan yaratadi.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            titles = [d["title"] for d in LISTINGS]
            deleted, _ = Listing.objects.filter(title__in=titles).delete()
            self.stdout.write(self.style.WARNING(f"Eski demo e'lonlar o'chirildi: {deleted} qator"))

        existing = Listing.objects.filter(title__in=[d["title"] for d in LISTINGS]).count()
        if existing == len(LISTINGS):
            self.stdout.write(self.style.SUCCESS("Demo e'lonlar allaqachon bor — hech narsa qilinmadi."))
            return

        users = []
        for i, email in enumerate(DEMO_EMAILS):
            user, created = User.objects.get_or_create(
                phone=DEMO_PHONES[i],
                defaults={"email": email, "role": "student", "is_verified": True},
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            else:
                changed = []
                if not user.is_verified:
                    user.is_verified, _ = True, changed.append("is_verified")
                if not user.email:
                    user.email, _ = email, changed.append("email")
                if changed:
                    user.save(update_fields=changed)

            profile = user.profile
            for field, value in {"city": "Tashkent", **PROFILES[i]}.items():
                setattr(profile, field, value)
            profile.save()
            users.append(user)
            if created:
                self.stdout.write(f"Demo foydalanuvchi: {user.phone} ({email})")

        amenities = {a.name: a for a in Amenity.objects.all()}
        missing = sorted({n for d in LISTINGS for n in d["amenities"]} - set(amenities))
        if missing:
            raise CommandError(
                "Jihozlar jadvali bo'sh yoki to'liq emas. Avval `python manage.py migrate` "
                "ishga tushiring. Yo'q jihozlar: " + ", ".join(missing)
            )

        created_count = 0
        for i, data in enumerate(LISTINGS):
            if Listing.objects.filter(title=data["title"]).exists():
                continue
            payload = dict(data)
            amenity_names = payload.pop("amenities")
            owner = users[payload.pop("owner")]
            listing = Listing.objects.create(owner=owner, **payload)
            listing.amenities.set([amenities[n] for n in amenity_names])
            for order in range(Listing.MIN_IMAGES):
                ListingImage.objects.create(
                    listing=listing, image=_placeholder_image(i * 10 + order), order=order
                )
            created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {created_count} ta yangi e'lon, bazada jami "
            f"{Listing.objects.filter(status=Listing.Status.ACTIVE).count()} ta faol e'lon."
        ))
        self.stdout.write(f"  Rasm papkasi: {settings.MEDIA_ROOT}")
        self.stdout.write("  Kirish uchun demo telefonlar: " + ", ".join(DEMO_PHONES))
        self.stdout.write("  (OTP kod server logida chiqadi — DEBUG rejimida `debug_code` qaytariladi)")