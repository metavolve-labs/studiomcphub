"""Stripe per-call payment integration.

For users who prefer traditional payment rails. Creates a PaymentIntent
per tool call, or charges against a saved payment method.
"""

import stripe
import structlog
from datetime import datetime, timezone

from ..mcp_server.config import config

logger = structlog.get_logger()

stripe.api_key = config.stripe_secret_key


def create_payment_intent(
    tool_name: str,
    amount_cents: int,
    customer_id: str | None = None,
) -> dict:
    """Create a Stripe PaymentIntent for a tool call.

    Args:
        tool_name: The tool being called.
        amount_cents: Price in USD cents.
        customer_id: Optional Stripe customer ID for saved payment methods.

    Returns:
        dict with client_secret, payment_intent_id.
    """
    params = {
        "amount": amount_cents,
        "currency": "usd",
        "metadata": {
            "tool": tool_name,
            "service": "studiomcphub",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "automatic_payment_methods": {"enabled": True},
    }
    if customer_id:
        params["customer"] = customer_id

    intent = stripe.PaymentIntent.create(**params)
    logger.info("stripe_intent_created", tool=tool_name, amount=amount_cents)

    return {
        "client_secret": intent.client_secret,
        "payment_intent_id": intent.id,
        "amount_cents": amount_cents,
    }


def verify_payment_intent(payment_intent_id: str, expected_cents: int | None = None, tool_name: str | None = None):
    """Verify a Stripe PaymentIntent has succeeded, and (2026-10-06 audit) that it paid at least `expected_cents` for
    `tool_name` (the metadata create_payment_intent wrote). Returns the intent, or None. Single use is enforced by
    settlement.redeem_payment_intent, not here."""
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["latest_charge"])
    except stripe.error.StripeError as e:
        logger.error("stripe_verify_failed", error=str(e))
        return None
    if intent.status != "succeeded":
        return None
    # CSO 0541Z L2: a refunded or disputed intent keeps status "succeeded"; refuse it
    charge = getattr(intent, "latest_charge", None)
    if charge is not None and not isinstance(charge, str):
        if getattr(charge, "refunded", False) or int(getattr(charge, "amount_refunded", 0) or 0) > 0 or getattr(charge, "disputed", False):
            logger.warning("stripe_intent_reversed", intent=payment_intent_id)
            return None
    if expected_cents is not None and int(intent.amount or 0) < int(expected_cents):
        logger.warning("stripe_intent_underpaid", intent=payment_intent_id, amount=intent.amount, expected=expected_cents)
        return None
    meta_tool = (getattr(intent, "metadata", None) or {}).get("tool")
    if tool_name is not None and meta_tool != tool_name:
        logger.warning("stripe_intent_tool_mismatch", intent=payment_intent_id, paid_for=meta_tool, called=tool_name)
        return None
    return intent
