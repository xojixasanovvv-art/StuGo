from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsModerator
from apps.reports.models import Block, Report
from apps.reports.serializers import (
    BlockSerializer,
    ReportDecisionSerializer,
    ReportSerializer,
)


class ReportListCreateView(ListCreateAPIView):
    """POST /reports/ — shikoyat yuborish, GET /reports/mine/ — o'z shikoyatlarim."""

    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Report.objects.filter(reporter=self.request.user)

    def perform_create(self, serializer):
        serializer.save(reporter=self.request.user)


class BlockListCreateView(ListCreateAPIView):
    """GET/POST /users/blocks/ — bloklanganlar ro'yxati va bloklash."""

    serializer_class = BlockSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Block.objects.none()
        return Block.objects.filter(blocker=self.request.user)


class ReportModerationListView(ListAPIView):
    """GET /admin/reports/ — ochiq shikoyatlar (moderator)."""

    queryset = Report.objects.filter(status=Report.Status.OPEN)
    serializer_class = ReportSerializer
    permission_classes = [IsModerator]


class ReportDecisionView(APIView):
    """POST /admin/reports/{id}/decision/ — shikoyatga qaror (moderator)."""

    permission_classes = [IsModerator]

    @extend_schema(request=ReportDecisionSerializer, responses={200: ReportSerializer})
    def post(self, request, pk):
        serializer = ReportDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]
        report = Report.objects.filter(pk=pk).first()
        if report is None:
            return Response({"detail": "Topilmadi."}, status=404)

        report.status = Report.Status.RESOLVED if decision == "resolve" else Report.Status.DISMISSED
        report.reviewed_by = request.user
        report.reviewed_at = timezone.now()
        report.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        return Response(ReportSerializer(report).data)
