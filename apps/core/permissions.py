from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    """Faqat obyekt egasiga ruxsat beradi."""

    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id


class IsVerified(BasePermission):
    """Faqat verifikatsiyadan o'tgan foydalanuvchiga ruxsat."""

    message = "Bu amal uchun verifikatsiya talab qilinadi."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_verified)


class IsModerator(BasePermission):
    """Moderator yoki admin uchun."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_staff or u.role == "moderator"))
