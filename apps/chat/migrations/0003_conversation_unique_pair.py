"""Conversation uchun unikal juftlik.

1. `user_low` / `user_high` nullable sifatida qo'shiladi.
2. Mavjud suhbatlar to'ldiriladi, takror juftliklar birlashtiriladi.
3. Unikal constraint va indekslar qo'shiladi, maydonlar NOT NULL qilinadi.

Avvalgi kodda `Conversation.participants` M2M bo'lib, unikal juftlik
constraint'i yo'q edi — ikki parallel `POST /conversations/` so'rovi
bitta suhbat o'rniga ikkita suhbat yaratib qo'yardi.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def normalize_conversations(apps, schema_editor):
    Conversation = apps.get_model("chat", "Conversation")
    Message = apps.get_model("chat", "Message")
    seen = {}

    for conv in Conversation.objects.all().order_by("id"):
        ids = sorted(conv.participants.values_list("id", flat=True))
        if len(ids) < 2:
            conv.delete()
            continue

        key = (ids[0], ids[1])
        duplicate = seen.get(key)

        if duplicate is not None:
            for msg in Message.objects.filter(conversation_id=conv.id):
                msg.conversation_id = duplicate
                msg.save(update_fields=["conversation"])
            conv.delete()
            continue

        seen[key] = conv.id
        conv.user_low_id, conv.user_high_id = ids[0], ids[1]
        conv.save(update_fields=["user_low", "user_high"])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("chat", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="user_low",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="conversations_low",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Ishtirokchi (kichik id)",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="user_high",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="conversations_high",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Ishtirokchi (katta id)",
            ),
        ),
        migrations.RunPython(normalize_conversations, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="conversation",
            constraint=models.UniqueConstraint(
                fields=("user_low", "user_high"), name="conversation_unique_pair"
            ),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["user_low", "-updated_at"], name="chat_conve_user_low_a1b2c3_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["user_high", "-updated_at"], name="chat_conve_user_high_d4e5f6_idx"
            ),
        ),
        migrations.AlterField(
            model_name="conversation",
            name="user_low",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="conversations_low",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Ishtirokchi (kichik id)",
            ),
        ),
        migrations.AlterField(
            model_name="conversation",
            name="user_high",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="conversations_high",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Ishtirokchi (katta id)",
            ),
        ),
    ]