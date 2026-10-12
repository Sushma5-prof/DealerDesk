from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services


class AssistantChatView(APIView):
    """POST /api/assistant/chat/"""

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        result = services.handle_chat(data)
        return Response(result, status=status.HTTP_200_OK)
