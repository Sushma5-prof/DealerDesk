from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination
from .serializers import OrderSerializer
from . import services


class OrderListCreateView(APIView):
    """
    GET /api/orders/
    POST /api/orders/
    """

    def get(self, request):
        qs = services.list_orders(
            dealer_id=request.query_params.get("dealer_id"),
            status_filter=request.query_params.get("status"),
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = OrderSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        idem_key = request.headers.get("Idempotency-Key")
        order, created = services.create_order(
            dealer_id=data.get("dealer_id"),
            items=data.get("items"),
            idempotency_key=idem_key,
        )
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(OrderSerializer(order).data, status=http_status)


class OrderDetailUpdateView(APIView):
    """
    GET /api/orders/{order_number}/
    PUT /api/orders/{order_number}/
    """

    def get(self, request, order_number: str):
        order = services.get_order(order_number)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)

    def put(self, request, order_number: str):
        data = request.data if isinstance(request.data, dict) else {}
        order = services.update_order_items(order_number, data.get("items"))
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderConfirmView(APIView):
    def post(self, request, order_number: str):
        order = services.confirm_order(order_number)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderDispatchView(APIView):
    def post(self, request, order_number: str):
        order = services.dispatch_order(order_number)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderDeliverView(APIView):
    def post(self, request, order_number: str):
        order = services.deliver_order(order_number)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)


class OrderCancelView(APIView):
    def post(self, request, order_number: str):
        order = services.cancel_order(order_number)
        return Response(OrderSerializer(order).data, status=status.HTTP_200_OK)
