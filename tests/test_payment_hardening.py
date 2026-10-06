"""Payment hardening fixtures (public-services audit, 2026-10-06; CSO 0541Z M1/M2/L1/L2/L3).

Part 1: the helpers (Stripe verify, redemption, x402 settlement). Part 2 (CSO L3): the WIRING, through the real Flask
app: /api/tools/<tool> and MCP tools/call with stubbed verify/settle/dispatch and a fake create-only Firestore. Deleting
a redeem/settle/release line in server.py must fail Part 2. Offline: `stripe` and Firestore are stubbed, no network.
Run from the repo root:  PYTHONPATH=. python3 tests/test_payment_hardening.py -v"""
import json
import sys
import types
import unittest

# --- stub `stripe` before importing anything (not installed locally; never call the network from a test) ---
INTENTS = {}


class _StripeError(Exception):
    pass


class _PI:
    @staticmethod
    def retrieve(pi, expand=None):
        if pi not in INTENTS:
            raise _StripeError("No such payment_intent")
        return INTENTS[pi]


stripe_stub = types.ModuleType("stripe")
stripe_stub.PaymentIntent = _PI
stripe_stub.error = types.SimpleNamespace(StripeError=_StripeError)
stripe_stub.api_key = None
sys.modules.setdefault("stripe", stripe_stub)

from src.payment import settlement  # noqa: E402
from src.payment import gcx_credits, x402  # noqa: E402
from src.payment.stripe_pay import verify_payment_intent  # noqa: E402
import src.tools as tools_pkg  # noqa: E402
import src.mcp_server.server as srv  # noqa: E402
from src.mcp_server.server import app  # noqa: E402
from mcp.types import CallToolRequest, CallToolResult, TextContent  # noqa: E402


def intent(status="succeeded", amount=100, tool="mockup_image", refunded=False, disputed=False):
    charge = types.SimpleNamespace(refunded=refunded, amount_refunded=amount if refunded else 0, disputed=disputed)
    return types.SimpleNamespace(status=status, amount=amount, metadata={"tool": tool}, latest_charge=charge)


class FakeDb:
    """create() is create-only like Firestore's; set() overwrites; delete() removes."""

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

            def delete(self):
                db.docs.pop(self.key, None)

        return types.SimpleNamespace(document=lambda doc_id: Ref(doc_id))


class StripeTests(unittest.TestCase):
    def setUp(self):
        INTENTS.clear()
        INTENTS["pi_ok"] = intent()
        INTENTS["pi_pending"] = intent(status="requires_payment_method")
        INTENTS["pi_cheap"] = intent(amount=10)
        INTENTS["pi_other_tool"] = intent(tool="mint_nft")
        INTENTS["pi_refunded"] = intent(refunded=True)
        INTENTS["pi_disputed"] = intent(disputed=True)

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

    def test_refunded_or_disputed_intent_refused(self):  # CSO L2
        self.assertIsNone(verify_payment_intent("pi_refunded", 100, "mockup_image"))
        self.assertIsNone(verify_payment_intent("pi_disputed", 100, "mockup_image"))

    def test_redemption_is_single_use(self):
        db = FakeDb()
        self.assertTrue(settlement.redeem_payment_intent("pi_ok", "mockup_image", 100, db=db))
        self.assertFalse(settlement.redeem_payment_intent("pi_ok", "mockup_image", 100, db=db), "replay must be refused")
        self.assertFalse(settlement.redeem_payment_intent("pi_ok", "mint_nft", 500, db=db), "replay on another tool too")

    def test_release_gives_the_call_back(self):  # CSO M2
        db = FakeDb()
        self.assertTrue(settlement.redeem_payment_intent("pi_ok", "t", 100, db=db))
        self.assertTrue(settlement.release_after_failure("stripe", {"payment_intent": "pi_ok"}, db=db))
        self.assertTrue(settlement.redeem_payment_intent("pi_ok", "t", 100, db=db), "usable again after a release")

    def test_redemption_refuses_non_pi_ids(self):
        self.assertFalse(settlement.redeem_payment_intent("", "t", 1, db=FakeDb()))
        self.assertFalse(settlement.redeem_payment_intent("cs_test_123", "t", 1, db=FakeDb()))


