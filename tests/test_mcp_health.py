"""Directory health-check contract for /mcp.

Glama (and kin) initialize then tools/list, often without a sticky
session. tools/list must not 400 when Mcp-Session-Id is missing.
"""

import json
import unittest

from src.mcp_server.server import app


class McpHealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.c = app.test_client()

    def test_tools_list_without_session_is_200(self):
        r = self.c.post(
            "/mcp",
            data=json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:400])
        body = r.get_json()
        self.assertIn("result", body)
        tools = body["result"].get("tools") or body["result"].get("root", {}).get("tools")
        if tools is None and "structuredContent" not in body.get("result", {}):
            # ServerResult dump may nest under 'root' or be the list itself
            dumped = body["result"]
            tools = dumped.get("tools") if isinstance(dumped, dict) else dumped
        self.assertTrue(tools, f"no tools in {list(body.get('result', {}))}")

    def test_initialized_notify_without_session_is_202(self):
        r = self.c.post(
            "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 202, r.get_data(as_text=True)[:400])

    def test_ping_without_session_is_200(self):
        r = self.c.post(
            "/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:400])
        self.assertEqual(r.get_json().get("result"), {})

    def test_tools_call_without_session_is_not_400(self):
        r = self.c.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "compliance_manifest",
                        "arguments": {},
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertNotEqual(r.status_code, 400, r.get_data(as_text=True)[:400])
        self.assertIn(r.status_code, (200, 402))

    def test_paid_tools_call_without_payment_is_402(self):
        r = self.c.post(
            "/mcp",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "upscale_image",
                        "arguments": {"image": "e30="},
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 402, r.get_data(as_text=True)[:400])

    def test_oauth_protected_resource_mcp_is_200(self):
        r = self.c.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:400])
        body = r.get_json()
        self.assertIn("/mcp", body.get("resource", ""))


if __name__ == "__main__":
    unittest.main()
