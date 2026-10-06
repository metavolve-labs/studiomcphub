"""Post-payment settlement and single-use redemption (public-services audit, 2026-10-06; CSO 0541Z M1/M2).

Gaps in check_payment() this module closes:
  * x402: verify_payment() proved the signed permit, but settle_payment() had no caller, so a USDC payer received the
    tool and the funds never moved. The same permit also passed verify N times until it settled (the EIP-3009 nonce is
    consumed only at /settle), and loyalty / tier credit was granted at verify, before anything was collected.
  * Stripe: verify_payment_intent() asked only "succeeded?", never "used already?" or "for this tool and amount?"; and
    once single-use, a tool failure would have burned the payer's one call.

Order of operations now:
  check_payment:  x402 -> verify -> redeem_x402_permit (create-only; a second use is refused)
                  stripe -> verify (tool + amount + not refunded/disputed) -> redeem_payment_intent (create-only)
  tool runs
  success:        settle_after_success -> x402 settle_payment, then the post-payment hooks (tier spend, account, loyalty)
  failure:        release_payment_intent (the Stripe payer keeps their call); x402 was never settled, nothing to undo
A failed x402 settlement is recorded in x402_unsettled so the loss is visible, not silent.
"""
import hashlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger("studiomcphub.settlement")


def _db_or_default(db):
    if db is not None:
        return db
    from .gcx_credits import _get_db
    return _get_db()


def _permit_key(header: str) -> str:
    return hashlib.sha256(header.encode()).hexdigest()[:32]


def redeem_x402_permit(payment_header: str, tool_name: str, amount_usd, db=None) -> bool:
    """Mark a verified x402 permit as spent on exactly one tool call (CSO M1). False on a second use."""
    if not payment_header:
        return False
    try:
        _db_or_default(db).collection("x402_redemptions").document(_permit_key(payment_header)).create({
            "tool_name": tool_name,
            "amount_usd": amount_usd,
            "timestamp": datetime.now(timezone.utc),
        })
        return True
    except Exception as e:
        logger.warning("x402 permit not redeemable (already used, or db error): %s", type(e).__name__)
        return False


def redeem_payment_intent(pi_id: str, tool_name: str, amount_cents: int, db=None) -> bool:
    """Mark a Stripe PaymentIntent as spent on exactly one tool call. False when it was already redeemed."""
    if not pi_id or not pi_id.startswith("pi_"):
        return False
    try:
        _db_or_default(db).collection("stripe_redemptions").document(pi_id).create({
            "tool_name": tool_name,
            "amount_cents": amount_cents,
            "timestamp": datetime.now(timezone.utc),
        })
        return True
    except Exception as e:
        # google.api_core.exceptions.AlreadyExists (Conflict) on a replay; anything else also refuses (fail closed)
        logger.warning("Stripe PaymentIntent %s not redeemable: %s", pi_id, type(e).__name__)
        return False


def release_payment_intent(pi_id: str, db=None) -> bool:
    """The tool failed after a Stripe redemption: give the payer their call back (CSO M2)."""
    if not pi_id:
        return False
    try:
        _db_or_default(db).collection("stripe_redemptions").document(pi_id).delete()
        logger.info("Stripe PaymentIntent %s released after a tool failure", pi_id)
        return True
    except Exception as e:
        logger.error("could not release Stripe PaymentIntent %s: %s", pi_id, e)
        return False


def release_after_failure(method: str, details: dict, db=None) -> bool:
    """Undo what check_payment reserved, after the tool failed. GCX refunds stay where they are (the consumers do them)."""
    if method == "stripe":
        return release_payment_intent((details or {}).get("payment_intent", ""), db=db)
    return True


def result_is_error(result) -> bool:
    """REST dispatch_tool returns a dict; an error-shaped one must not trigger settlement (CSO L1)."""
    if isinstance(result, dict):
        if str(result.get("status", "")).lower() in ("error", "failed", "failure"):
            return True
        if result.get("error"):
            return True
    return False


def _default_hooks():
    from .agent_tiers import record_spend
    from .gcx_credits import ensure_account
    from .loyalty import earn_loyalty
    return record_spend, ensure_account, earn_loyalty


def settle_after_success(method: str, details: dict, tool_name: str, settle=None, db=None, hooks=None) -> bool:
    """Collect an x402 payment after the tool ran, then grant the post-payment hooks (tier spend, account, loyalty).
    Other methods owe nothing here (gcx was deducted up front, stripe was redeemed in check_payment).
    Returns True when nothing is owed or the settlement succeeded."""
    if method != "x402":
        return True
    details = details or {}
    header = details.get("header")
    if not header:
        logger.error("x402 settlement skipped: no payment header on the payment details (tool=%s)", tool_name)
        return False
    if settle is None:
        from .x402 import settle_payment as settle
    try:
        result = settle(header) or {}
    except Exception as e:  # settle_payment already catches; belt and braces
        result = {"settled": False, "error": str(e)}
    if not (result.get("settled") or result.get("success")):
        logger.error("x402 settlement FAILED for %s: %s", tool_name, result)
        try:
            _db_or_default(db).collection("x402_unsettled").document(_permit_key(header)).set({
                "tool_name": tool_name,
                "wallet": details.get("wallet"),
                "amount_usd": details.get("amount_usd"),
                "facilitator_response": result,
                "timestamp": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.error("could not record the unsettled x402 payment: %s", e)
        return False
    # Collected. Only now does the payer earn tier progress, an account and loyalty GCX (CSO M1: these ran at verify).
    wallet = details.get("wallet")
    if wallet:
        record_spend, ensure_account, earn_loyalty = hooks or _default_hooks()
        for name, fn, args in (("record_spend", record_spend, (wallet, details.get("amount_usd"), tool_name)),
                               ("ensure_account", ensure_account, (wallet,)),
                               ("earn_loyalty", earn_loyalty, (wallet, details.get("gcx_credits", 0), tool_name))):
            try:
                fn(*args)
            except Exception as e:
                logger.warning("%s failed after settlement: %s", name, e)
    return True