class X402SettlementTests(unittest.TestCase):
    NOHOOKS = (lambda *a: None, lambda *a: None, lambda *a: None)

    def test_non_x402_methods_owe_nothing(self):
        boom = lambda h: self.fail("must not settle")  # noqa: E731
        self.assertTrue(settlement.settle_after_success("gcx", {"token": "0xabc"}, "t", settle=boom))
        self.assertTrue(settlement.settle_after_success("stripe", {}, "t", settle=boom))
        self.assertTrue(settlement.settle_after_success("free", {}, "t", settle=boom))

    def test_x402_is_settled_with_the_payment_header(self):
        seen = []
        ok = settlement.settle_after_success("x402", {"header": "PERMIT", "wallet": "0xw"}, "t",
                                             settle=lambda h: (seen.append(h), {"settled": True})[1], hooks=self.NOHOOKS)
        self.assertTrue(ok)
        self.assertEqual(seen, ["PERMIT"])

    def test_hooks_run_only_after_a_successful_settlement(self):  # CSO M1 (second half)
        calls = []
        hooks = (lambda *a: calls.append(("spend",) + a), lambda *a: calls.append(("account",) + a), lambda *a: calls.append(("loyalty",) + a))
        d = {"header": "PERMIT", "wallet": "0xw", "amount_usd": 0.2, "gcx_credits": 2}
        settlement.settle_after_success("x402", d, "t", settle=lambda h: {"settled": False}, db=FakeDb(), hooks=hooks)
        self.assertEqual(calls, [], "nothing granted when the funds were not collected")
        settlement.settle_after_success("x402", d, "t", settle=lambda h: {"settled": True}, hooks=hooks)
        self.assertEqual([c[0] for c in calls], ["spend", "account", "loyalty"])
        self.assertEqual(calls[2], ("loyalty", "0xw", 2, "t"))

    def test_failed_settlement_is_recorded_not_silent(self):
        db = FakeDb()
        ok = settlement.settle_after_success("x402", {"header": "PERMIT", "wallet": "0xw", "amount_usd": 0.1}, "mockup_image",
                                             settle=lambda h: {"settled": False, "error": "facilitator down"}, db=db)
        self.assertFalse(ok)
        recs = [v for k, v in db.docs.items() if k.startswith("x402_unsettled/")]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["tool_name"], "mockup_image")

    def test_permit_redemption_is_single_use(self):  # CSO M1
        db = FakeDb()
        self.assertTrue(settlement.redeem_x402_permit("PERMIT", "t", 0.2, db=db))
        self.assertFalse(settlement.redeem_x402_permit("PERMIT", "t", 0.2, db=db))
        self.assertFalse(settlement.redeem_x402_permit("", "t", 0.2, db=db))

    def test_missing_header_is_a_failure(self):
        self.assertFalse(settlement.settle_after_success("x402", {}, "t", settle=lambda h: {"settled": True}, db=FakeDb()))

    def test_result_is_error_shapes(self):  # CSO L1
        self.assertTrue(settlement.result_is_error({"status": "error", "error": "x"}))
        self.assertTrue(settlement.result_is_error({"error": "boom"}))
        self.assertFalse(settlement.result_is_error({"status": "success", "result": 1}))
        self.assertFalse(settlement.result_is_error("text"))


