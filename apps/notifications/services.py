from apps.notifications.models import Notification


def notify(user, ntype: str, payload: dict | None = None):
    """Foydalanuvchiga bildirishnoma yaratadi (va keyinchalik push jo'natadi)."""
    notif = Notification.objects.create(user=user, type=ntype, payload=payload or {})
    # TODO production: Firebase Cloud Messaging push
    print(f"[PUSH] user={user_id_of(user)} type={ntype} payload={payload or {}}")
    return notif


def user_id_of(user):
    return getattr(user, "id", None)
