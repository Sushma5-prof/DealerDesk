from rest_framework import serializers
from .models import Order, OrderItem
from . import services


class OrderItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.SerializerMethodField()
    line_subtotal = serializers.SerializerMethodField()
    line_tax = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "sku",
            "name",
            "quantity",
            "unit_price",
            "line_subtotal",
            "line_tax",
            "line_total",
        ]

    def get_unit_price(self, obj: OrderItem) -> str:
        return f"{obj.unit_price:.2f}"

    def get_line_subtotal(self, obj: OrderItem) -> str:
        return f"{obj.line_subtotal:.2f}"

    def get_line_tax(self, obj: OrderItem) -> str:
        return f"{obj.line_tax:.2f}"

    def get_line_total(self, obj: OrderItem) -> str:
        return f"{obj.line_total:.2f}"


class OrderSerializer(serializers.ModelSerializer):
    dealer_id = serializers.IntegerField(source="dealer.id", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    tax_total = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "order_number",
            "dealer_id",
            "status",
            "items",
            "subtotal",
            "tax_total",
            "grand_total",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance: Order):
        if instance.status == Order.STATUS_DRAFT:
            services.sync_draft_prices(instance)
        return super().to_representation(instance)

    def get_subtotal(self, obj: Order) -> str:
        return f"{obj.subtotal:.2f}"

    def get_tax_total(self, obj: Order) -> str:
        return f"{obj.tax_total:.2f}"

    def get_grand_total(self, obj: Order) -> str:
        return f"{obj.grand_total:.2f}"
