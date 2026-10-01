from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


class NotificationListView(APIView):
    """GET /notifications/ — bildirishnomalar ro'yxati (pagination bilan)."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(responses=NotificationSerializer(many=True))
    def get(self, request):
        qs = Notification.objects.filter(user=request.user)

        # Bitta agregatsiyada ham umumiy, ham o'qilmagan soni —
        # avval `count()` uch marta alohida chaqirilardi.
        stats = qs.aggregate(total=Count("id"), unread=Count("id", filter=Q(is_read=False)))

        page = self.pagination_class()
        paginated = page.paginate_queryset(qs, request, view=self)
        data = NotificationSerializer(
            paginated if paginated is not None else qs, many=True
        ).data

        body = {"unread": stats["unread"], "results": data}
        if paginated is not None:
            response = page.get_paginated_response(data)
            response.data["unread"] = stats["unread"]
            return response
        return Response(body)


class NotificationReadView(APIView):
    """POST /notifications/{id}/read/ — o'qilgan deb belgilash."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=None)
    def post(self, request, pk):
        # `user=request.user` filtri IDOR'ni oldini oladi: boshqa
        # foydalanuvchining bildirishnomasini o'qilgan qilib belgilab
        # bo'lmaydi.
        updated = Notification.objects.filter(
            user=request.user, pk=pk, is_read=False
        ).update(is_read=True, read_at=timezone.now())

        if not updated:
            exists = Notification.objects.filter(user=request.user, pk=pk).exists()
            if not exists:
                return Response(
                    {"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND
                )
        return Response({"status": "read"})