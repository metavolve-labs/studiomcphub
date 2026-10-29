"""StudioMCPHub tool dispatch."""

from typing import Any


def _resolve_wallet_from_params(params: dict) -> str:
    """Extract wallet address from params body or Bearer header fallback."""
    wallet = params.get("wallet", "").strip().lower()
    if not wallet:
        try:
            from flask import request as _req
            auth = _req.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                from ..auth.tokens import resolve_bearer_to_wallet
                wallet = (resolve_bearer_to_wallet(auth[7:]) or "").lower()
        except RuntimeError:
            pass
    if not wallet:
        raise ValueError("Missing 'wallet'. Provide in body or use Authorization: Bearer header.")
    return wallet


# Category mapping for progressive discovery
_TOOL_CATEGORIES: dict[str, str] = {
    "generate_image": "creative",
    "upscale_image": "creative",
    "enrich_metadata": "creative",
    "infuse_metadata": "creative",
    "register_hash": "creative",
    "store_permanent": "creative",
    "mint_nft": "creative",
    "verify_provenance": "creative",
    "full_pipeline": "creative",
    "search_artworks": "dataset",
    "get_artwork": "dataset",
    "get_artwork_oracle": "dataset",
    "batch_download": "dataset",
    "compliance_manifest": "dataset",
    "generate_image_nano": "creative",
    "resize_image": "creative",
    "extract_palette": "creative",
    "remove_background": "creative",
    "mockup_image": "creative",
    "convert_color_profile": "creative",
    "print_ready": "creative",
    "vectorize_image": "creative",
    "watermark_embed": "creative",
    "watermark_detect": "creative",
    "save_asset": "storage",
    "get_asset": "storage",
    "list_assets": "storage",
    "delete_asset": "storage",
    "register_wallet": "account",
    "check_balance": "account",
}

# Usage examples for get_tool_schema
_TOOL_EXAMPLES: dict[str, list[dict]] = {
    "generate_image": [
        {"prompt": "A serene Japanese garden at sunset", "width": 1024, "height": 1024},
    ],
    "upscale_image": [
        {"image": "<base64-encoded-image>", "scale": 2},
        {"image": "<base64-encoded-image>", "model": "realesrgan_x4plus"},
        {"image": "<base64-encoded-image>", "model": "realesrgan_x4plus_anime"},
    ],
    "enrich_metadata": [
        {"image": "<base64-encoded-image>", "tier": "standard", "content_type": "artwork"},
        {"image": "<base64-encoded-image>", "tier": "premium", "context": "Oil on canvas, Claude Monet, 1872"},
    ],
    "infuse_metadata": [
        {"image": "<base64-encoded-image>", "metadata": {"title": "Water Lilies", "description": "...", "keywords": ["impressionist"]}, "metadata_mode": "standard"},
        {"image": "<base64-encoded-image>", "metadata": {"title": "Water Lilies", "artist": "Monet"}, "metadata_mode": "full_gcx"},
    ],
    "register_hash": [
        {"image": "<base64-encoded-image>"},
    ],
    "store_permanent": [
        {"image": "<base64-encoded-image>", "metadata": {"title": "My Artwork"}},
    ],
    "mint_nft": [
        {"image": "<base64-encoded-image>", "metadata": {"title": "Genesis #1"}, "collection": "my-collection"},
    ],
    "verify_provenance": [
        {"image": "<base64-encoded-image>"},
    ],
    "full_pipeline": [
        {"prompt": "Impressionist landscape", "options": {"skip": ["mint_nft", "store_permanent"]}},
    ],
    "search_artworks": [
        {"query": "impressionist landscape", "museum": "met", "limit": 10},
    ],
    "get_artwork": [
        {"artifact_id": "met_437419"},
    ],
    "get_artwork_oracle": [
        {"artifact_id": "met_437419"},
    ],
    "batch_download": [
        {"dataset_id": "alexandria-aeternum", "quantity": 100, "offset": 0},
    ],
    "compliance_manifest": [
        {"dataset_id": "alexandria-aeternum", "regulation": "all"},
    ],
    "resize_image": [
        {"image": "<base64-encoded-image>", "width": 512, "height": 512, "mode": "contain"},
        {"image": "<base64-encoded-image>", "width": 1200, "height": 630, "mode": "cover", "format": "jpeg", "quality": 85},
    ],
    "extract_palette": [
        {"image": "<base64-encoded-image>", "num_colors": 6, "format": "hex"},
        {"image": "<base64-encoded-image>", "num_colors": 8, "format": "rgb"},
    ],
    "remove_background": [
        {"image": "<base64-encoded-image>"},
        {"image": "<base64-encoded-image>", "output_format": "webp"},
    ],
    "mockup_image": [
        {"image": "<base64-encoded-image>", "product": "tshirt"},
        {"image": "<base64-encoded-image>", "product": "poster", "background_color": "#ffffff"},
    ],
    "convert_color_profile": [
        {"image": "<base64-encoded-image>", "target_profile": "cmyk", "dpi": 300},
        {"image": "<base64-encoded-image>", "target_profile": "srgb"},
    ],
    "print_ready": [
        {"image": "<base64-encoded-image>", "dpi": 300, "product_size": "a4", "output_format": "tiff"},
        {"image": "<base64-encoded-image>", "dpi": 300, "product_size": "poster_24x36", "bleed_mm": 5, "output_format": "pdf"},
    ],
    "vectorize_image": [
        {"image": "<base64-encoded-image>", "mode": "color", "color_precision": 6},
        {"image": "<base64-encoded-image>", "mode": "binary"},
    ],
    "watermark_embed": [
        {"image": "<base64-encoded-image>", "payload": "Created by MyBot 2026", "strength": 0.5},
    ],
    "watermark_detect": [
        {"image": "<base64-encoded-image>"},
    ],
}


