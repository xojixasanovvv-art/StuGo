"""Match juftligi normalizatsiyasi.

Avvalgi kodda `unique_together = ("user_a", "user_b")` bor edi, lekin
juftlik yo'nalishi normallashmagan edi. Shuning uchun A->B va B->A
ikki xil qator yaratib, `MatchDecisionView` faqat bittasini yangilab,
bir juftlik `ACCEPTED` + `PENDING` holatida qolardi.

Bu migration:
1. `user_a > user_b` qatorlarni teskari yo'nalishga aylantiradi.
2. Takror qatorlarni birlashtiradi.
3. `user_a < user_b` check constraint va indekslar qo'shadi.
"""

from django.db import migrations, models


def normalize_matches(apps, schema_editor):
    Match = apps.get_model("roommates", "Match")
    for match in Match.objects.all().order_by("id"):
        if match.user_a_id and match.user_b_id and match.user_a_id > match.user_b_id:
            a, b = match.user_a_id, match.user_b_id
            match.user_a_id, match.user_b_id = b, a
            match.save(update_fields=["user_a", "user_b"])


def dedupe_matches(apps, schema_editor):
    Match = apps.get_model("roommates", "Match")
    seen = set()
    for match in Match.objects.all().order_by("-score", "-created_at"):
        key = (match.user_a_id, match.user_b_id)
        if key in seen:
            match.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [("roommates", "0002_initial")]

    operations = [
        migrations.RunPython(normalize_matches, migrations.RunPython.noop),
        migrations.RunPython(dedupe_matches, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="match",
            constraint=models.CheckConstraint(
                condition=models.Q(("user_a__lt", models.F("user_b"))),
                name="match_user_a_lt_user_b",
            ),
        ),
        migrations.AddIndex(
            model_name="match",
            index=models.Index(fields=["user_a", "status"], name="roommates_m_user_a_7a1b2c_idx"),
        ),
        migrations.AddIndex(
            model_name="match",
            index=models.Index(fields=["user_b", "status"], name="roommates_m_user_b_3d4e5f_idx"),
        ),
    ]