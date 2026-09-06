"""OAuth 2.1 Blueprint for StudioMCPHub.

Implements the MCP OAuth 2.1 specification (Nov 2025):
  - Authorization Code flow with PKCE (S256)
  - Protected Resource Metadata (RFC 9728)
  - Authorization Server Metadata (RFC 8414)
  - Dynamic Client Registration (RFC 7591)
  - Refresh token rotation

All endpoints are registered at the app root (no url_prefix) so that
/.well-known/* paths work correctly.
"""

import logging
import secrets
from urllib.parse import urlencode, urlparse

from flask import Blueprint, request, jsonify, render_template, redirect, session

from .clients import get_client, validate_redirect_uri, register_client, ensure_trusted_clients
from .consent import (
    store_auth_request,
    get_auth_request,
    create_auth_code,
    exchange_auth_code,
    refresh_tokens,
)

logger = logging.getLogger("studiomcphub.auth")

oauth_bp = Blueprint("oauth", __name__)

# Scopes supported by this server
SCOPES_SUPPORTED = ["tools:free", "tools:paid", "account:read"]

_trusted_clients_seeded = False


def _ensure_seeded():
    """Seed trusted clients once on first request."""
    global _trusted_clients_seeded
    if not _trusted_clients_seeded:
        try:
            ensure_trusted_clients()
        except Exception as e:
            logger.warning(f"Failed to seed trusted clients: {e}")
        _trusted_clients_seeded = True


def _get_issuer() -> str:
    from ..mcp_server.config import config
    return getattr(config, "oauth_issuer", "https://studiomcphub.com")


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------

def _protected_resource_body(resource: str) -> dict:
    issuer = _get_issuer()
    return {
        "resource": resource,
        "authorization_servers": [issuer],
        "scopes_supported": SCOPES_SUPPORTED,
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{issuer}/llms.txt",
    }


@oauth_bp.route("/.well-known/oauth-protected-resource")
def protected_resource_metadata():
    """RFC 9728 — Protected Resource Metadata."""
    return jsonify(_protected_resource_body(_get_issuer()))