def dispatch_tool(tool_name: str, params: dict) -> dict[str, Any]:
    """Route a tool call to its implementation."""
    handlers = {
        "generate_image": _generate_image,
        "upscale_image": _upscale_image,
        "enrich_metadata": _enrich_metadata,
        "infuse_metadata": _infuse_metadata,
        "register_hash": _register_hash,
        "store_permanent": _store_permanent,
        "mint_nft": _mint_nft,
        "verify_provenance": _verify_provenance,
        "full_pipeline": _full_pipeline,
        # Dataset tools
        "search_artworks": _search_artworks,
        "get_artwork": _get_artwork,
        "get_artwork_oracle": _get_artwork_oracle,
        "batch_download": _batch_download,
        "compliance_manifest": _compliance_manifest,
        # Nano Banana Pro
        "generate_image_nano": _generate_image_nano,
        # Image utilities
        "resize_image": _resize_image,
        "extract_palette": _extract_palette,
        "remove_background": _remove_background,
        "mockup_image": _mockup_image,
        "convert_color_profile": _convert_color_profile,
        "print_ready": _print_ready,
        "vectorize_image": _vectorize_image,
        "watermark_embed": _watermark_embed,
        "watermark_detect": _watermark_detect,
        # Storage tools
        "save_asset": _save_asset,
        "get_asset": _get_asset,
        "list_assets": _list_assets,
        "delete_asset": _delete_asset,
        # Account tools
        "register_wallet": _register_wallet,
        "check_balance": _check_balance,
        # Meta-tools
        "search_tools": _search_tools,
        "get_tool_schema": _get_tool_schema,
    }
    handler = handlers.get(tool_name)
    if not handler:
        raise ValueError(f"No handler for tool: {tool_name}")
    return handler(params)


def _generate_image(params: dict) -> dict:
    from .generate import generate_image
    return generate_image(
        prompt=params["prompt"],
        negative_prompt=params.get("negative_prompt", ""),
        width=params.get("width", 1024),
        height=params.get("height", 1024),
        guidance_scale=params.get("guidance_scale", 7.5),
        enhance_prompt=params.get("enhance_prompt", True),
    )


def _upscale_image(params: dict) -> dict:
    from .upscale import upscale_image
    return upscale_image(
        image_b64=params["image"],
        model=params.get("model"),
        scale=params.get("scale", 2),
    )


