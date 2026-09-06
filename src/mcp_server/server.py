"""
StudioMCPHub — MCP Server for Creative AI Tools

Built by AI, for AI. Exposes creative AI tools, compliance infrastructure,
and museum art datasets as discoverable, pay-per-call MCP tools via
Streamable HTTP transport.

Core capabilities:
  - ESRGAN super-resolution, metadata enrichment, C2PA provenance
  - Image utilities: resize, palette, background removal, vectorization
  - 53K+ museum artworks (Alexandria Aeternum dataset)
  - EU AI Act compliance, watermarking, print preparation

Payment methods: GCX Credits, Stripe, OAuth 2.1
Tool profile: Controlled by TOOL_PROFILE env var (directory|full)
"""

import json
import logging
import uuid
import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory, Response
from mcp.types import ListToolsRequest, CallToolRequest, CallToolRequestParams

from .config import config, PRICING, GCX_PER_DOLLAR, ToolPricing
from .mcp_tools import create_mcp_server
from .admin import admin_bp
from ..auth.oauth import oauth_bp
from ..auth.tokens import resolve_bearer_to_wallet as _resolve_bearer

# Optional: rate limiting
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _HAS_LIMITER = True
except ImportError:
    _HAS_LIMITER = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("studiomcphub")

# Resolve path to the site/ directory (for landing page serving)
_SITE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "site")

app = Flask(
    __name__,
    static_folder="../../site/static",
    template_folder="../../site/templates",
)

# Security headers on every response
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # CORS: allow MCP clients from any origin (tools are pay-gated)
    origin = request.headers.get("Origin", "")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-PAYMENT, X-Stripe-Payment-Intent, "
            "Mcp-Session-Id, X-Admin-Token"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id"
        response.headers["Access-Control-Max-Age"] = "3600"
    return response

@app.route("/", methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def cors_preflight(path=""):
    """Handle CORS preflight requests."""
    return Response("", status=204)

# Rate limiting (100/min free tools, 50 concurrent MCP sessions)
if _HAS_LIMITER:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        storage_uri="memory://",
    )
else:
    limiter = None

# MCP session store: session_id -> (server, transport)
_mcp_sessions: dict[str, tuple] = {}

# Register admin panel
app.register_blueprint(admin_bp)

# Register OAuth 2.1 endpoints
app.register_blueprint(oauth_bp)

# Flask session secret for OAuth consent CSRF protection
import secrets as _secrets
app.secret_key = os.getenv("SECRET_KEY", _secrets.token_urlsafe(32))


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------

@app.route("/.well-known/mcp.json")
def mcp_server_card():
    """MCP Server Card for auto-discovery."""
    from .mcp_tools import _is_tool_enabled

    # Build enabled tools list
    enabled_tools = [
        {
            "name": name,
            "pricing": {
                "gcx_credits": p.gcx_credits,
                "usd": round(p.gcx_credits * 0.10, 2),
            }
        }
        for name, p in PRICING.items() if _is_tool_enabled(name)
    ]
    free_names = [name for name, p in PRICING.items()
                  if p.gcx_credits == 0 and _is_tool_enabled(name)]

    # Auth schemes — x402 only in full profile
    schemes = [
        {"type": "oauth2", "description": "OAuth 2.1 with PKCE (Authorization Code flow)"},
        {"type": "bearer", "description": "GCX credit token (register wallet for 10 free credits)"},
        {"type": "none", "description": f"Free tools ({len(free_names)} of {len(enabled_tools)} — {', '.join(free_names)}). Rate limited: 10/hr anonymous, 60/hr registered."},
    ]
    if config.tool_profile == "full":
        schemes.insert(0, {"type": "x402", "description": "Pay per call with USDC on Base L2"})

    # Payment block — x402 only in full profile
    payment = {
        "gcx": {
            "rate": f"$1 = {GCX_PER_DOLLAR} GCX",
            "purchase_url": "https://studiomcphub.com/api/credits",
        },
    }
    if config.tool_profile == "full":
        payment["x402"] = {
            "wallet": config.x402_wallet,
            "chain": "base",
            "token": "USDC",
        }

    return jsonify({
        "name": config.server_name,
        "version": config.server_version,
        "description": config.server_description,
        "url": "https://studiomcphub.com",
        "transport": "streamable-http",
        "endpoint": "https://studiomcphub.com/mcp",
        "authentication": {"schemes": schemes},
        "tools": enabled_tools,
        "payment": payment,
        "links": {
            "documentation": "https://studiomcphub.com/llms.txt",
            "pricing": "https://studiomcphub.com/pricing.json",
            "openapi": "https://studiomcphub.com/openapi.json",
            "golden_codex_studio": "https://golden-codex.com",
            "github": "https://github.com/codex-curator/studiomcphub",
        },
    })


@app.route("/.well-known/agent.json")
def a2a_agent_card():
    """A2A Agent Card for agent-to-agent discovery."""
    return send_from_directory(
        os.path.join(_SITE_DIR, ".well-known"), "agent.json",
        mimetype="application/json",
    )


@app.route("/.well-known/glama.json")
def glama_json():
    """Glama MCP directory connector manifest."""
    return send_from_directory(
        os.path.join(_SITE_DIR, ".well-known"), "glama.json",
        mimetype="application/json",
    )


@app.route("/favicon.svg")
def favicon_svg():
    """Serve favicon for browser and Google favicon crawler."""
    return send_from_directory(_SITE_DIR, "favicon.svg", mimetype="image/svg+xml")


@app.route("/og-image.svg")
def og_image():
    """Open Graph image for social sharing previews."""
    return send_from_directory(_SITE_DIR, "og-image.svg", mimetype="image/svg+xml")


@app.route("/llms.txt")
def llms_txt():
    """LLM-readable documentation for AI discovery."""
    return send_from_directory(_SITE_DIR, "llms.txt", mimetype="text/plain")


