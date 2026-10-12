from rest_framework import serializers
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "sku",
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "stock",
            "description",
        ]
        read_only_fields = ["stock"]

    def get_price(self, obj: Product) -> str:
        return f"{obj.price:.2f}"
