"""TZ 4.6 — standart jihozlar ro'yxatini to'ldirish.

`Amenity` jadvali `migrate` dan keyin bo'sh qoladi. Frontenddagi "Jihozlar"
bloki shu jadvaldan o'qidi, shuning uchun yangi o'rnatilgan (yoki local)
baza bo'sh bo'lib qolsa e'lon shaklida birorta ham checkbox ko'rinmaydi.

Bu data migration `get_or_create` ishlatadi — takror ishga tushirilsa ham
ikkinchi marta hech narsani o'chirmaydi va o'zgartirmaydi.
"""

from django.db import migrations

# (nom, FontAwesome ikonkasi) — ikonka frontendda `fa-' + icon` sifatida
# ishlatiladi, shuning uchun `fa-` qisqasi bu yerda YOK.
AMENITIES = [
    ("Wi-Fi", "wifi"),
    ("Kir yuvish mashinasi", "washing-machine"),
    ("Kir yuvish qurilmasi", "tshirt"),
    ("Muzlatgich", "snowflake"),
    ("Konditsioner", "wind"),
    ("Isitgich", "fire"),
    ("Televizor", "tv"),
    ("Kafedekinet komp yotagi", "bed"),
    ("Ofis stoli", "table"),
    ("Kitob javoni", "bookshelf"),
    ("Balcon", "sun"),
    ("Avtoturargoh", "car"),
    ("Lift", "elevator"),
    ("Xavfsizlik", "shield-halved"),
    ("24/7 suv", "faucet-drip"),
    ("Gaz", "fire-burner"),
    ("Lift va domofon", "bell"),
]


def seed_amenities(apps, schema_editor):
    Amenity = apps.get_model("housing", "Amenity")
    for name, icon in AMENITIES:
        Amenity.objects.get_or_create(name=name, defaults={"icon": icon})


def unseed_amenities(apps, schema_editor):
    """Faqat shu migratsiya qo'shgan qatorlarni olib tashlaydi.

    Foydalanuvchi qo'shgan yoki boshqa migratsiya yaratgan qatorlar
    saqlanib qoladi.
    """
    Amenity = apps.get_model("housing", "Amenity")
    Amenity.objects.filter(name__in=[name for name, _ in AMENITIES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("housing", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(seed_amenities, unseed_amenities),
    ]