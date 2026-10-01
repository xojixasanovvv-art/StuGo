from django.db.models import Q, Prefetch
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.chat.models import Conversation, Message
from apps.chat.serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    MessageSerializer,
)
from apps.chat.services import create_message, participants_blocked
from apps.core.pagination import StandardResultsSetPagination
from apps.reports.models import Block


class ConversationListView(APIView):
    """GET /conversations/ — suhbatlar ro'yxati."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(responses=ConversationSerializer(many=True))
    def get(self, request):
        convs = (
            Conversation.objects.filter(participants=request.user)
            .select_related("user_low", "user_high")
            # N+1 oldini olish: oxirgi xabar va unread_count uchun
            .prefetch_related(
                Prefetch(
                    "messages",
                    queryset=Message.objects.select_related("sender"),
                    to_attr="messages_cache",
                )
            )
        )
        # Bloklash mavjud bo'lgan suhbatlar ro'yxatda ko'rinmasin.
        # Muhim: filtrni PAGINATION'dan KEYIN emas, undan OLDIN qilamiz —
        # aks holda `count` metadata noto'g'ri bo'lardi va bloklangan
        # qatorlar bo'sh sahifalarni to'ldirardi.
        blocked_ids = set(
            Block.objects.filter(blocker_id=request.user.id).values_list(
                "blocked_id", flat=True
            )
        ) | set(
            Block.objects.filter(blocked_id=request.user.id).values_list(
                "blocker_id", flat=True
            )
        )
        if blocked_ids:
            convs = convs.exclude(user_low_id__in=blocked_ids).exclude(
                user_high_id__in=blocked_ids
            )

        page = self.pagination_class()
        paginated = page.paginate_queryset(convs, request, view=self)
        rows = list(paginated if paginated is not None else convs)
        data = ConversationSerializer(rows, many=True, context={"request": request}).data

        if paginated is not None:
            return page.get_paginated_response(data)
        return Response(data)

    @extend_schema(request=ConversationCreateSerializer, responses=ConversationSerializer)
    def post(self, request):
        """POST /conversations/ — suhbat boshlash (mavjud bo'lsa shu qaytadi)."""
        ser = ConversationCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        other_id = ser.validated_data["user_id"]

        from django.contrib.auth import get_user_model

        other = get_user_model().objects.filter(id=other_id).first()
        conv, created = Conversation.get_or_create_pair(request.user, other)
        return Response(
            ConversationSerializer(conv, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MessageListView(APIView):
    """GET/POST /conversations/{id}/messages/."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "message_send"

    def get_throttles(self):
        # Throttle faqat yuborishga (POST) qo'llanadi; o'qish cheylanmasin.
        if self.request.method != "POST":
            return []
        return super().get_throttles()

    def _get_conv(self, request, pk):
        conv = (
            Conversation.objects.filter(
                Q(participants=request.user), pk=pk
            )
            .select_related("user_low", "user_high")
            .first()
        )
        if conv is None:
            return None
        # Bloklash ikki tomon uchun ham amal qiladi
        if participants_blocked(conv, request.user):
            return None
        return conv

    @extend_schema(responses=MessageSerializer(many=True))
    def get(self, request, pk):
        conv = self._get_conv(request, pk)
        if conv is None:
            return Response({"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        msgs = conv.messages.select_related("sender").order_by("created_at")

        # O'qilgan deb belgilash — faqat o'z xabarimni emas, qarshi tomonniki.
        # Eslatma: `read_at` bitta ustun bo'lgani uchun "meni o'qidi" holati
        # alohida saqlanmaydi. Frontend `sender` orqali ajratadi.
        conv.messages.filter(read_at__isnull=True).exclude(sender=request.user).update(
            read_at=timezone.now()
        )

        page = self.pagination_class()
        paginated = page.paginate_queryset(msgs, request, view=self)
        data = MessageSerializer(paginated if paginated is not None else msgs, many=True).data

        if paginated is not None:
            return page.get_paginated_response(data)
        return Response(data)

    @extend_schema(request=None, responses=MessageSerializer)
    def post(self, request, pk):
        conv = self._get_conv(request, pk)
        if conv is None:
            return Response({"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        text = (request.data.get("text") or "").strip()
        image = request.FILES.get("image")
        if not text and not image:
            return Response(
                {"detail": "Xabar bo'sh."}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(text) > Message._meta.get_field("text").max_length:
            return Response(
                {"detail": "Xabar juda uzun."}, status=status.HTTP_400_BAD_REQUEST
            )

        msg = create_message(conv, request.user, text=text, image=image)
        if msg is None:
            return Response(
                {"detail": "Xabar yuborilmadi (bloklangan bo'lishi mumkin)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = MessageSerializer(msg)
        return Response(ser.data, status=status.HTTP_201_CREATED)