@oauth_bp.route("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata_mcp():
    """Path-appended RFC 9728 metadata for the /mcp resource.

    MCP clients (Glama health checks included) fetch this after seeing
    OAuth advertised. A 405 here looks like a dead connector.
    """
    return jsonify(_protected_resource_body(f"{_get_issuer()}/mcp"))


@oauth_bp.route("/.well-known/oauth-authorization-server")
def authorization_server_metadata():
    """RFC 8414 — Authorization Server Metadata."""
    issuer = _get_issuer()
    return jsonify({
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "registration_endpoint": f"{issuer}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": SCOPES_SUPPORTED,
    })


# ---------------------------------------------------------------------------
# Authorization endpoint
# ---------------------------------------------------------------------------

@oauth_bp.route("/authorize")
def authorize():
    """OAuth 2.1 Authorization endpoint — renders consent page."""
    _ensure_seeded()

    # Required parameters
    response_type = request.args.get("response_type", "")
    client_id = request.args.get("client_id", "")
    redirect_uri = request.args.get("redirect_uri", "")
    state = request.args.get("state", "")
    code_challenge = request.args.get("code_challenge", "")
    code_challenge_method = request.args.get("code_challenge_method", "")
    scope = request.args.get("scope", "tools:free tools:paid")
    resource = request.args.get("resource", "")

    # Validate response_type
    if response_type != "code":
        return _render_error(
            "unsupported_response_type",
            "Only response_type=code is supported.",
        )

    # Validate PKCE
    if not code_challenge or code_challenge_method != "S256":
        return _render_error(
            "invalid_request",
            "PKCE is required. Include code_challenge with code_challenge_method=S256.",
        )

    # Validate client
    client = get_client(client_id)
    if not client:
        return _render_error("invalid_client", f"Client '{client_id}' is not registered.")

    # Validate redirect_uri
    if not redirect_uri:
        return _render_error("invalid_request", "redirect_uri is required.")
    if not validate_redirect_uri(client, redirect_uri):
        return _render_error(
            "invalid_request",
            f"redirect_uri '{redirect_uri}' is not registered for this client.",
        )

    # Validate state
    if not state:
        return _render_error("invalid_request", "state parameter is required.")

    # Store auth request for consent form
    csrf_token = secrets.token_urlsafe(16)
    auth_request_id = store_auth_request({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "scope": scope,
        "resource": resource,
        "csrf_token": csrf_token,
    })

    return render_template(
        "oauth/consent.html",
        client_name=client.get("client_name", client_id),
        is_trusted=client.get("is_trusted", False),
        scope=scope,
        auth_request_id=auth_request_id,
        csrf_token=csrf_token,
        error=None,
    )


@oauth_bp.route("/authorize/submit", methods=["POST"])
def authorize_submit():
    """Process consent form submission."""
    auth_request_id = request.form.get("auth_request_id", "")
    csrf_token = request.form.get("csrf_token", "")
    action = request.form.get("action", "")
    wallet = request.form.get("wallet", "").strip()

    # Retrieve pending auth request
    auth_req = get_auth_request(auth_request_id)
    if not auth_req:
        return _render_error("invalid_request", "Authorization request expired. Please try again.")

    # Verify CSRF
    if csrf_token != auth_req.get("csrf_token", ""):
        return _render_error("invalid_request", "Invalid CSRF token.")

    redirect_uri = auth_req["redirect_uri"]
    state = auth_req["state"]

    # User denied
    if action == "deny":
        return redirect(f"{redirect_uri}?{urlencode({'error': 'access_denied', 'state': state})}")

    # Validate wallet address
    wallet_lower = wallet.lower()
    if not (wallet_lower.startswith("0x") and len(wallet_lower) == 42):
        # Re-render consent with error
        client = get_client(auth_req["client_id"])
        new_csrf = secrets.token_urlsafe(16)
        new_request_id = store_auth_request({**auth_req, "csrf_token": new_csrf})
        return render_template(
            "oauth/consent.html",
            client_name=client.get("client_name", auth_req["client_id"]) if client else auth_req["client_id"],
            is_trusted=client.get("is_trusted", False) if client else False,
            scope=auth_req.get("scope", ""),
            auth_request_id=new_request_id,
            csrf_token=new_csrf,
            error="Invalid wallet address. Must be 0x followed by 40 hex characters.",
        )

    try:
        int(wallet_lower[2:], 16)
    except ValueError:
        client = get_client(auth_req["client_id"])
        new_csrf = secrets.token_urlsafe(16)
        new_request_id = store_auth_request({**auth_req, "csrf_token": new_csrf})
        return render_template(
            "oauth/consent.html",
            client_name=client.get("client_name", auth_req["client_id"]) if client else auth_req["client_id"],
            is_trusted=client.get("is_trusted", False) if client else False,
            scope=auth_req.get("scope", ""),
            auth_request_id=new_request_id,
            csrf_token=new_csrf,
            error="Invalid wallet address. Contains non-hex characters.",
        )

    # Issue auth code
    code = create_auth_code(
        wallet=wallet_lower,
        client_id=auth_req["client_id"],
        redirect_uri=redirect_uri,
        scope=auth_req.get("scope", "tools:free tools:paid"),
        code_challenge=auth_req["code_challenge"],
    )

    return redirect(f"{redirect_uri}?{urlencode({'code': code, 'state': state})}")


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------

@oauth_bp.route("/token", methods=["POST"])
def token():
    """OAuth 2.1 Token endpoint — code exchange and refresh."""
    _ensure_seeded()

    # Accept both form-encoded and JSON
    if request.content_type and "json" in request.content_type:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    grant_type = data.get("grant_type", "")

    if grant_type == "authorization_code":
        return _handle_code_exchange(data)
    elif grant_type == "refresh_token":
        return _handle_refresh(data)
    else:
        return _token_error("unsupported_grant_type", f"Grant type '{grant_type}' is not supported.")


def _handle_code_exchange(data: dict):
    """Exchange authorization code for tokens."""
    code = data.get("code", "")
    redirect_uri = data.get("redirect_uri", "")
    client_id = data.get("client_id", "")
    code_verifier = data.get("code_verifier", "")

    if not all([code, redirect_uri, client_id, code_verifier]):
        return _token_error("invalid_request", "Missing required parameters: code, redirect_uri, client_id, code_verifier")

    # Validate client exists
    client = get_client(client_id)
    if not client:
        return _token_error("invalid_client", "Client not found.")

    # Exchange
    result = exchange_auth_code(code, code_verifier, redirect_uri, client_id)
    if result is None:
        return _token_error("invalid_grant", "Authorization code is invalid, expired, or already used.")

    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store, no-cache"
    response.headers["Pragma"] = "no-cache"
    return response


def _handle_refresh(data: dict):
    """Exchange refresh token for new token pair."""
    refresh_token_raw = data.get("refresh_token", "")
    client_id = data.get("client_id", "")

    if not refresh_token_raw or not client_id:
        return _token_error("invalid_request", "Missing required parameters: refresh_token, client_id")

    client = get_client(client_id)
    if not client:
        return _token_error("invalid_client", "Client not found.")

    result = refresh_tokens(refresh_token_raw, client_id)
    if result is None:
        return _token_error("invalid_grant", "Refresh token is invalid, expired, or already used.")

    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store, no-cache"
    response.headers["Pragma"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591)
# ---------------------------------------------------------------------------

@oauth_bp.route("/register", methods=["POST"])
def dcr_register():
    """Register a new OAuth client dynamically."""
    _ensure_seeded()

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid_request", "error_description": "JSON body required"}), 400

    try:
        result = register_client(data)
    except ValueError as e:
        return jsonify({"error": "invalid_client_metadata", "error_description": str(e)}), 400

    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_error(error_code: str, error_description: str, status: int = 400):
    """Render the OAuth error page."""
    return render_template(
        "oauth/error.html",
        error_code=error_code,
        error_description=error_description,
    ), status


def _token_error(error: str, description: str, status: int = 400):
    """Return a standard OAuth token error response."""
    response = jsonify({
        "error": error,
        "error_description": description,
    })
    response.status_code = status
    response.headers["Cache-Control"] = "no-store, no-cache"
    return response
