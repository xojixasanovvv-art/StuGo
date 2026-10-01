from django.db.models import Max, Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.permissions import IsModerator, IsOwner, IsVerified
from apps.housing.models import Amenity, Favorite, Listing, ListingImage
from apps.housing.serializers import (
    AmenitySerializer,
    ListingDetailSerializer,
    ListingImageSerializer,
    ListingImageUploadSerializer,
    ListingListSerializer,
    ListingWriteSerializer,
)


from apps.core.pagination import StandardResultsSetPagination


class ListingViewSet(viewsets.ModelViewSet):
    """TZ 5.3 — E'lonlar: CRUD, qidiruv, filtrlar, sevimlilar."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filterset_fields = {
        "type": ["exact"],
        "city": ["exact", "icontains"],
        "district": ["exact", "icontains"],
        "rooms": ["exact", "gte", "lte"],
        "price": ["gte", "lte"],
        "currency": ["exact"],
        "amenities": ["exact"],
        "smoking_allowed": ["exact"],
        "pets_allowed": ["exact"],
    }
    search_fields = ["title", "description", "city", "district"]
    ordering_fields = ["price", "created_at", "area"]
    ordering = ["-created_at"]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "listing_create"

    def get_throttles(self):
        # Throttle faqat yaratishga (POST) qo'llanadi; o'qish/tahrirlash
        # foydalanuvchini bloklamasligi kerak.
        if self.request.method != "POST" or self.action not in ("create", None):
            return []
        return super().get_throttles()

    def get_queryset(self):
        # Swagger schema generation `swagger_fake_view` bilan so'rov yuboradi:
        # `request.user` — `AnonymousUser`, shuning uchun querysetni olish
        # muvaffaqiyatsiz bo'lardi va schema xatosi chiqardi.
        if getattr(self, "swagger_fake_view", False):
            return Listing.objects.none()

        user = self.request.user
        base = Listing.objects.select_related("owner").prefetch_related("images", "amenities")
        if self.action in ["retrieve", "list", "favorite"]:
            # Faqat faol e'lonlar yoki o'z e'lonlari
            return base.filter(Q(status=Listing.Status.ACTIVE) | Q(owner=user))
        return base.filter(owner=user)

    def get_serializer_class(self):
        if self.action == "list":
            return ListingListSerializer
        if self.action in ["create", "update", "partial_update"]:
            return ListingWriteSerializer
        return ListingDetailSerializer

    def get_permissions(self):
        if self.action in ["list", "retrieve", "favorite", "favorites"]:
            return [IsAuthenticated()]
        if self.action == "create":
            return [IsVerified()]
        return [IsAuthenticated(), IsOwner()]

    @extend_schema(responses=ListingListSerializer)
    def list(self, request, *args, **kwargs):
        """Mehmonlar uchun ham cheklangan ko'rish (TZ 6) — hozircha auth kerak."""
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()

    @extend_schema(request=None, responses=ListingDetailSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def favorite(self, request, pk=None):
        """POST /listings/{id}/favorite/ — sevimlilarga qo'shish/o'chirish (toggle)."""
        listing = self.get_object()
        fav, created = Favorite.objects.get_or_create(user=request.user, listing=listing)
        if not created:
            fav.delete()
            return Response({"favorited": False})
        return Response({"favorited": True})

    @extend_schema(responses=ListingListSerializer(many=True))
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def favorites(self, request):
        """GET /listings/favorites/ — mening sevimlilarim."""
        favs = (
            Favorite.objects.filter(user=request.user)
            .select_related("listing__owner")
            .prefetch_related("listing__images", "listing__amenities")
        )
        page = self.paginator
        paginated = page.paginate_queryset(favs, request, view=self)
        data = ListingListSerializer(
            [f.listing for f in (paginated if paginated is not None else favs)],
            many=True,
        ).data
        if paginated is not None:
            return page.get_paginated_response(data)
        return Response(data)

    @extend_schema(request=None, responses=ListingDetailSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsOwner])
    def archive(self, request, pk=None):
        """POST /listings/{id}/archive/ — arxivlaydi (fizik o'chirish emas).

        Eslatma: `DELETE` ListingImage va Favorite qatorlarini CASCADE
        bilan o'chirdi va diskdagi rasm fayllari qoldi. `archive` xavfsizroq.
        """
        listing = self.get_object()
        listing.archive()
        return Response(ListingDetailSerializer(listing).data)


class MyListingsView(ListAPIView):
    """GET /listings/mine/ — faqat o'z e'lonlarim (barcha statuslar)."""

    serializer_class = ListingListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Listing.objects.none()
        return Listing.objects.filter(owner=self.request.user).select_related("owner")


class AmenityListView(ListAPIView):
    """GET /amenities/ — jihozlar ro'yxati."""

    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [AllowAny]
    pagination_class = None


class ListingImageViewSet(viewsets.GenericViewSet):
    """E'lon rasmlari: POST (yuklash), DELETE (o'chirish)."""

    serializer_class = ListingImageSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        # IsOwner `obj.owner_id` kutadi, lekin bu viewset `ListingImage`
        # bilan ishlaydi (uning `owner` maydoni yo'q). Shuning uchun ruxsat
        # qo'lda tekshiriladi — `IsOwner` bu yerda ishlamagan/dekorativ edi.
        return [IsAuthenticated()]

    def _get_listing(self, pk):
        return Listing.objects.filter(pk=pk).first()

    def _get_own_listing(self, request, pk):
        listing = self._get_listing(pk)
        if listing is None or listing.owner_id != request.user.id:
            return None
        return listing

    @extend_schema(
        request=ListingImageUploadSerializer,
        responses={201: ListingDetailSerializer},
    )
    def create(self, request, listing_pk=None):
        listing = self._get_own_listing(request, listing_pk)
        if listing is None:
            return Response({"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        files = request.FILES.getlist("images")
        if not files:
            return Response(
                {"images": "Rasm yuborilishi shart."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = listing.images.count()
        if existing + len(files) > Listing.MAX_IMAGES:
            return Response(
                {"images": f"Ko'pi bilan {Listing.MAX_IMAGES} rasm bo'lishi mumkin (hozir {existing})."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = ListingImageUploadSerializer(data={"images": files})
        ser.is_valid(raise_exception=True)

        start = listing.images.aggregate(m=Max("order"))["m"] or 0
        ListingImage.objects.bulk_create(
            [
                ListingImage(listing=listing, image=img, order=start + i)
                for i, img in enumerate(ser.validated_data["images"], start=1)
            ]
        )

        # TZ 5.3: kamida MIN_IMAGES rasm bo'lmasa — e'lon moderatsiyada qoladi.
        if listing.images.count() < Listing.MIN_IMAGES and listing.status == Listing.Status.ACTIVE:
            listing.status = Listing.Status.MODERATION
            listing.save(update_fields=["status", "updated_at"])

        listing.refresh_from_db()
        return Response(
            ListingDetailSerializer(listing).data, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=None, responses={204: None})
    def destroy(self, request, listing_pk=None, pk=None):
        listing = self._get_own_listing(request, listing_pk)
        if listing is None:
            return Response({"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        img = ListingImage.objects.filter(pk=pk, listing=listing).first()
        if img is None:
            return Response({"detail": "Topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        img.image.delete(save=False)
        img.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ListingModerationListView(ListAPIView):
    """GET /admin/listings/moderation/ — moderatsiyadagi e'lonlar (moderator)."""

    serializer_class = ListingListSerializer
    permission_classes = [IsModerator]

    def get_queryset(self):
        return Listing.objects.filter(status=Listing.Status.MODERATION).select_related("owner")