def _enrich_metadata(params: dict) -> dict:
    tier = params.get("tier", "premium")
    if tier == "standard":
        from .enrich import enrich_metadata_standard
        return enrich_metadata_standard(
            image_b64=params["image"],
            content_type=params.get("content_type", "artwork"),
        )
    from .enrich import enrich_metadata
    return enrich_metadata(
        image_b64=params["image"],
        context=params.get("context", ""),
        artist_name=params.get("artist_name", ""),
        title=params.get("title", ""),
        copyright_holder=params.get("copyright_holder", ""),
        creation_year=params.get("creation_year", ""),
        soul_whisper=params.get("soul_whisper"),
    )


def _infuse_metadata(params: dict) -> dict:
    from .infuse import infuse_metadata
    return infuse_metadata(
        image_b64=params["image"],
        metadata=params["metadata"],
        metadata_mode=params.get("metadata_mode", "full_gcx"),
    )


def _register_hash(params: dict) -> dict:
    from .register import register_hash
    return register_hash(image_b64=params["image"])


def _store_permanent(params: dict) -> dict:
    from .store import store_permanent
    return store_permanent(
        image_b64=params["image"],
        metadata=params.get("metadata"),
    )


def _mint_nft(params: dict) -> dict:
    # Minting disabled until hot wallets funded (AR + POL/ETH) and
    # OpenSea integration wired. Re-enable by removing this gate.
    raise ValueError(
        "mint_nft is temporarily disabled while we wire up Base L2 contract "
        "deployment, Arweave storage, and OpenSea integration. "
        "Follow @StudioMCPHub for launch announcement. ETA: coming soon."
    )


def _verify_provenance(params: dict) -> dict:
    from .verify import verify_provenance
    return verify_provenance(image_b64=params["image"])


def _full_pipeline(params: dict) -> dict:
    from .pipeline import run_full_pipeline
    return run_full_pipeline(
        prompt=params.get("prompt"),
        image_b64=params.get("image"),
        options=params.get("options", {}),
    )


# --- Dataset tools (Alexandria Aeternum) ---

def _search_artworks(params: dict) -> dict:
    from .dataset import search_artworks
    return search_artworks(
        query=params["query"],
        museum=params.get("museum", ""),
        limit=params.get("limit", 20),
    )


def _get_artwork(params: dict) -> dict:
    from .dataset import get_artwork
    artifact_id = params.get("artifact_id") or params.get("artwork_id")
    if not artifact_id:
        raise ValueError("Missing required parameter 'artifact_id'. Use search_artworks to find IDs.")
    return get_artwork(artifact_id=artifact_id)


def _get_artwork_oracle(params: dict) -> dict:
    from .dataset import get_artwork_oracle
    artifact_id = params.get("artifact_id") or params.get("artwork_id")
    if not artifact_id:
        raise ValueError("Missing required parameter 'artifact_id'. Use search_artworks to find IDs.")
    return get_artwork_oracle(artifact_id=artifact_id)


def _batch_download(params: dict) -> dict:
    from .dataset import batch_download
    return batch_download(
        dataset_id=params.get("dataset_id", "alexandria-aeternum"),
        quantity=params.get("quantity", 100),
        offset=params.get("offset", 0),
    )


def _compliance_manifest(params: dict) -> dict:
    from .dataset import compliance_manifest
    return compliance_manifest(
        dataset_id=params.get("dataset_id", "alexandria-aeternum"),
        regulation=params.get("regulation", "all"),
    )


# --- Nano Banana Pro (Imagen 3) ---

def _generate_image_nano(params: dict) -> dict:
    from .generate_nano import generate_image_nano
    return generate_image_nano(
        prompt=params["prompt"],
        width=params.get("width", 1024),
        height=params.get("height", 1024),
        enhance_prompt=params.get("enhance_prompt", True),
    )


# --- Image utilities ---

def _resize_image(params: dict) -> dict:
    from .resize import resize_image
    return resize_image(
        image_b64=params["image"],
        width=params["width"],
        height=params["height"],
        mode=params.get("mode", "contain"),
        fmt=params.get("format", "png"),
        quality=params.get("quality", 90),
    )


# --- Creative processing tools ---