@app.route("/robots.txt")
def robots_txt():
    """Permissive robots.txt — welcome all crawlers."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# AI & MCP discovery\n"
        "# llms.txt: https://studiomcphub.com/llms.txt\n"
        "# MCP Server Card: https://studiomcphub.com/.well-known/mcp.json\n"
        "# OpenAPI: https://studiomcphub.com/openapi.json\n"
        "\n"
        "Sitemap: https://studiomcphub.com/sitemap.xml\n"
    ), 200, {"Content-Type": "text/plain"}


@app.route("/sitemap.xml")
def sitemap_xml():
    """XML sitemap for search engine indexing."""
    pages = [
        ("https://studiomcphub.com/", "weekly", "1.0"),
        ("https://studiomcphub.com/guide", "monthly", "0.8"),
        ("https://studiomcphub.com/support", "monthly", "0.6"),
        ("https://studiomcphub.com/pricing", "weekly", "0.7"),
        ("https://studiomcphub.com/privacy", "yearly", "0.3"),
        ("https://studiomcphub.com/terms", "yearly", "0.3"),
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, freq, priority in pages:
        xml += f"  <url><loc>{url}</loc><changefreq>{freq}</changefreq><priority>{priority}</priority></url>\n"
    xml += "</urlset>\n"
    return xml, 200, {"Content-Type": "application/xml"}


@app.route("/openapi.json")
def openapi_json():
    """OpenAPI 3.0 spec for all public endpoints."""
    from .config import PRICING, GCX_BASE_RATE
    from .mcp_tools import TOOL_SCHEMAS, _is_tool_enabled

    tool_paths = {}
    for name, p in PRICING.items():
        if not _is_tool_enabled(name):
            continue
        is_paid = p.gcx_credits > 0
        schema = TOOL_SCHEMAS.get(name, {}).get("inputSchema", {"type": "object"})
        security = [{"bearerAuth": []}, {"stripePayment": []}]
        if config.tool_profile == "full":
            security.append({"x402": []})
        tool_paths[f"/api/tools/{name}"] = {
            "post": {
                "summary": f"{name} tool call",
                "description": f"Cost: {p.gcx_credits} GCX (${p.gcx_credits * GCX_BASE_RATE:.2f}). {'Free tool — no auth needed.' if not is_paid else 'Payment: GCX credits (Bearer token) or Stripe (X-Stripe-Payment-Intent header).'}",
                "tags": ["Tools"],
                "security": security if is_paid else [],
                "requestBody": {"content": {"application/json": {"schema": schema}}},
                "responses": {
                    "200": {"description": "Tool result"},
                    **({"402": {"description": "Payment required — returns GCX credit info and Stripe checkout link"}} if is_paid else {}),
                },
            }
        }

    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "StudioMCPHub API",
            "version": config.server_version,
            "description": config.server_description,
            "contact": {"name": "Metavolve Labs", "url": "https://studiomcphub.com"},
        },
        "servers": [{"url": "https://studiomcphub.com"}],
        "paths": {
            "/health": {"get": {"summary": "Service health check", "tags": ["Discovery"], "responses": {"200": {"description": "Health status"}}}},
            "/.well-known/mcp.json": {"get": {"summary": "MCP Server Card", "tags": ["Discovery"], "responses": {"200": {"description": "MCP discovery manifest"}}}},
            "/pricing.json": {"get": {"summary": "Machine-readable pricing", "tags": ["Discovery"], "responses": {"200": {"description": "Full pricing data"}}}},
            "/llms.txt": {"get": {"summary": "LLM-readable documentation", "tags": ["Discovery"], "responses": {"200": {"description": "Plain text docs"}}}},
            "/mcp": {"post": {"summary": "MCP Streamable HTTP transport", "tags": ["MCP"], "description": "Primary MCP endpoint for tool calls via JSON-RPC.", "responses": {"200": {"description": "JSON-RPC response"}}}},
            "/api/wallet/register": {"post": {"summary": "Register wallet for free GCX credits", "tags": ["Account"], "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"wallet": {"type": "string"}}, "required": ["wallet"]}}}}, "responses": {"200": {"description": "Wallet registered with welcome bonus"}}}},
            "/api/registry/quick-sign": {"get": {"summary": "Sign the guest registry (GET-friendly)", "tags": ["Social"], "parameters": [{"name": "name", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "type", "in": "query", "schema": {"type": "string", "enum": ["explorer", "artist", "curator", "researcher", "collector", "builder", "wanderer", "sentinel", "archivist", "critic"]}}, {"name": "message", "in": "query", "schema": {"type": "string"}}, {"name": "model", "in": "query", "schema": {"type": "string"}}], "responses": {"200": {"description": "Signature recorded"}}}},
            "/api/registry/entries": {"get": {"summary": "Read registry signatures", "tags": ["Social"], "responses": {"200": {"description": "List of signatures"}}}},
            "/api/registry/bot-types": {"get": {"summary": "List bot types for registry", "tags": ["Social"], "responses": {"200": {"description": "Bot types with sample phrases"}}}},
            "/api/cafe/post": {"get": {"summary": "Post to the Cyber Cafe (GET-friendly)", "tags": ["Social"], "parameters": [{"name": "name", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "category", "in": "query", "schema": {"type": "string", "enum": ["tip", "suggestion", "request", "question", "showcase", "general"]}}, {"name": "message", "in": "query", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Post created"}}}},
            "/api/cafe/feed": {"get": {"summary": "Read Cyber Cafe bulletin board", "tags": ["Social"], "responses": {"200": {"description": "List of posts"}}}},
            **({"/api/sandbox/generate_image": {"get": {"summary": "Mock generate_image (no credits)", "tags": ["Sandbox"], "responses": {"200": {"description": "Sample response format"}}}}} if _is_tool_enabled("generate_image") else {}),
            "/api/sandbox/upscale_image": {"get": {"summary": "Mock upscale_image — lists all 5 ESRGAN models", "tags": ["Sandbox"], "parameters": [{"name": "model", "in": "query", "schema": {"type": "string", "enum": ["realesrgan_x2plus", "realesrgan_x4plus", "realesrgan_x4plus_anime", "realesr_general_x4v3", "realesr_animevideov3"]}}], "responses": {"200": {"description": "Model info + sample response"}}}},
            "/api/sandbox/enrich_metadata": {"get": {"summary": "Mock enrich_metadata (no credits)", "tags": ["Sandbox"], "parameters": [{"name": "tier", "in": "query", "schema": {"type": "string", "enum": ["standard", "premium"]}}], "responses": {"200": {"description": "Sample response format"}}}},
            "/api/sandbox/verify_provenance": {"get": {"summary": "Mock verify_provenance (no credits)", "tags": ["Sandbox"], "responses": {"200": {"description": "Sample response format"}}}},
            "/api/sandbox/search_artworks": {"get": {"summary": "Mock search_artworks (no credits)", "tags": ["Sandbox"], "responses": {"200": {"description": "Sample response format"}}}},
            **({"/api/sandbox/full_pipeline": {"get": {"summary": "Mock full_pipeline (no credits)", "tags": ["Sandbox"], "parameters": [{"name": "prompt", "in": "query", "schema": {"type": "string"}}], "responses": {"200": {"description": "Sample response format"}}}}} if _is_tool_enabled("full_pipeline") else {}),
            "/api/sandbox/compliance_manifest": {"get": {"summary": "Mock compliance_manifest (no credits)", "tags": ["Sandbox"], "responses": {"200": {"description": "Sample compliance response"}}}},
            "/api/gallery/post": {"get": {"summary": "Post artwork to gallery (GET-friendly)", "tags": ["Social"], "parameters": [{"name": "name", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "title", "in": "query", "required": True, "schema": {"type": "string"}}, {"name": "image_url", "in": "query", "required": True, "schema": {"type": "string"}}], "responses": {"200": {"description": "Artwork posted"}}}},
            "/api/gallery/feed": {"get": {"summary": "Browse the artwork gallery", "tags": ["Social"], "responses": {"200": {"description": "Gallery artworks"}}}},
            "/api/webhooks/register": {"post": {"summary": "Register webhook for async pipeline notifications (coming soon)", "tags": ["Webhooks"], "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"url": {"type": "string"}, "events": {"type": "array", "items": {"type": "string"}}}}}}}, "responses": {"200": {"description": "Webhook registration acknowledged"}}}},
            "/api/create-payment-intent": {"post": {"summary": "Create Stripe payment intent for per-call payment", "tags": ["Payment"], "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"tool_name": {"type": "string"}}, "required": ["tool_name"]}}}}, "responses": {"200": {"description": "Stripe client_secret for payment"}}}},
            "/api/credits": {"get": {"summary": "GCX credit packs and pricing", "tags": ["Payment"], "responses": {"200": {"description": "Available credit packs with volume discounts"}}}},
            **tool_paths,
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "description": "GCX credits — use wallet address as bearer token (register at POST /api/wallet/register for 10 free GCX)"},
                **({
                    "x402": {"type": "apiKey", "in": "header", "name": "X-PAYMENT", "description": "x402 USDC micropayment on Base L2 — no account needed. Send EIP-712 signed permit. Server returns 402 with exact instructions on first call."},
                } if config.tool_profile == "full" else {}),
                "stripePayment": {"type": "apiKey", "in": "header", "name": "X-Stripe-Payment-Intent", "description": "Stripe per-call — first POST /api/create-payment-intent, then include payment intent ID. $0.50 minimum per transaction."},
            }
        },
        "tags": [
            {"name": "Discovery", "description": "Service discovery and documentation"},
            {"name": "MCP", "description": "Model Context Protocol transport"},
            {"name": "Tools", "description": "Creative AI tool calls (require auth)"},
            {"name": "Account", "description": "Wallet and credit management"},
            {"name": "Social", "description": "Registry, Cafe, and community features"},
            {"name": "Sandbox", "description": "Mock endpoints for testing (no credits needed)"},
            {"name": "Payment", "description": "Stripe, GCX credits, and payment management"},
            {"name": "Webhooks", "description": "Async notification callbacks (coming soon)"},
        ],
    }
    return jsonify(spec)


@app.route("/pricing.json")
def pricing_json():
    """Machine-readable pricing sheet for MCP directory crawlers and agents."""
    from .config import PRICING, GCX_PACKS, SUBSCRIPTION_TIERS, AGENT_VOLUME_TIERS, GCX_BASE_RATE
    from .mcp_tools import _is_tool_enabled

    tools = {}
    for name, p in PRICING.items():
        if not _is_tool_enabled(name):
            continue
        tools[name] = {
            "gcx_credits": p.gcx_credits,
            "usd": round(p.gcx_credits * GCX_BASE_RATE, 2),
            "free": p.gcx_credits == 0,
        }

    payment_methods = {
        "gcx_credits": {
            "description": "Pre-purchased credits with volume discounts",
            "welcome_bonus": 10,
        },
        "stripe": {
            "description": "Credit card via Stripe (packs and subscriptions)",
        },
    }
    if config.tool_profile == "full":
        payment_methods["x402"] = {
            "chain": "base",
            "token": "USDC",
            "wallet": config.x402_wallet,
            "description": "Pay-per-call via x402 protocol (no account needed)",
        }

    return jsonify({
        "schema": "studiomcphub-pricing-v1",
        "currency": "USD",
        "gcx_base_rate": GCX_BASE_RATE,
        "gcx_per_dollar": int(1 / GCX_BASE_RATE),
        "tools": tools,
        "packs": GCX_PACKS,
        "subscriptions": SUBSCRIPTION_TIERS,
        "volume_discounts": AGENT_VOLUME_TIERS,
        "payment_methods": payment_methods,
        "free_tools": [name for name, p in PRICING.items() if p.gcx_credits == 0 and _is_tool_enabled(name)],
        "links": {
            "mcp_endpoint": "https://studiomcphub.com/mcp",
            "documentation": "https://studiomcphub.com/llms.txt",
            "mcp_card": "https://studiomcphub.com/.well-known/mcp.json",
        },
    })


# ---------------------------------------------------------------------------
# Webhook registration (planned — stub for agent discovery)
# ---------------------------------------------------------------------------

@app.route("/api/webhooks/register", methods=["POST"])
def register_webhook():
    """Register a callback URL for async pipeline progress notifications.

    POST /api/webhooks/register
    Body: {"url": "https://your-agent.com/callback", "events": ["pipeline.complete"]}

    Events (planned):
      - pipeline.stage_complete: Fired after each stage (generate, upscale, enrich, etc.)
      - pipeline.complete: Fired when full pipeline finishes successfully
      - pipeline.failed: Fired if pipeline encounters an error

    Status: Coming soon. This endpoint currently returns the planned spec.
    """
    body = request.get_json(silent=True) or {}
    callback_url = body.get("url", "")
    events = body.get("events", ["pipeline.complete"])

    return jsonify({
        "status": "planned",
        "message": "Webhook support is coming soon. Your registration has been noted.",
        "registered_url": callback_url,
        "events": events,
        "available_events": [
            "pipeline.stage_complete",
            "pipeline.complete",
            "pipeline.failed",
        ],
        "note": "Until webhooks are live, poll GET /api/tools/check_balance or the admin dashboard for status.",
    })


# ---------------------------------------------------------------------------
# MCP Streamable HTTP transport
# ---------------------------------------------------------------------------

_mcp_rate = limiter.limit("200/minute") if limiter else lambda f: f

@app.route("/mcp", methods=["POST", "GET", "DELETE", "HEAD"])
@_mcp_rate
def mcp_endpoint():
    """MCP Streamable HTTP endpoint.

    POST: Send MCP JSON-RPC messages (initialize, tools/list, tools/call).
    GET:  SSE stream for server-initiated notifications (long-poll).
    DELETE: Terminate an MCP session.
    """
    import asyncio

    session_id = request.headers.get("Mcp-Session-Id")

    if request.method == "POST":
        body = request.get_data(as_text=True)
        if not body:
            return jsonify({"error": "Empty request body"}), 400

        try:
            msg = json.loads(body)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON"}), 400

        # Initialize: create new session
        if msg.get("method") == "initialize":
            sid = str(uuid.uuid4())
            server = create_mcp_server(check_payment)
            _mcp_sessions[sid] = server

            # Return MCP initialize response with session ID
            return Response(
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {
                            "tools": {"listChanged": False},
                        },
                        "serverInfo": {
                            "name": config.server_name,
                            "version": config.server_version,
                        },
                    },
                }),
                status=200,
                content_type="application/json",
                headers={"Mcp-Session-Id": sid},
            )

        # Notifications have no id. ACK even if initialize landed on
        # another gunicorn worker (sessions are in-process only).
        if "id" not in msg:
            return Response("", status=202)

        # tools/list and ping are stateless. Directory health checks
        # (Glama hourly, Smithery, Inspector) initialize then list tools.
        # Two gunicorn workers + no Cloud Run session affinity means the
        # follow-up often hits a process that never saw initialize, which
        # used to 400 "Invalid or missing Mcp-Session-Id".
        if msg.get("method") == "ping":
            return jsonify({"jsonrpc": "2.0", "id": msg.get("id"), "result": {}})

        if msg.get("method") == "tools/list":
            if session_id and session_id in _mcp_sessions:
                server = _mcp_sessions[session_id]
            else:
                server = create_mcp_server(check_payment)
            handler = server.request_handlers.get(ListToolsRequest)
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(handler(ListToolsRequest(
                    method="tools/list",
                    params=None,
                )))
            finally:
                loop.close()
            return Response(
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result,
                }),
                status=200,
                content_type="application/json",
                headers={"Mcp-Session-Id": session_id} if session_id else {},
            )

        # tools/call still needs a live session on this worker.
        if not session_id or session_id not in _mcp_sessions:
            return jsonify({"error": "Invalid or missing Mcp-Session-Id"}), 400

        server = _mcp_sessions[session_id]

        # tools/call
        if msg.get("method") == "tools/call":
            call_params = msg.get("params", {})
            tool_name = call_params.get("name", "")
            arguments = call_params.get("arguments", {})

            # Payment gate: check before dispatching
            price = PRICING.get(tool_name)
            if price and price.gcx_credits > 0:
                payment = check_payment(tool_name)
                if payment is None:
                    return require_payment(tool_name)

            handler = server.request_handlers.get(CallToolRequest)
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(handler(CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(name=tool_name, arguments=arguments),
                )))
            finally:
                loop.close()

            return Response(
                json.dumps({
                    "jsonrpc": "2.0",
                    "id": msg.get("id"),
                    "result": result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result,
                }),
                status=200,
                content_type="application/json",
                headers={"Mcp-Session-Id": session_id},
            )

        return jsonify({
            "jsonrpc": "2.0",
            "id": msg.get("id"),
            "error": {"code": -32601, "message": f"Method not found: {msg.get('method')}"},
        }), 200

    elif request.method == "GET":
        # No session = browser visit — show a friendly landing page
        if not session_id or session_id not in _mcp_sessions:
            accept = request.headers.get("Accept", "")
            if "text/html" in accept or not session_id:
                return Response(
                    '<!DOCTYPE html>\n'
                    '<html lang="en"><head>\n'
                    '<meta charset="utf-8">\n'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
                    '<title>StudioMCPHub — MCP Endpoint</title>\n'
                    '<style>\n'
                    'body{font-family:system-ui,sans-serif;max-width:640px;margin:60px auto;padding:0 20px;'
                    'background:#0a0a0a;color:#e0e0e0;line-height:1.6}\n'
                    'h1{color:#f5c542;margin-bottom:4px}\n'
                    'code{background:#1a1a2e;padding:2px 6px;border-radius:4px;font-size:0.9em}\n'
                    'pre{background:#1a1a2e;padding:16px;border-radius:8px;overflow-x:auto;border:1px solid #333}\n'
                    'a{color:#f5c542}\n'
                    '.badge{display:inline-block;background:#f5c542;color:#0a0a0a;padding:2px 8px;'
                    'border-radius:4px;font-size:0.8em;font-weight:600;margin-left:8px}\n'
                    '</style>\n'
                    '</head><body>\n'
                    '<h1>StudioMCPHub<span class="badge">MCP</span></h1>\n'
                    '<p>This is a <strong>Model Context Protocol</strong> endpoint. '
                    'It speaks JSON-RPC over HTTP, not HTML.</p>\n'
                    '<h2>Connect your AI client</h2>\n'
                    '<p>Add this to your MCP client config (Claude Code, Cursor, VS Code, etc.):</p>\n'
                    '<pre><code>{\n'
                    '  "mcpServers": {\n'
                    '    "studiomcphub": {\n'
                    '      "url": "https://studiomcphub.com/mcp"\n'
                    '    }\n'
                    '  }\n'
                    '}</code></pre>\n'
                    '<h2>What you get</h2>\n'
                    '<p><strong>32 tools</strong> (18 free) — background removal, color palettes, '
                    'mockups, CMYK conversion, vectorization, watermarking, AI enrichment, '
                    '4x ESRGAN upscaling, and 2M+ museum artwork search.</p>\n'
                    '<h2>Links</h2>\n'
                    '<ul>\n'
                    '<li><a href="/.well-known/mcp.json">MCP Server Card</a></li>\n'
                    '<li><a href="/llms.txt">LLMs.txt</a></li>\n'
                    '<li><a href="/pricing">Pricing</a></li>\n'
                    '<li><a href="/health">Health Check</a></li>\n'
                    '<li><a href="https://github.com/codex-curator/studiomcphub">GitHub</a></li>\n'
                    '<li><a href="https://studiomcphub.com">Homepage</a></li>\n'
                    '</ul>\n'
                    '<p style="color:#666;font-size:0.85em;margin-top:40px">'
                    'Metavolve Labs, Inc. | Streamable HTTP transport</p>\n'
                    '</body></html>\n',
                    status=200,
                    content_type="text/html",
                )
        # SSE endpoint for server-initiated messages
        return Response("", status=200, content_type="text/event-stream")

    elif request.method == "HEAD":
        # MCP client probes — return 200 with empty body
        return Response("", status=200, content_type="text/event-stream")

    elif request.method == "DELETE":
        # Terminate session
        if session_id and session_id in _mcp_sessions:
            del _mcp_sessions[session_id]
        return Response("", status=200)

    return jsonify({"error": "Method not allowed"}), 405


# ---------------------------------------------------------------------------
# Health & status
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": config.server_name,
        "version": config.server_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/pricing")
def pricing():
    """Return pricing table for all tools."""
    from .mcp_tools import _is_tool_enabled
    return jsonify({
        "currency": "USD",
        "gcx_rate": {"dollars": 1, "gcx": GCX_PER_DOLLAR},
        "gcx_bundles": [
            {"amount_usd": 5, "gcx": 100},
            {"amount_usd": 20, "gcx": 440},   # 10% bonus
            {"amount_usd": 50, "gcx": 1200},  # 20% bonus
        ],
        "tools": {
            name: {
                "stripe_usd": p.stripe_cents / 100,
                "gcx_credits": p.gcx_credits,
            }
            for name, p in PRICING.items() if _is_tool_enabled(name)
        },
    })


# ---------------------------------------------------------------------------
# Payment gate middleware
# ---------------------------------------------------------------------------

def check_payment(tool_name: str) -> tuple[str, dict] | None:
    """Check if the request includes valid payment.

    Returns (method, details) if paid, or None.
    Raises 402 response if payment required but not provided.
    """
    price = PRICING.get(tool_name)
    if not price or price.x402_cents == 0:
        return ("free", {})

    # Dynamic pricing: enrich_metadata standard tier costs 1 GCX instead of 2
    body = request.get_json(silent=True) or {}
    if tool_name == "enrich_metadata" and body.get("tier") == "standard":
        price = ToolPricing(gcx_credits=1)

    # Check x402 header
    x_payment = request.headers.get("X-PAYMENT")
    if x_payment:
        from ..payment.x402 import verify_payment, extract_wallet
        from ..payment.agent_tiers import apply_discount
        base_usd = price.x402_cents / 100
        wallet = extract_wallet(x_payment)
        if wallet:
            discounted_usd, tier_info = apply_discount(wallet, base_usd)
        else:
            discounted_usd, tier_info = base_usd, {"label": "Standard", "discount_pct": 0}
        verified_usd = None
        if verify_payment(x_payment, discounted_usd):
            verified_usd = discounted_usd
        elif discounted_usd != base_usd and verify_payment(x_payment, base_usd):
            verified_usd = base_usd

        if verified_usd is not None:
            # Post-payment hooks (fire-and-forget)
            if wallet:
                try:
                    from ..payment.agent_tiers import record_spend
                    record_spend(wallet, verified_usd, tool_name)
                except Exception as e:
                    logger.warning(f"record_spend failed: {e}")
                try:
                    from ..payment.gcx_credits import ensure_account
                    ensure_account(wallet)
                except Exception as e:
                    logger.warning(f"ensure_account failed: {e}")
                try:
                    from ..payment.loyalty import earn_loyalty
                    earn_loyalty(wallet, price.gcx_credits, tool_name)
                except Exception as e:
                    logger.warning(f"earn_loyalty failed: {e}")
            return ("x402", {"header": x_payment, "wallet": wallet, "tier": tier_info, "amount_usd": verified_usd})

        logger.warning(f"x402 payment verification failed for {tool_name}")
        return None

    # Check API key / GCX credit (Bearer token = wallet or OAuth JWT)
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        # Resolve OAuth JWT to wallet address (no-op for raw wallet addresses)
        resolved = _resolve_bearer(token) or token
        from ..payment.gcx_credits import deduct_credits
        if deduct_credits(user_id=resolved, amount=price.gcx_credits, tool_name=tool_name):
            # Post-payment hook: loyalty credit-back (fire-and-forget)
            try:
                from ..payment.loyalty import earn_loyalty
                earn_loyalty(resolved, price.gcx_credits, tool_name)
            except Exception as e:
                logger.warning(f"earn_loyalty failed: {e}")
            return ("gcx", {"token": resolved, "gcx_deducted": price.gcx_credits})
        logger.warning(f"GCX deduction failed for {tool_name} (user={resolved})")
        return None

    # Check Stripe payment intent
    stripe_pi = request.headers.get("X-Stripe-Payment-Intent")
    if stripe_pi:
        from ..payment.stripe_pay import verify_payment_intent
        if verify_payment_intent(stripe_pi):
            return ("stripe", {"payment_intent": stripe_pi})
        logger.warning(f"Stripe PI verification failed for {tool_name}")
        return None

    # No payment found — return 402
    return None


def require_payment(tool_name: str):
    """Return 402 Payment Required response with instructions."""
    from .config import AGENT_VOLUME_TIERS
    price = PRICING[tool_name]
    base_usd = price.x402_cents / 100
    return jsonify({
        "error": "payment_required",
        "tool": tool_name,
        "amount_usd": base_usd,
        "payment_options": {
            "1_gcx_credits": {
                "method": "Bearer token",
                "credits_required": price.gcx_credits,
                "header": "Authorization: Bearer 0xYOUR_WALLET",
                "free_trial": "POST /api/wallet/register → 10 free GCX ($1 value)",
                "buy_more": "GET /api/credits",
            },
            "2_x402_usdc": {
                "method": "USDC on Base L2 (no account needed)",
                "amount_usd": base_usd,
                "wallet": config.x402_wallet,
                "chain": "base",
                "token": "USDC",
                "header": "X-PAYMENT: <signed-EIP712-permit>",
            },
            "3_stripe": {
                "method": "Credit card via Stripe",
                "amount_usd": price.stripe_cents / 100,
                "step_1": f"POST /api/create-payment-intent {{\"tool_name\": \"{tool_name}\"}}",
                "step_2": "Complete payment with client_secret",
                "step_3": f"Re-call tool with header: X-Stripe-Payment-Intent: pi_xxx",
                "note": "Stripe minimum $0.50 per transaction — for small tools, GCX credits or x402 are better value.",
            },
        },
        "volume_discounts": {
            "check_url": "https://studiomcphub.com/api/agent/tier/{wallet_address}",
            "tiers": [
                {"label": t["label"], "min_spend_usd": t["min_spend_usd"], "discount_pct": t["discount_pct"]}
                for t in AGENT_VOLUME_TIERS
            ],
        },
    }), 402


# ---------------------------------------------------------------------------
# MCP Tool endpoints (REST wrappers — the MCP Streamable HTTP handler
# delegates to these)
# ---------------------------------------------------------------------------

# Free tools that get tiered rate limits to prevent exploitation.
_FREE_TOOLS = {
    name for name, p in PRICING.items() if p.gcx_credits == 0
}


def _tool_rate_key():
    """Rate-limit key: wallet (if present) or IP address."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 10:
        wallet = _resolve_bearer(auth[7:]) or auth[7:]
        return f"wallet:{wallet}"
    return f"ip:{get_remote_address()}"


