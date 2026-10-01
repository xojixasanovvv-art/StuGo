from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsVerified
from apps.core.pagination import StandardResultsSetPagination
from apps.notifications.services import notify
from apps.roommates.models import Match, RoommateProfile
from apps.roommates.serializers import (
    MatchDecisionSerializer,
    MatchRequestSerializer,
    MatchSerializer,
    RoommateProfileSerializer,
)
from apps.roommates.services import compatibility_score

MIN_MATCH_SCORE = 30


class RoommateProfileView(APIView):
    """GET/PUT/PATCH /roommates/profile/ — o'z anketa."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(responses=RoommateProfileSerializer)
    def get(self, request):
        prof, _ = RoommateProfile.objects.get_or_create(user=request.user)
        return Response(RoommateProfileSerializer(prof).data)

    @extend_schema(request=RoommateProfileSerializer, responses=RoommateProfileSerializer)
    def put(self, request):
        return self._save(request, partial=False)

    @extend_schema(request=RoommateProfileSerializer, responses=RoommateProfileSerializer)
    def patch(self, request):
        return self._save(request, partial=True)

    def _save(self, request, partial):
        prof, _ = RoommateProfile.objects.get_or_create(user=request.user)
        ser = RoommateProfileSerializer(prof, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        ser.save(user=request.user)
        return Response(ser.data)


class MatchListView(APIView):
    """GET /roommates/matches/ — mos anketalar ro'yxati (score bo'yicha).

    DIQQAT: bu endpoint FAQAT O'QISH uchun. Avvalgi versiya har bir GET
    so'rovida bazaga `INSERT` qilardi (crawler/prefetch ham yozardi) —
    bu `n` ta profil uchun `n` ta yozuv tug'ilishiga olib kelardi.
    """

    permission_classes = [IsAuthenticated, IsVerified]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        responses=MatchSerializer(many=True),
        parameters=[
            OpenApiParameter("page", int, description="Sahifa raqami"),
            OpenApiParameter("search", str, description="Shahar bo'yicha qidiruv"),
        ],
    )
    def get(self, request):
        me_profile = getattr(request.user, "roommate_profile", None)
        if me_profile is None:
            return Response(
                {"detail": "Avval roommate anketani to'ldiring."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        others = RoommateProfile.objects.filter(is_active=True).exclude(
            user=request.user
        ).select_related("user")

        search = (request.query_params.get("search") or "").strip()
        if search:
            others = others.filter(city__icontains=search)

        # Avval saqlangan mosliklar bazasidan o'qiymiz (tez, N+1 yo'q).
        existing = {
            m.partner_for(request.user).id: m
            for m in Match.objects.filter(
                Q(user_a=request.user) | Q(user_b=request.user)
            ).select_related("user_a", "user_b")
        }

        rows = []
        for other in others:
            match = existing.get(other.user_id)
            # Saqlangan score ishlatiladi; yo'q bo'lsa hisoblanadi va
            # HECH NARSA yozilmaydi. Yozish `sync_matches` task'ida.
            score = match.score if match else compatibility_score(me_profile, other)
            if score < MIN_MATCH_SCORE:
                continue
            rows.append((score, other, match))

        rows.sort(key=lambda r: r[0], reverse=True)

        payload = [
            {
                "id": match.id if match else None,
                "partner": {"id": other.user.id, "is_verified": other.user.is_verified},
                "partner_profile": RoommateProfileSerializer(
                    other, context={"request": request}
                ).data,
                "score": score,
                "status": match.status if match else "pending",
                "created_at": match.created_at if match else None,
            }
            for score, other, match in rows
        ]

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(payload, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(page)
        return Response(payload)


class MatchRequestView(APIView):
    """POST /roommates/matches/request/ — moslik so'rovi yaratish.

    `GET /roommates/matches/` endi HECH NARSA yozmaydi (crawler/prefetch
    himoyasi), shuning uchun ro'yxatdagi `id: null` qatorlarni qabul/rad
    etish mumkin emas edi. Bu endpoint hisoblangan moslikni bir marta
    saqlaydi va keyin `MatchDecisionView` ishlaydi.
    """

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        request=MatchRequestSerializer,
        responses={201: MatchSerializer},
    )
    def post(self, request):
        serializer = MatchRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        partner = serializer.validated_data["partner"]

        me_profile = getattr(request.user, "roommate_profile", None)
        if me_profile is None:
            return Response(
                {"detail": "Avval roommate anketani to'ldiring."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        partner_profile = getattr(partner, "roommate_profile", None)
        if partner_profile is None or not partner_profile.is_active:
            return Response(
                {"detail": "Foydalanuvchi topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )

        match, created = Match.for_users(
            request.user, partner, score=compatibility_score(me_profile, partner_profile)
        )

        if created:
            notify(
                partner,
                "new_match",
                {
                    "match_id": match.id,
                    "message": "Sizga roommate so'rovi keldi! Javob bering.",
                },
            )

        return Response(MatchSerializer(match, context={"request": request}).data, status=201)


class MatchDecisionView(APIView):
    """POST /roommates/matches/{id}/decision/ — qabul/rad etish."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        request=MatchDecisionSerializer,
        responses={200: MatchSerializer},
    )
    def post(self, request, pk):
        serializer = MatchDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        decision = serializer.validated_data["decision"]

        match = Match.objects.filter(
            Q(user_a=request.user) | Q(user_b=request.user), pk=pk
        ).select_related("user_a", "user_b").first()
        if match is None:
            return Response({"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        if match.status == Match.Status.ACCEPTED:
            return Response(
                {"detail": "Bu so'rov allaqachon qabul qilingan."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        match.status = Match.Status.ACCEPTED if decision == "accept" else Match.Status.REJECTED
        match.save(update_fields=["status"])

        if decision == "accept":
            partner = match.partner_for(request.user)
            notify(
                partner,
                "new_match",
                {
                    "match_id": match.id,
                    "message": "Sizning roommate so'rovingiz qabul qilindi! Xabar yozing.",
                },
            )
        return Response(MatchSerializer(match, context={"request": request}).data)