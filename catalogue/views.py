from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination
from .serializers import ProductSerializer
from . import services


class ProductListCreateView(APIView):
    """
    GET /api/products/
    POST /api/products/
    """

    def get(self, request):
        qs = services.list_products(
            search=request.query_params.get("search"),
            category=request.query_params.get("category"),
            vehicle=request.query_params.get("vehicle"),
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        product = services.create_product(data)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailView(APIView):
    """
    GET /api/products/{sku}/
    PATCH /api/products/{sku}/
    """

    def get(self, request, sku: str):
        product = services.get_product(sku)
        return Response(ProductSerializer(product).data, status=status.HTTP_200_OK)

    def patch(self, request, sku: str):
        data = request.data if isinstance(request.data, dict) else {}
        product = services.update_product(sku, data)
        return Response(ProductSerializer(product).data, status=status.HTTP_200_OK)


class InventoryUpdateView(APIView):
    """
    PUT /api/inventory/{sku}/
    """

    def put(self, request, sku: str):
        data = request.data if isinstance(request.data, dict) else {}
        product = services.set_inventory(
            sku=sku,
            quantity=data.get("quantity"),
            reason=str(data.get("reason") or ""),
        )
        return Response(
            {"sku": product.sku, "quantity": product.stock},
            status=status.HTTP_200_OK,
        )