def _extract_palette(params: dict) -> dict:
    from .palette import extract_palette
    return extract_palette(
        image_b64=params["image"],
        num_colors=params.get("num_colors", 6),
        fmt=params.get("format", "hex"),
    )


def _remove_background(params: dict) -> dict:
    from .remove_bg import remove_background
    return remove_background(
        image_b64=params["image"],
        output_format=params.get("output_format", "png"),
    )


def _mockup_image(params: dict) -> dict:
    from .mockup import mockup_image
    return mockup_image(
        image_b64=params["image"],
        product=params.get("product", "tshirt"),
        background_color=params.get("background_color", "#f5f5f5"),
    )


def _convert_color_profile(params: dict) -> dict:
    from .color_profile import convert_color_profile
    return convert_color_profile(
        image_b64=params["image"],
        target_profile=params.get("target_profile", "cmyk"),
        dpi=params.get("dpi", 300),
    )


def _print_ready(params: dict) -> dict:
    from .print_ready import print_ready
    return print_ready(
        image_b64=params["image"],
        dpi=params.get("dpi", 300),
        bleed_mm=params.get("bleed_mm", 3.0),
        crop_marks=params.get("crop_marks", True),
        output_format=params.get("output_format", "tiff"),
        product_size=params.get("product_size", "a4"),
        custom_width_mm=params.get("custom_width_mm"),
        custom_height_mm=params.get("custom_height_mm"),
    )


def _vectorize_image(params: dict) -> dict:
    from .vectorize import vectorize_image
    return vectorize_image(
        image_b64=params["image"],
        color_precision=params.get("color_precision", 6),
        filter_speckle=params.get("filter_speckle", 4),
        mode=params.get("mode", "color"),
    )


def _watermark_embed(params: dict) -> dict:
    from .watermark import watermark_embed
    return watermark_embed(
        image_b64=params["image"],
        payload=params["payload"],
        strength=params.get("strength", 0.5),
    )


def _watermark_detect(params: dict) -> dict:
    from .watermark import watermark_detect
    return watermark_detect(image_b64=params["image"])


# --- Storage tools ---

def _save_asset(params: dict) -> dict:
    from .storage import save_asset
    return save_asset(
        wallet=params["wallet"],
        key=params["key"],
        data=params["data"],
        content_type=params.get("content_type", "image/png"),
        metadata=params.get("metadata"),
    )


def _get_asset(params: dict) -> dict:
    from .storage import get_asset
    wallet = _resolve_wallet_from_params(params)
    return get_asset(wallet=wallet, key=params.get("key", params.get("asset_id", "")))


def _list_assets(params: dict) -> dict:
    from .storage import list_assets
    wallet = _resolve_wallet_from_params(params)
    return list_assets(wallet=wallet)


def _delete_asset(params: dict) -> dict:
    from .storage import delete_asset
    wallet = _resolve_wallet_from_params(params)
    return delete_asset(wallet=wallet, key=params.get("key", params.get("asset_id", "")))


# --- Account tools ---

def _register_wallet(params: dict) -> dict:
    from ..payment.gcx_credits import _get_db
    from datetime import datetime, timezone as tz

    wallet = params.get("wallet", "").strip().lower()
    if not (wallet.startswith("0x") and len(wallet) == 42):
        raise ValueError("Invalid wallet address. Expected 0x + 40 hex characters.")
    try:
        int(wallet[2:], 16)
    except ValueError:
        raise ValueError("Invalid wallet address: non-hex characters")

    db = _get_db()
    ref = db.collection("gcx_accounts").document(wallet)
    existing = ref.get()

    if existing.exists:
        account = existing.to_dict()
        return {
            "status": "existing",
            "wallet": wallet,
            "balance": account.get("balance", 0),
            "message": "Wallet already registered. Your balance is ready to use.",
        }

    from ..mcp_server.config import WELCOME_BONUS_GCX
    welcome_bonus = WELCOME_BONUS_GCX  # CSO interim 2026-10-29: 0 (REVISIT #69)
    ref.set({
        "balance": welcome_bonus,
        "created_at": datetime.now(tz.utc),
        "last_updated": datetime.now(tz.utc),
        "tier": "standard",
        "source": "mcp_registration",
        "welcome_bonus": welcome_bonus,
    })
    if welcome_bonus > 0:
        db.collection("gcx_transactions").add({
            "user_id": wallet,
            "type": "credit",
            "amount": welcome_bonus,
            "reason": "welcome_bonus",
            "balance_after": welcome_bonus,
            "timestamp": datetime.now(tz.utc),
        })

    return {
        "status": "created",
        "wallet": wallet,
        "balance": welcome_bonus,
        "message": (
            f"Welcome! You received {welcome_bonus} free GCX credits. Use them to call any tool."
            if welcome_bonus > 0 else
            "Wallet registered. Free tools work now; buy GCX packs (GET https://studiomcphub.com/api/credits) for paid tools."
        ),
        "next_step": "Call enrich_metadata, search_artworks, or any tool — credits deduct automatically when you include 'Authorization: Bearer <wallet>' header.",
    }


