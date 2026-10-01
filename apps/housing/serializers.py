from rest_framework import serializers

from apps.housing.models import Amenity, Favorite, Listing, ListingImage
from apps.roommates.serializers import mask_phone


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "name", "icon"]


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ["id", "image", "order"]


MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def validate_image_file(image) -> None:
    """Rasm hajmi va turini tekshiradi."""
    if image.size > MAX_IMAGE_BYTES:
        raise serializers.ValidationError(
            f"Rasm {MAX_IMAGE_BYTES // (1024 * 1024)}MB dan oshmasligi kerak."
        )
    content_type = (getattr(image, "content_type", "") or "").lower()
    name = (getattr(image, "name", "") or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES or not any(
        name.endswith(e) for e in ALLOWED_EXTENSIONS
    ):
        raise serializers.ValidationError(
            "Faqat JPG, PNG yoki WEBP formatdagi rasm qabul qilinadi."
        )


class ListingImageUploadSerializer(serializers.Serializer):
    images = serializers.ListField(child=serializers.ImageField(), allow_empty=False)

    def validate_images(self, value):
        for img in value:
            validate_image_file(img)
        return value


class ListingListSerializer(serializers.ModelSerializer):
    # Eslatma: avval bu yerda TO'LIQ telefon raqam har bir ommaviy
    # e'lon uchun chiqarilardi (rajam yig'ish xavfi). Endi yashirilgan.
    owner_phone = serializers.SerializerMethodField()
    owner_verified = serializers.BooleanField(source="owner.is_verified", read_only=True)
    owner_role = serializers.CharField(source="owner.role", read_only=True)
    owner_id = serializers.IntegerField(read_only=True)
    main_image = serializers.SerializerMethodField()
    amenities = AmenitySerializer(many=True, read_only=True)

    class Meta:
        model = Listing
        fields = [
            "id", "title", "type", "price", "currency", "deposit",
            "city", "district", "rooms", "area", "floor", "lat", "lng",
            "main_image", "amenities", "status",
            "owner", "owner_id", "owner_phone", "owner_verified", "owner_role",
            "created_at",
        ]

    def get_owner_phone(self, obj) -> str | None:
        return mask_phone(obj.owner.phone)

    def get_main_image(self, obj) -> str | None:
        # N+1 oldini olish: prefetch qilingan `images` ishlatiladi.
        images = getattr(obj, "images_cache", None)
        if images is None:
            images = list(obj.images.all())
        for img in sorted(images, key=lambda i: i.order):
            if img.image:
                return img.image.url
        return None


class ListingDetailSerializer(ListingListSerializer):
    images = ListingImageSerializer(many=True, read_only=True)

    class Meta(ListingListSerializer.Meta):
        fields = ListingListSerializer.Meta.fields + [
            "description", "address", "total_floors",
            "current_residents", "residents_gender", "smoking_allowed",
            "pets_allowed", "available_from", "images",
        ]


class ListingWriteSerializer(serializers.ModelSerializer):
    # `id` o'qish uchun (write_only emas) — frontend yaratilgan e'lonning
    # `id` sidan keyin `POST /listings/{id}/images/` uchun foydalanadi.
    id = serializers.IntegerField(read_only=True)
    amenity_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Amenity.objects.all(), source="amenities", required=False
    )

    class Meta:
        model = Listing
        fields = [
            "id", "title", "description", "type", "price", "currency", "deposit",
            "city", "district", "address", "lat", "lng", "rooms", "area",
            "floor", "total_floors", "current_residents", "residents_gender",
            "smoking_allowed", "pets_allowed", "available_from", "amenity_ids",
        ]

    def validate(self, attrs):
        """Moderatsiya chegarasi.

        Eslatma: avvalgi versiya `validate()` da faol e'lonlarni sanagan
        va o'z e'lonini ham hisobga olgan — shuning uchun mavjud e'lonni
        PATCH qilishda u moderatsiyaga tushib ketardi. Bu mantiq modelning
        `save()` methodida to'g'ri bajariladi (`.exclude(pk=self.pk)` bilan),
        shuning uchun bu yerda takrorlanmaydi.
        """
        return attrs

    def create(self, validated_data):
        amenities = validated_data.pop("amenities", [])
        instance = Listing.objects.create(owner=self.context["request"].user, **validated_data)
        instance.amenities.set(amenities)
        return instance

    def update(self, instance, validated_data):
        amenities = validated_data.pop("amenities", None)
        instance = super().update(instance, validated_data)
        if amenities is not None:
            instance.amenities.set(amenities)
        return instance
