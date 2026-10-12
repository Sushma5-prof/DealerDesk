from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.pagination import StandardPagination
from .serializers import DealerSerializer
from . import services


class DealerListCreateView(APIView):
    """
    GET /api/dealers/
    POST /api/dealers/
    """

    def get(self, request):
        qs = services.list_dealers()
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = DealerSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        dealer = services.create_dealer(data)
        return Response(DealerSerializer(dealer).data, status=status.HTTP_201_CREATED)


class DealerDetailView(APIView):
    """
    GET /api/dealers/{id}/
    """

    def get(self, request, dealer_id: int):
        dealer = services.get_dealer(dealer_id)
        return Response(DealerSerializer(dealer).data, status=status.HTTP_200_OK)
