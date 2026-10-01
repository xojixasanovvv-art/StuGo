from django.db.models import Q

from apps.chat.models import Conversation, Message
from apps.notifications.services import notify
from apps.reports.models import Block


def participants_blocked(conv: Conversation, sender) -> bool:
    """Ishtirokchilardan biri bloklagan bo'lsa (ikki tomonlama tekshiruv) — xabar yuborilmaydi."""
    other_id = conv.partner_for(sender).id
    return Block.objects.filter(
        Q(blocker_id=sender.id, blocked_id=other_id)
        | Q(blocker_id=other_id, blocked_id=sender.id)
    ).exists()


def create_message(conv: Conversation, sender, text: str = "", image=None) -> Message | None:
    """Blok tekshiruvi bilan xabar yaratadi va qarshi tomonga push yuboradi."""
    if not text and not image:
        return None
    if participants_blocked(conv, sender):
        return None

    msg = Message.objects.create(conversation=conv, sender=sender, text=text, image=image)

    partner = conv.partner_for(sender)
    if partner:
        notify(
            partner,
            "new_message",
            {
                "conversation_id": conv.id,
                "message_id": msg.id,
                "preview": (text or "[rasm]")[:80],
                "message": "StuGo: yangi xabar",
            },
        )
    return msg