class WiringTests(unittest.TestCase):
    """CSO L3: the server must CALL the helpers. Through the real Flask app, with the outside world stubbed."""
    TOOL = "infuse_metadata"  # 1 GCX = 10 cents

    def setUp(self):
        self.c = app.test_client()
        self.db = FakeDb()
        gcx_credits._db = self.db                     # settlement and gcx_credits read this
        INTENTS.clear()
        INTENTS["pi_ok"] = intent(amount=10, tool=self.TOOL)
        self.settled = []
        self._orig = (x402.verify_payment, x402.settle_payment, tools_pkg.dispatch_tool)
        x402.verify_payment = lambda header, usd: header == "GOODPERMIT"
        x402.settle_payment = lambda header: (self.settled.append(header), {"settled": True})[1]
        self.dispatch_result = {"status": "success", "result": "ok"}
        tools_pkg.dispatch_tool = lambda name, params: self.dispatch_result() if callable(self.dispatch_result) else self.dispatch_result
        # the MCP tools/call handler would run the real tool; stub it to a clean success
        self._server = srv._get_mcp_server()  # the per-worker MCP Server the endpoint dispatches through
        self._orig_handler = self._server.request_handlers.get(CallToolRequest)

        async def fake_handler(req):
            return CallToolResult(content=[TextContent(type="text", text="ok")], isError=False)
        self._server.request_handlers[CallToolRequest] = fake_handler

    def tearDown(self):
        x402.verify_payment, x402.settle_payment, tools_pkg.dispatch_tool = self._orig
        if self._orig_handler is not None:
            self._server.request_handlers[CallToolRequest] = self._orig_handler
        gcx_credits._db = None

    def rest(self, headers):
        return self.c.post(f"/api/tools/{self.TOOL}", json={"image": "aGVsbG8="}, headers=headers)

    def test_stripe_intent_buys_one_call_then_402(self):
        r1 = self.rest({"X-Stripe-Payment-Intent": "pi_ok"})
        self.assertEqual(r1.status_code, 200, r1.get_data(as_text=True)[:300])
        self.assertIn("stripe_redemptions/pi_ok", self.db.docs)
        r2 = self.rest({"X-Stripe-Payment-Intent": "pi_ok"})
        self.assertEqual(r2.status_code, 402, "replay must be refused")

    def test_stripe_payer_keeps_the_call_when_the_tool_fails(self):  # M2 wiring
        def boom():
            raise RuntimeError("tool down")
        self.dispatch_result = boom
        r = self.rest({"X-Stripe-Payment-Intent": "pi_ok"})
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("stripe_redemptions/pi_ok", self.db.docs, "redemption must be released")
        self.dispatch_result = {"status": "success"}
        self.assertEqual(self.rest({"X-Stripe-Payment-Intent": "pi_ok"}).status_code, 200, "the same intent works again")

    def test_stripe_error_shaped_result_releases_too(self):  # L1 + M2 wiring
        self.dispatch_result = {"status": "error", "error": "bad image"}
        self.rest({"X-Stripe-Payment-Intent": "pi_ok"})
        self.assertNotIn("stripe_redemptions/pi_ok", self.db.docs)

    def test_x402_permit_settles_once_and_cannot_be_reused(self):  # M1 wiring
        r1 = self.rest({"X-PAYMENT": "GOODPERMIT"})
        self.assertEqual(r1.status_code, 200, r1.get_data(as_text=True)[:300])
        self.assertEqual(self.settled, ["GOODPERMIT"], "settled exactly once, after the tool")
        self.assertEqual(len([k for k in self.db.docs if k.startswith("x402_redemptions/")]), 1)
        r2 = self.rest({"X-PAYMENT": "GOODPERMIT"})
        self.assertEqual(r2.status_code, 402, "the same permit must not buy a second call")
        self.assertEqual(self.settled, ["GOODPERMIT"])

    def test_x402_not_settled_when_the_tool_fails(self):
        self.dispatch_result = {"status": "error", "error": "x"}
        self.rest({"X-PAYMENT": "GOODPERMIT"})
        self.assertEqual(self.settled, [], "a failed tool collects nothing")

    def test_mcp_tools_call_replay_refused(self):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": self.TOOL, "arguments": {"image": "aGVsbG8="}}}
        r1 = self.c.post("/mcp", data=json.dumps(body), content_type="application/json", headers={"X-Stripe-Payment-Intent": "pi_ok"})
        self.assertIn(r1.status_code, (200, 202), r1.get_data(as_text=True)[:300])
        self.assertIn("stripe_redemptions/pi_ok", self.db.docs)
        r2 = self.c.post("/mcp", data=json.dumps(body), content_type="application/json", headers={"X-Stripe-Payment-Intent": "pi_ok"})
        self.assertEqual(r2.status_code, 402, "MCP path: replay must be refused")


if __name__ == "__main__":
    unittest.main()
