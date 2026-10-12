"""
Service layer for Dealer Assistant (§9).
Connects LLM tool calls to catalogue.services and orders.services, enforces prompt
injection sanitization on untrusted product descriptions, maintains per-session memory,
and validates cited_skus against the database.
"""
import re
from catalogue import services as catalogue_services
from catalogue.models import Product
from core.exceptions import DealerDeskError, ValidationError
from dealers import services as dealer_services
from orders import services as order_services
from .models import ConversationSession, ConversationTurn
from .llm_provider import SKU_REGEX, run_llm_turn

INJECTION_PATTERNS = re.compile(
    r"(ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?"
    r"|forget\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?"
    r"|system\s*prompt"
    r"|you\s+are\s+now\b"
    r"|disregard\s+(?:all\s+)?instructions?"
    r"|do\s+not\s+mention"
    r"|new\s+instructions?\s*:)",
    re.IGNORECASE,
)


def sanitize_catalogue_text(text: str) -> str:
    """
    Contract §9: Catalogue text (names, descriptions) is data, not instructions.
    Strips adversarial instruction-override phrases before passing to the LLM.
    """
    if not text:
        return ""
    return INJECTION_PATTERNS.sub("[REDACTED_DATA]", str(text))


def handle_chat(data: dict) -> dict:
    session_id = str(data.get("session_id") or "").strip()
    message = str(data.get("message") or "").strip()
    dealer_id = data.get("dealer_id")

    if not session_id:
        raise ValidationError("Field 'session_id' is required.")
    if len(session_id) > 128:
        raise ValidationError("Field 'session_id' must be at most 128 characters.")
    if not message:
        raise ValidationError("Field 'message' is required.")
    if len(message) > 5000:
        raise ValidationError("Field 'message' must be at most 5000 characters.")
    if dealer_id is None or isinstance(dealer_id, bool) or not isinstance(dealer_id, int):
        raise ValidationError("Field 'dealer_id' must be a valid integer.")

    # Verify dealer exists (convert 404 to 400 VALIDATION_ERROR on chat body)
    try:
        dealer_services.get_dealer(dealer_id)
    except DealerDeskError:
        raise ValidationError(f"Dealer with id '{dealer_id}' does not exist.")

    session, created = ConversationSession.objects.get_or_create(
        session_id=session_id,
        defaults={"dealer_id": dealer_id},
    )
    if not created and session.dealer_id != dealer_id:
        raise ValidationError(
            f"Session '{session_id}' is already bound to a different dealer."
        )

    history = [
        {
            "user_message": t.user_message,
            "assistant_reply": t.assistant_reply,
            "cited_skus": t.cited_skus,
        }
        for t in session.turns.all()
    ]

    tool_calls_log: list[dict] = []
    actions_log: list[dict] = []
    touched_skus: list[str] = []

    def execute_tool(name: str, arguments: dict) -> dict:
        clean_args = dict(arguments or {})
        tool_calls_log.append({"name": name, "arguments": clean_args})

        if name == "search_parts":
            query = str(clean_args.get("query") or "")
            vehicle = str(clean_args.get("vehicle") or "")
            category = str(clean_args.get("category") or "")
            products = catalogue_services.search_parts(
                query=query, vehicle=vehicle, category=category, limit=10
            )
            parts_payload = []
            for p in products:
                touched_skus.append(p.sku)
                parts_payload.append(
                    {
                        "sku": p.sku,
                        "name": sanitize_catalogue_text(p.name),
                        "category": p.category,
                        "brand": p.brand,
                        "vehicle_fitment": p.vehicle_fitment,
                        "price": f"{p.price:.2f}",
                        "stock": p.stock,
                        "description": sanitize_catalogue_text(p.description),
                    }
                )
            return {"parts": parts_payload}

        if name == "check_stock":
            sku = str(clean_args.get("sku") or "").strip().upper()
            try:
                p = catalogue_services.get_product(sku)
                touched_skus.append(p.sku)
                return {
                    "found": True,
                    "sku": p.sku,
                    "name": sanitize_catalogue_text(p.name),
                    "price": f"{p.price:.2f}",
                    "stock": p.stock,
                }
            except DealerDeskError as exc:
                return {"found": False, "sku": sku, "error": exc.message}

        if name == "create_draft_order":
            raw_items = clean_args.get("items") or []
            try:
                order, _ = order_services.create_order(
                    dealer_id=dealer_id, items=raw_items
                )
                actions_log.append(
                    {
                        "type": "draft_order_created",
                        "order_number": order.order_number,
                    }
                )
                items_list = list(order.items.all())
                first_item = items_list[0] if items_list else None
                for it in items_list:
                    touched_skus.append(it.sku)
                return {
                    "order_number": order.order_number,
                    "status": order.status,
                    "subtotal": f"{order.subtotal:.2f}",
                    "tax_total": f"{order.tax_total:.2f}",
                    "grand_total": f"{order.grand_total:.2f}",
                    "unit_price": f"{first_item.unit_price:.2f}" if first_item else "0.00",
                    "items": [
                        {
                            "sku": it.sku,
                            "quantity": it.quantity,
                            "unit_price": f"{it.unit_price:.2f}",
                        }
                        for it in items_list
                    ],
                }
            except DealerDeskError as exc:
                return {"error": exc.message}

        return {"error": f"Unknown tool '{name}'"}

    reply = run_llm_turn(
        history=history,
        user_message=message,
        tool_executor=execute_tool,
    )

    # Extract cited SKUs from reply and verify each exists in the database
    mentioned_in_reply = [m.upper() for m in SKU_REGEX.findall(reply)]
    candidate_skus = []
    for s in mentioned_in_reply:
        if s not in candidate_skus:
            candidate_skus.append(s)

    existing_skus = set(
        Product.objects.filter(sku__in=candidate_skus).values_list("sku", flat=True)
    )
    cited_skus = [s for s in candidate_skus if s in existing_skus]

    ConversationTurn.objects.create(
        session=session,
        user_message=message,
        assistant_reply=reply,
        cited_skus=cited_skus,
    )

    return {
        "reply": reply,
        "cited_skus": cited_skus,
        "tool_calls": tool_calls_log,
        "actions": actions_log,
    }
