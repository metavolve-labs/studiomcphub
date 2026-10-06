"""Post-payment settlement and single-use redemption (public-services audit, 2026-10-06).

Two gaps in check_payment():
  * x402: verify_payment() proved the signed permit, but settle_payment() had no caller, so a USDC payer received the
    tool and the funds never moved. (0 x402 payments have ever happened: agent_spend is empty, no x402 log lines in 30 d.)
  * Stripe: verify_payment_intent() asked only "succeeded?", never "used already?" or "for this tool and amount?", so one
    PaymentIntent could pay for unlimited calls.

settle_after_success() is called by both tool consumers once the tool has run (the docstring on settle_payment always said
"after successful tool execution"); a failed settlement is recorded in x402_unsettled so the loss is visible, not silent.
redeem_payment_intent() is a create-only Firestore write keyed on the PaymentIntent id: the second use fails.
"""
import hashlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger("studiomcphub.settlement")


def settle_after_success(method: str, details: dict, tool_name: str, settle=None, db=None) -> bool:
    """Collect an x402 payment after the tool ran. Other methods: nothing to do (gcx was deducted up front, stripe was
    redeemed in check_payment). Returns True when nothing is owed or the settlement succeeded."""
    if method != "x402":
        return True
    header = (details or {}).get("header")
    if not header:
        logger.error("x402 settlement skipped: no payment header on the payment details (tool=%s)", tool_name)
        return False
    if settle is None:
        from .x402 import settle_payment as settle
    try:
        result = settle(header) or {}
    except Exception as e:  # settle_payment already catches; belt and braces
        result = {"settled": False, "error": str(e)}
    if result.get("settled") or result.get("success"):
        return True
    logger.error("x402 settlement FAILED for %s: %s", tool_name, result)
    try:
        if db is None:
            from .gcx_credits import _get_db
            db = _get_db()
        key = hashlib.sha256(header.encode()).hexdigest()[:32]
        db.collection("x402_unsettled").document(key).set({
            "tool_name": tool_name,
            "wallet": (details or {}).get("wallet"),
            "amount_usd": (details or {}).get("amount_usd"),
            "facilitator_response": result,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.error("could not record the unsettled x402 payment: %s", e)
    return False


def redeem_payment_intent(pi_id: str, tool_name: str, amount_cents: int, db=None) -> bool:
    """Mark a Stripe PaymentIntent as spent on exactly one tool call. False when it was already redeemed."""
    if not pi_id or not pi_id.startswith("pi_"):
        return False
    if db is None:
        from .gcx_credits import _get_db
        db = _get_db()
    try:
        db.collection("stripe_redemptions").document(pi_id).create({
            "tool_name": tool_name,
            "amount_cents": amount_cents,
            "timestamp": datetime.now(timezone.utc),
        })
        return True
    except Exception as e:
        # google.api_core.exceptions.AlreadyExists (Conflict) on a replay; anything else also refuses (fail closed)
        logger.warning("Stripe PaymentIntent %s not redeemable: %s", pi_id, type(e).__name__)
        return False