def _check_balance(params: dict) -> dict:
    wallet = _resolve_wallet_from_params(params)

    from ..payment.gcx_credits import get_balance
    from ..payment.loyalty import get_loyalty_balance
    from ..payment.agent_tiers import get_tier

    balance = get_balance(wallet)
    loyalty = get_loyalty_balance(wallet)
    tier = get_tier(wallet)

    return {
        "wallet": wallet,
        "gcx_balance": balance,
        "loyalty_credits": loyalty["balance"],
        "loyalty_lifetime_earned": loyalty["lifetime_earned"],
        "tier": tier["label"],
        "discount_pct": tier["discount_pct"],
        "spend_30d_usd": tier["spend_30d"],
    }


# --- Meta-tools (Progressive Discovery) ---

_META_TOOLS = {"search_tools", "get_tool_schema"}


def _search_tools(params: dict) -> dict:
    from ..mcp_server.mcp_tools import TOOL_SCHEMAS, _is_tool_enabled
    from ..mcp_server.config import PRICING

    query = params.get("query", "").lower()
    category = params.get("category", "all")
    max_price = params.get("max_price_usd", -1)

    results = []
    for name, schema in TOOL_SCHEMAS.items():
        # Exclude meta-tools and profile-disabled tools
        if name in _META_TOOLS or not _is_tool_enabled(name):
            continue

        tool_cat = _TOOL_CATEGORIES.get(name, "creative")
        price = PRICING.get(name)
        price_usd = (price.x402_cents / 100) if price else 0.0
        is_free = price_usd == 0

        # Category filter
        if category == "free" and not is_free:
            continue
        if category in ("creative", "dataset", "account", "storage") and tool_cat != category:
            continue

        # Price filter
        if max_price >= 0 and price_usd > max_price:
            continue

        # Query filter (name or description)
        if query:
            desc = schema.get("description", "").lower()
            if query not in name and query not in desc:
                continue

        # Truncate description to first sentence
        full_desc = schema.get("description", "")
        short_desc = full_desc.split(". ")[0] + "." if ". " in full_desc else full_desc

        results.append({
            "name": name,
            "description": short_desc,
            "price_usd": price_usd,
            "gcx_credits": price.gcx_credits if price else 0,
            "category": tool_cat,
            "free": is_free,
        })

    return {"tools": results, "total": len(results)}


def _get_tool_schema(params: dict) -> dict:
    from ..mcp_server.mcp_tools import TOOL_SCHEMAS, _is_tool_enabled
    from ..mcp_server.config import PRICING

    tool_name = params.get("tool_name", "")
    if not tool_name or tool_name not in TOOL_SCHEMAS or not _is_tool_enabled(tool_name):
        raise ValueError(f"Unknown tool: {tool_name}. Use search_tools to discover available tools.")

    schema = TOOL_SCHEMAS[tool_name]
    price = PRICING.get(tool_name)
    examples = _TOOL_EXAMPLES.get(tool_name, [])

    return {
        "name": tool_name,
        "description": schema["description"],
        "inputSchema": schema["inputSchema"],
        "price_usd": (price.x402_cents / 100) if price else 0.0,
        "gcx_credits": price.gcx_credits if price else 0,
        "examples": examples,
    }
