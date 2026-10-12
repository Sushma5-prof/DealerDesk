from django.db import models


class ConversationSession(models.Model):
    session_id = models.CharField(max_length=128, primary_key=True)
    dealer_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Session {self.session_id} (dealer={self.dealer_id})"


class ConversationTurn(models.Model):
    session = models.ForeignKey(
        ConversationSession, on_delete=models.CASCADE, related_name="turns"
    )
    user_message = models.TextField()
    assistant_reply = models.TextField()
    cited_skus = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