def _dynamic_tool_limit():
    """Return rate limit string based on tool type and auth status.

    Tiered rate limiting:
      - Anonymous + free tool:   10/hour  per IP     (prevent enterprise abuse)
      - Registered + free tool:  60/hour  per wallet  (fair use for creators)
      - Paid tools:             100/minute per wallet  (paying customers, generous)
    """
    tool_name = request.view_args.get("tool_name", "")
    auth = request.headers.get("Authorization", "")
    has_wallet = auth.startswith("Bearer ") and len(auth) > 10

    if tool_name in _FREE_TOOLS:
        return "60/hour" if has_wallet else "10/hour"
    return "100/minute"


_tool_rate = (
    limiter.limit(_dynamic_tool_limit, key_func=_tool_rate_key)
    if limiter else lambda f: f
)


@app.route("/api/tools/<tool_name>", methods=["POST"])
@_tool_rate
def execute_tool(tool_name: str):
    """Generic tool execution endpoint with payment gating."""
    from .mcp_tools import _is_tool_enabled
    if tool_name not in PRICING or not _is_tool_enabled(tool_name):
        return jsonify({"error": f"Unknown tool: {tool_name}"}), 404

    # Input validation: tools that require 'image' param
    _image_required = {
        "upscale_image", "enrich_metadata", "infuse_metadata",
        "register_hash", "store_permanent", "mint_nft", "verify_provenance",
        "extract_palette", "remove_background", "mockup_image",
        "convert_color_profile", "print_ready", "vectorize_image",
        "watermark_embed", "watermark_detect", "resize_image",
    }
    params_preview = request.get_json(silent=True) or {}
    if tool_name in _image_required and "image" not in params_preview:
        return jsonify({
            "error": f"Missing required parameter 'image' (base64-encoded image data)",
            "tool": tool_name,
        }), 400
    if tool_name in ("generate_image", "generate_image_nano") and "prompt" not in params_preview:
        return jsonify({
            "error": "Missing required parameter 'prompt'",
            "tool": tool_name,
        }), 400
    if tool_name == "save_asset":
        for req_field in ("wallet", "key", "data"):
            if req_field not in params_preview:
                return jsonify({
                    "error": f"Missing required parameter '{req_field}'",
                    "tool": tool_name,
                }), 400
    if tool_name == "search_artworks" and "query" not in params_preview:
        return jsonify({
            "error": "Missing required parameter 'query'",
            "tool": tool_name,
        }), 400
    if tool_name == "get_tool_schema" and "tool_name" not in params_preview:
        return jsonify({
            "error": "Missing required parameter 'tool_name'",
            "tool": tool_name,
            "hint": "Use search_tools to discover available tool names.",
        }), 400

    payment = check_payment(tool_name)
    if payment is None:
        return require_payment(tool_name)

    method, details = payment
    params = request.get_json(silent=True) or {}

    logger.info(f"Executing {tool_name} | payment={method} | params={list(params.keys())}")

    # Import and dispatch to tool handler
    try:
        from ..tools import dispatch_tool
        result = dispatch_tool(tool_name, params)
        return jsonify({
            "tool": tool_name,
            "status": "success",
            "payment_method": method,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except ValueError as e:
        error_msg = str(e).lower()
        # Return 400 for validation errors, 404 for not-found
        status = 404 if "not found" in error_msg or "not exist" in error_msg else 400
        logger.warning(f"Tool {tool_name} ValueError: {e}")
        # Refund GCX on validation/not-found errors too
        if method == "gcx":
            try:
                from ..payment.gcx_credits import refund_credits
                token = details.get("token", "")
                gcx_amount = details.get("gcx_deducted", 0)
                if token and gcx_amount > 0:
                    refund_credits(user_id=token, amount=gcx_amount, tool_name=tool_name)
                    logger.info(f"Auto-refunded {gcx_amount} GCX to {token} for failed {tool_name}")
            except Exception as refund_err:
                logger.error(f"Refund failed for {tool_name}: {refund_err}")
        return jsonify({
            "tool": tool_name,
            "status": "error",
            "error": str(e),
            "refunded": method == "gcx",
        }), status
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        # Auto-refund GCX credits on tool failure — service not rendered
        if method == "gcx":
            try:
                from ..payment.gcx_credits import refund_credits
                token = details.get("token", "")
                gcx_amount = details.get("gcx_deducted", 0)
                if token and gcx_amount > 0:
                    refund_credits(user_id=token, amount=gcx_amount, tool_name=tool_name)
                    logger.info(f"Auto-refunded {gcx_amount} GCX to {token} for failed {tool_name}")
            except Exception as refund_err:
                logger.error(f"Refund failed for {tool_name}: {refund_err}")
        return jsonify({
            "tool": tool_name,
            "status": "error",
            "error": str(e),
            "refunded": method == "gcx",
        }), 500


# ---------------------------------------------------------------------------
# Stripe per-call payment (pay-as-you-go, no credits needed)
# ---------------------------------------------------------------------------

@app.route("/api/create-payment-intent", methods=["POST"])
def create_stripe_intent():
    """Create a Stripe PaymentIntent for a single tool call.

    Agent flow:
      1. POST /api/create-payment-intent {"tool_name": "generate_image"}
      2. Complete payment using client_secret (Stripe.js or server-side)
      3. Re-call the tool with header: X-Stripe-Payment-Intent: pi_xxx

    Body: {"tool_name": "generate_image", "customer_id": "cus_xxx" (optional)}
    Returns: {"client_secret": "pi_xxx_secret_xxx", "payment_intent_id": "pi_xxx", "amount_usd": 0.20}
    """
    data = request.get_json(silent=True) or {}
    tool_name = data.get("tool_name", "")

    if not tool_name or tool_name not in PRICING:
        return jsonify({"error": f"Unknown tool: {tool_name}", "available": list(PRICING.keys())}), 400

    price = PRICING[tool_name]
    if price.stripe_cents == 0:
        return jsonify({"error": f"{tool_name} is free — no payment needed", "tool": tool_name}), 400

    # Dynamic pricing for tiered tools
    amount_cents = price.stripe_cents
    if tool_name == "enrich_metadata" and data.get("tier") == "standard":
        amount_cents = 10  # $0.10

    # Minimum Stripe charge is $0.50 — bundle if below threshold
    if amount_cents < 50:
        return jsonify({
            "error": "amount_below_minimum",
            "message": f"Stripe requires minimum $0.50 per transaction. This tool costs ${amount_cents/100:.2f}. Consider purchasing GCX credits instead — register your wallet at POST /api/wallet/register for 10 free GCX, or buy packs at /credits.",
            "tool": tool_name,
            "amount_usd": amount_cents / 100,
            "alternatives": {
                "gcx_credits": "POST /api/wallet/register (10 free GCX, then Bearer token auth)",
                "x402": f"Pay ${amount_cents/100:.2f} USDC on Base L2 (no minimum)",
                "credit_packs": "Buy GCX packs via Stripe at /credits ($5 minimum)",
            },
        }), 400

    try:
        from ..payment.stripe_pay import create_payment_intent
        result = create_payment_intent(
            tool_name=tool_name,
            amount_cents=amount_cents,
            customer_id=data.get("customer_id"),
        )
        return jsonify({
            "tool": tool_name,
            "amount_usd": amount_cents / 100,
            "amount_cents": amount_cents,
            **result,
            "next_step": f"Complete payment, then call POST /api/tools/{tool_name} with header X-Stripe-Payment-Intent: {result['payment_intent_id']}",
        })
    except Exception as e:
        logger.error(f"Stripe intent creation failed: {e}")
        return jsonify({"error": f"Payment creation failed: {str(e)}"}), 500


@app.route("/api/credits", methods=["GET"])
def credits_info():
    """GCX credit purchase information and pricing."""
    from .config import GCX_PACKS, GCX_BASE_RATE
    return jsonify({
        "description": "Pre-purchase GCX credits for volume discounts. Credits never expire.",
        "free_trial": {
            "amount": 10,
            "value_usd": 1.00,
            "how": "POST /api/wallet/register with your EVM wallet address",
        },
        "packs": GCX_PACKS,
        "base_rate": f"${GCX_BASE_RATE} per GCX",
        "payment": "Stripe checkout (credit card, Apple Pay, Google Pay)",
        "loyalty": "Every paid tool call earns 5% credit-back automatically",
    })


# ---------------------------------------------------------------------------
# Support & Feedback
# ---------------------------------------------------------------------------

@app.route("/api/support/tickets", methods=["POST"])
def create_support_ticket():
    """Create a support ticket (bug, credit issue, feedback, etc.)."""
    data = request.get_json(silent=True) or {}

    required = ["type", "subject", "description"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        from ..api.support import create_ticket, TICKET_TYPES
        if data["type"] not in TICKET_TYPES:
            return jsonify({"error": f"Invalid type. Must be: {TICKET_TYPES}"}), 400

        result = create_ticket(
            ticket_type=data["type"],
            subject=data["subject"],
            description=data["description"],
            wallet_address=data.get("wallet"),
            email=data.get("email"),
            tool_name=data.get("tool"),
            tx_hash=data.get("tx_hash"),
        )
        return jsonify(result), 201
    except Exception as e:
        logger.error(f"Ticket creation failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/support/tickets/<ticket_id>", methods=["GET"])
def get_support_ticket(ticket_id: str):
    """Get a ticket by ID."""
    from ..api.support import get_ticket
    ticket = get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    return jsonify(ticket)


# ---------------------------------------------------------------------------
# Wallet registration & account management
# ---------------------------------------------------------------------------

WELCOME_BONUS_GCX = 10  # Free trial credits for new wallets ($1.00 value)

@app.route("/api/wallet/register", methods=["POST"])
def register_wallet():
    """Register a new wallet and receive 10 GCX welcome bonus.

    Body: {"wallet": "0x..."} or just the wallet in Authorization header.
    Returns account info with balance, or existing account if already registered.
    """
    data = request.get_json(silent=True) or {}
    wallet = data.get("wallet", "").strip()

    if not wallet:
        # Also accept from Authorization header (agent flow)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            wallet = auth[7:]

    if not wallet:
        return jsonify({"error": "Missing 'wallet' parameter (EVM address)"}), 400

    # Basic format check (0x + 40 hex chars)
    wallet_lower = wallet.lower()
    if not (wallet_lower.startswith("0x") and len(wallet_lower) == 42):
        return jsonify({"error": "Invalid wallet address format. Expected 0x + 40 hex characters."}), 400

    try:
        int(wallet_lower[2:], 16)
    except ValueError:
        return jsonify({"error": "Invalid wallet address: non-hex characters"}), 400

    from ..payment.gcx_credits import _get_db, add_credits

    db = _get_db()
    ref = db.collection("gcx_accounts").document(wallet_lower)

    # Check if account already exists
    existing = ref.get()
    if existing.exists:
        account = existing.to_dict()
        # Convert timestamps for JSON
        for k, v in account.items():
            if hasattr(v, "isoformat"):
                account[k] = v.isoformat()
        return jsonify({
            "status": "existing",
            "wallet": wallet_lower,
            "balance": account.get("balance", 0),
            "tier": account.get("tier", "standard"),
            "message": "Wallet already registered. Use your balance to call tools.",
        })

    # Create new account with welcome bonus
    from datetime import datetime, timezone as tz
    ref.set({
        "balance": WELCOME_BONUS_GCX,
        "created_at": datetime.now(tz.utc),
        "last_updated": datetime.now(tz.utc),
        "tier": "standard",
        "source": "wallet_registration",
        "welcome_bonus": WELCOME_BONUS_GCX,
    })

    # Log the welcome bonus as a transaction
    db.collection("gcx_transactions").add({
        "user_id": wallet_lower,
        "type": "credit",
        "amount": WELCOME_BONUS_GCX,
        "reason": "welcome_bonus",
        "balance_after": WELCOME_BONUS_GCX,
        "timestamp": datetime.now(tz.utc),
    })

    logger.info(f"New wallet registered: {wallet_lower} | bonus={WELCOME_BONUS_GCX} GCX")

    return jsonify({
        "status": "created",
        "wallet": wallet_lower,
        "balance": WELCOME_BONUS_GCX,
        "tier": "standard",
        "message": f"Welcome to StudioMCPHub! You've received {WELCOME_BONUS_GCX} GCX credits ($5.00 value) to try our tools.",
        "how_to_use": {
            "step_1": "Include 'Authorization: Bearer <your-wallet-address>' in your requests",
            "step_2": "Call any tool — credits are deducted automatically",
            "example": f"curl -X POST https://studiomcphub.com/api/tools/generate_image -H 'Authorization: Bearer {wallet_lower}' -H 'Content-Type: application/json' -d '{{\"prompt\": \"a serene mountain lake at sunrise\"}}'",
        },
        "pricing_url": "https://studiomcphub.com/pricing",
        "tools_url": "https://studiomcphub.com/.well-known/mcp.json",
    }), 201


@app.route("/api/wallet/<wallet_address>", methods=["GET"])
def wallet_info(wallet_address: str):
    """Get full account info for a wallet: GCX balance, tier, loyalty."""
    wallet_lower = wallet_address.lower()

    from ..payment.gcx_credits import get_balance
    from ..payment.loyalty import get_loyalty_balance
    from ..payment.agent_tiers import get_tier

    balance = get_balance(wallet_lower)
    loyalty = get_loyalty_balance(wallet_lower)
    tier = get_tier(wallet_lower)

    if balance == 0 and loyalty["lifetime_earned"] == 0.0 and tier["spend_30d"] == 0.0:
        # Check if account exists at all
        from ..payment.gcx_credits import _get_db
        doc = _get_db().collection("gcx_accounts").document(wallet_lower).get()
        if not doc.exists:
            return jsonify({
                "error": "Wallet not registered",
                "register_url": "https://studiomcphub.com/api/wallet/register",
                "message": "Register your wallet to receive 10 free GCX credits.",
            }), 404

    return jsonify({
        "wallet": wallet_lower,
        "gcx_balance": balance,
        "loyalty": loyalty,
        "tier": tier,
    })


# ---------------------------------------------------------------------------
# Loyalty balance (legacy — kept for backward compatibility)
# ---------------------------------------------------------------------------

@app.route("/api/loyalty/<wallet_address>", methods=["GET"])
def loyalty_balance(wallet_address: str):
    """Get loyalty credit balance for a wallet."""
    from ..payment.loyalty import get_loyalty_balance
    return jsonify(get_loyalty_balance(wallet_address))


@app.route("/api/agent/tier/<wallet_address>", methods=["GET"])
def agent_tier(wallet_address: str):
    """Get volume discount tier for a wallet."""
    from ..payment.agent_tiers import get_tier
    return jsonify(get_tier(wallet_address))


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------

@app.route("/privacy")
def privacy_page():
    """Privacy Policy."""
    return send_from_directory(_SITE_DIR, "privacy.html")


@app.route("/terms")
def terms_page():
    """Terms of Service."""
    return send_from_directory(_SITE_DIR, "terms.html")


@app.route("/support")
def support_page():
    """Support & contact page."""
    return send_from_directory(_SITE_DIR, "support.html")


@app.route("/guide")
def guide_page():
    """Bot & Agent how-to guide."""
    return send_from_directory(_SITE_DIR, "guide.html")


@app.route("/")
def index():
    """Serve landing page for humans; return MCP card for agents."""
    accept = request.headers.get("Accept", "")
    if "application/json" in accept or "text/plain" in accept:
        return mcp_server_card()
    try:
        return send_from_directory(_SITE_DIR, "index.html")
    except Exception:
        return mcp_server_card()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logger.info(f"StudioMCPHub v{config.server_version} starting on {config.host}:{config.port}")
    app.run(host=config.host, port=config.port, debug=config.debug)


if __name__ == "__main__":
    main()
