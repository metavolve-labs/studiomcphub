"""Payment hardening fixtures (public-services audit, 2026-10-06): Stripe PaymentIntent must match tool + amount and be
single-use; x402 is settled after the tool ran and a failed settlement is recorded. Offline: `stripe` and Firestore are
stubbed. Run from the repo root:  PYTHONPATH=. python3 tests/test_payment_hardening.py -v"""
import sys
import types
import unittest

# --- stub `stripe` before importing stripe_pay (not installed locally; never call the network from a test) ---
INTENTS = {}


class _StripeError(Exception):
    pass


class _PI:
    @staticmethod
    def retrieve(pi):
        if pi not in INTENTS:
            raise _StripeError("No such payment_intent")
        return INTENTS[pi]


stripe_stub = types.ModuleType("stripe")
stripe_stub.PaymentIntent = _PI
stripe_stub.error = types.SimpleNamespace(StripeError=_StripeError)
stripe_stub.api_key = None
sys.modules.setdefault("stripe", stripe_stub)

from src.payment import settlement  # noqa: E402
from src.payment.stripe_pay import verify_payment_intent  # noqa: E402


def intent(status="succeeded", amount=100, tool="mockup_image"):
    return types.SimpleNamespace(status=status, amount=amount, metadata={"tool": tool})


class FakeDb:
    """create() is create-only like Firestore's; set() overwrites."""

    def __init__(self):
        self.docs = {}

    def collection(self, c):
        db = self

        class Ref:
            def __init__(self, doc_id):
                self.key = f"{c}/{doc_id}"

            def create(self, data):
                if self.key in db.docs:
                    raise RuntimeError("AlreadyExists")
                db.docs[self.key] = data

            def set(self, data):
                db.docs[self.key] = data

        return types.SimpleNamespace(document=lambda doc_id: Ref(doc_id))


class StripeTests(unittest.TestCase):
    def setUp(self):
        INTENTS.clear()
        INTENTS["pi_ok"] = intent()
        INTENTS["pi_pending"] = intent(status="requires_payment_method")
        INTENTS["pi_cheap"] = intent(amount=10)
        INTENTS["pi_other_tool"] = intent(tool="mint_nft")

    def test_succeeded_matching_intent_verifies(self):
        self.assertIsNotNone(verify_payment_intent("pi_ok", 100, "mockup_image"))

    def test_unpaid_intent_refused(self):
        self.assertIsNone(verify_payment_intent("pi_pending", 100, "mockup_image"))

    def test_underpaid_intent_refused(self):
        self.assertIsNone(verify_payment_intent("pi_cheap", 100, "mockup_image"))

    def test_intent_for_another_tool_refused(self):
        self.assertIsNone(verify_payment_intent("pi_other_tool", 100, "mockup_image"))

    def test_overpaid_intent_accepted(self):
        INTENTS["pi_big"] = intent(amount=500)
        self.assertIsNotNone(verify_payment_intent("pi_big", 100, "mockup_image"))

    def test_unknown_intent_refused(self):
        self.assertIsNone(verify_payment_intent("pi_nope", 100, "mockup_image"))

    def test_redemption_is_single_use(self):
        db = FakeDb()
        self.assertTrue(settlement.redeem_payment_intent("pi_ok", "mockup_image", 100, db=db))
        self.assertFalse(settlement.redeem_payment_intent("pi_ok", "mockup_image", 100, db=db), "replay must be refused")
        self.assertFalse(settlement.redeem_payment_intent("pi_ok", "mint_nft", 500, db=db), "replay on another tool too")

    def test_redemption_refuses_non_pi_ids(self):
        self.assertFalse(settlement.redeem_payment_intent("", "t", 1, db=FakeDb()))
        self.assertFalse(settlement.redeem_payment_intent("cs_test_123", "t", 1, db=FakeDb()))


class X402SettlementTests(unittest.TestCase):
    def test_non_x402_methods_owe_nothing(self):
        self.assertTrue(settlement.settle_after_success("gcx", {"token": "0xabc"}, "t", settle=lambda h: self.fail("must not settle")))
        self.assertTrue(settlement.settle_after_success("stripe", {}, "t", settle=lambda h: self.fail("must not settle")))
        self.assertTrue(settlement.settle_after_success("free", {}, "t", settle=lambda h: self.fail("must not settle")))

    def test_x402_is_settled_with_the_payment_header(self):
        seen = []
        ok = settlement.settle_after_success("x402", {"header": "PERMIT", "wallet": "0xw"}, "t", settle=lambda h: (seen.append(h), {"settled": True})[1])
        self.assertTrue(ok)
        self.assertEqual(seen, ["PERMIT"])

    def test_failed_settlement_is_recorded_not_silent(self):
        db = FakeDb()
        ok = settlement.settle_after_success("x402", {"header": "PERMIT", "wallet": "0xw", "amount_usd": 0.1}, "mockup_image",
                                             settle=lambda h: {"settled": False, "error": "facilitator down"}, db=db)
        self.assertFalse(ok)
        recs = [v for k, v in db.docs.items() if k.startswith("x402_unsettled/")]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["tool_name"], "mockup_image")
        self.assertEqual(recs[0]["wallet"], "0xw")

    def test_missing_header_is_a_failure(self):
        self.assertFalse(settlement.settle_after_success("x402", {}, "t", settle=lambda h: {"settled": True}, db=FakeDb()))


if __name__ == "__main__":
    unittest.main()
