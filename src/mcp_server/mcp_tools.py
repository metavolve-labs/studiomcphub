"""MCP tool registrations for StudioMCPHub Streamable HTTP transport.

Registers all 32 tools as proper MCP tools with payment gating.
Each tool checks payment, dispatches to the existing tool implementation,
and returns MCP-formatted results.
"""

import json
import logging
from datetime import datetime, timezone

from mcp.server import Server
from mcp.types import (
    TextContent,
    Tool,
    ToolAnnotations,
)

from .config import PRICING, config

logger = logging.getLogger("studiomcphub.mcp")

# Tools excluded from "directory" profile (Anthropic policy 4A/4B compliance)
# 4B: AI image generation prohibited unless design-focused
# 4A: Financial/crypto transactions prohibited
_DIRECTORY_EXCLUDED = {
    "generate_image",       # 4B — standalone AI image generation
    "generate_image_nano",  # 4B — standalone AI image generation
    "mint_nft",             # 4A — crypto/financial transaction
    "store_permanent",      # Arweave blockchain storage
    "full_pipeline",        # Orchestrates generation
}


def _is_tool_enabled(name: str) -> bool:
    """Check if a tool is enabled under the current TOOL_PROFILE."""
    if config.tool_profile == "directory" and name in _DIRECTORY_EXCLUDED:
        return False
    return True


# --- MCP Tool Safety Annotations (per MCP spec 2025-11) ---
# readOnlyHint:    true = no side effects, false = writes data
# destructiveHint: true = may delete/overwrite, false = additive only
# idempotentHint:  true = same args → same effect, false = may differ
# openWorldHint:   true = calls external services, false = closed domain
TOOL_ANNOTATIONS: dict[str, ToolAnnotations] = {
    # --- Creative pipeline (writes/transforms, calls GPU services) ---
    "generate_image": ToolAnnotations(
        title="Generate Image (SD 3.5 Large)",
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True,
    ),
    "upscale_image": ToolAnnotations(
        title="Upscale Image (ESRGAN)",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "enrich_metadata": ToolAnnotations(
        title="AI Metadata Enrichment",
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True,
    ),
    "infuse_metadata": ToolAnnotations(
        title="Metadata Infusion (ExifTool)",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "register_hash": ToolAnnotations(
        title="Perceptual Hash Registration",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "store_permanent": ToolAnnotations(
        title="Arweave Permanent Storage",
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True,
    ),
    "mint_nft": ToolAnnotations(
        title="NFT Minting",
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True,
    ),
    "verify_provenance": ToolAnnotations(
        title="Provenance Verification",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "full_pipeline": ToolAnnotations(
        title="Full Creative Pipeline",
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True,
    ),
    # --- Dataset tools (read-only queries against Alexandria Aeternum) ---
    "search_artworks": ToolAnnotations(
        title="Search Artworks",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "get_artwork": ToolAnnotations(
        title="Get Artwork Metadata",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "get_artwork_oracle": ToolAnnotations(
        title="Get Artwork Oracle Analysis",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "batch_download": ToolAnnotations(
        title="Batch Download",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True,
    ),
    "compliance_manifest": ToolAnnotations(
        title="Compliance Manifest",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    # --- Nano generation ---
    "generate_image_nano": ToolAnnotations(
        title="Generate Image (Imagen 3)",
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True,
    ),
    # --- Image utilities (pure transforms, no external calls) ---
    "resize_image": ToolAnnotations(
        title="Resize Image",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "extract_palette": ToolAnnotations(
        title="Extract Color Palette",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "remove_background": ToolAnnotations(
        title="Remove Background",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "mockup_image": ToolAnnotations(
        title="Product Mockup",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "convert_color_profile": ToolAnnotations(
        title="Convert Color Profile",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "print_ready": ToolAnnotations(
        title="Print-Ready Preparation",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "vectorize_image": ToolAnnotations(
        title="Vectorize to SVG",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "watermark_embed": ToolAnnotations(
        title="Embed Invisible Watermark",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "watermark_detect": ToolAnnotations(
        title="Detect Watermark",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    # --- Storage tools (wallet-scoped CRUD) ---
    "save_asset": ToolAnnotations(
        title="Save Asset to Storage",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "get_asset": ToolAnnotations(
        title="Retrieve Asset",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "list_assets": ToolAnnotations(
        title="List Stored Assets",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "delete_asset": ToolAnnotations(
        title="Delete Asset",
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False,
    ),
    # --- Account tools (wallet registration + balance) ---
    "register_wallet": ToolAnnotations(
        title="Register Wallet",
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "check_balance": ToolAnnotations(
        title="Check Balance",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    # --- Meta-tools (discovery) ---
    "search_tools": ToolAnnotations(
        title="Search Tools",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
    "get_tool_schema": ToolAnnotations(
        title="Get Tool Schema",
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False,
    ),
}

# Tool input schemas for MCP discovery
TOOL_SCHEMAS = {
    "generate_image": {
        "description": "Text-to-image generation using SD 3.5 Large + T5-XXL on NVIDIA L4 GPU. Prompts are automatically enhanced by Gemini for optimal output and checked for content safety.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for image generation (will be enhanced by AI for optimal SD 3.5 output)"},
                "negative_prompt": {"type": "string", "description": "Negative prompt (auto-generated if not provided)", "default": ""},
                "width": {"type": "integer", "description": "Image width (512-2048)", "default": 1024},
                "height": {"type": "integer", "description": "Image height (512-2048)", "default": 1024},
                "guidance_scale": {"type": "number", "description": "CFG scale (1.0-20.0)", "default": 7.5},
                "enhance_prompt": {"type": "boolean", "description": "Whether to enhance the prompt via AI (default true)", "default": True},
            },
            "required": ["prompt"],
        },
    },
    "upscale_image": {
        "description": "Super-resolution using Real-ESRGAN on NVIDIA L4 GPU. 5 models for different content types. Default: 2x general upscale.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "model": {
                    "type": "string",
                    "description": "ESRGAN model to use. Options: 'realesrgan_x2plus' (2x, general — default), 'realesrgan_x4plus' (4x, general/photo), 'realesrgan_x4plus_anime' (4x, anime/illustrations), 'realesr_general_x4v3' (4x, fast general), 'realesr_animevideov3' (4x, anime video frames).",
                    "default": "realesrgan_x2plus",
                    "enum": ["realesrgan_x2plus", "realesrgan_x4plus", "realesrgan_x4plus_anime", "realesr_general_x4v3", "realesr_animevideov3"],
                },
                "scale": {"type": "integer", "description": "Shorthand: 2 selects x2plus, 4 selects x4plus. Ignored if model is specified directly.", "default": 2},
            },
            "required": ["image"],
        },
    },
    "enrich_metadata": {
        "description": "AI-powered artwork analysis. Two tiers: 'standard' (1 GCX) = SEO-optimized title, description, keywords, alt_text via Nova-Lite. 'premium' (2 GCX, default) = full 8-section Golden Codex museum-grade analysis via Nova/Gemini 2.5 Pro. Optionally customize metadata fields and add a Soul Whisper personal message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "tier": {"type": "string", "description": "Metadata tier: 'standard' (1 GCX — SEO title/description/keywords/alt_text) or 'premium' (2 GCX — full Golden Codex 8-section analysis)", "default": "premium", "enum": ["standard", "premium"]},
                "content_type": {"type": "string", "description": "Content type hint: 'artwork' or 'photo' — affects analysis style", "default": "artwork", "enum": ["artwork", "photo"]},
                "context": {"type": "string", "description": "Creator's brief — technical/artistic context for AI analysis (e.g. 'SD 3.5 Large, impressionist style')", "default": ""},
                "artist_name": {"type": "string", "description": "Artist/creator name (embedded in metadata)", "default": ""},
                "title": {"type": "string", "description": "Artwork title (leave blank for AI to suggest one)", "default": ""},
                "copyright_holder": {"type": "string", "description": "Copyright owner name", "default": ""},
                "creation_year": {"type": "string", "description": "4-digit creation year", "default": ""},
                "soul_whisper": {
                    "type": "object",
                    "description": "Optional personal message embedded in metadata — visible to anyone who reads the image's provenance (premium tier only)",
                    "properties": {
                        "message": {"type": "string", "description": "Personal message, dedication, or story behind the artwork (max 1000 chars)"},
                        "sender": {"type": "string", "description": "Your name or pseudonym"},
                    },
                },
            },
            "required": ["image"],
        },
    },
    "infuse_metadata": {
        "description": "Embed metadata into image via ExifTool. Two modes: 'standard' (XMP/IPTC only — title, description, keywords, copyright) or 'full_gcx' (default — full Golden Codex XMP-gc namespace + IPTC + C2PA + soulmark + hash registration).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "metadata": {"type": "object", "description": "Metadata JSON to embed. For standard: {title, description, keywords, alt_text, copyright_holder}. For full_gcx: Golden Codex JSON from enrich_metadata."},
                "metadata_mode": {"type": "string", "description": "Infusion mode: 'standard' (XMP/IPTC fields only) or 'full_gcx' (full Golden Codex + soulmark + hash registration)", "default": "full_gcx", "enum": ["standard", "full_gcx"]},
            },
            "required": ["image", "metadata"],
        },
    },
    "register_hash": {
        "description": "Register 256-bit perceptual hash with LSH band indexing for strip-proof provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
            },
            "required": ["image"],
        },
    },
    "store_permanent": {
        "description": "Upload to Arweave L1 for permanent, immutable storage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "metadata": {"type": "object", "description": "Optional metadata JSON to store alongside"},
            },
            "required": ["image"],
        },
    },
    "mint_nft": {
        "description": "Mint as NFT on Base L2 (Aeternum Collection) or Polygon. Image stored permanently on Arweave. Auto-listed on OpenSea.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "recipient_wallet": {"type": "string", "description": "EVM wallet address (0x...) to receive the NFT"},
                "chain": {"type": "string", "description": "Blockchain to mint on", "default": "base", "enum": ["base", "polygon"]},
                "title": {"type": "string", "description": "NFT title/name"},
                "description": {"type": "string", "description": "NFT description"},
                "attributes": {
                    "type": "array",
                    "description": "OpenSea-compatible attributes",
                    "items": {
                        "type": "object",
                        "properties": {
                            "trait_type": {"type": "string"},
                            "value": {"type": "string"},
                        },
                    },
                },
                "metadata": {"type": "object", "description": "Golden Codex metadata JSON (optional, for provenance)"},
                "collection": {"type": "string", "description": "Optional collection name or ID (Polygon only)"},
            },
            "required": ["image", "recipient_wallet"],
        },
    },
    "verify_provenance": {
        "description": "Strip-proof provenance verification via Aegis hash index. FREE - no payment required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
            },
            "required": ["image"],
        },
    },
    "full_pipeline": {
        "description": "Complete creative pipeline: generate/upscale/enrich/infuse/register/store/mint in one call.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt (provide this OR image)"},
                "image": {"type": "string", "description": "Base64 image (provide this OR prompt)"},
                "options": {"type": "object", "description": "Per-stage overrides and skip list"},
            },
        },
    },
    # --- Alexandria Aeternum Dataset Tools ---
    "search_artworks": {
        "description": "Search 53K+ museum artworks from Alexandria Aeternum (MET, Chicago, NGA, Rijksmuseum, Smithsonian, Cleveland, Paris). FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g. 'impressionist landscape', 'Monet', 'Dutch Golden Age')"},
                "museum": {"type": "string", "description": "Filter by museum (met, chicago, nga, rijks, smithsonian, cleveland, paris)", "default": ""},
                "limit": {"type": "integer", "description": "Max results (1-100)", "default": 20},
            },
            "required": ["query"],
        },
    },
    "get_artwork": {
        "description": "Get Human_Standard metadata (500-1200 tokens) + signed image URL for a museum artwork.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string", "description": "Artifact ID from search results (e.g. 'met_437419')"},
            },
            "required": ["artifact_id"],
        },
    },
    "get_artwork_oracle": {
        "description": "Get Hybrid_Premium 111-field NEST analysis (2K-6K tokens) + image. Deep AI visual analysis with color palette, composition, symbolism, emotional mapping.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string", "description": "Artifact ID from search results (e.g. 'met_437419')"},
            },
            "required": ["artifact_id"],
        },
    },
    "batch_download": {
        "description": "Bulk download metadata + images from Alexandria Aeternum (min 100 artworks).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Dataset ID", "default": "alexandria-aeternum"},
                "quantity": {"type": "integer", "description": "Number of artworks (min 100)", "default": 100},
                "offset": {"type": "integer", "description": "Start offset for pagination", "default": 0},
            },
        },
    },
    "compliance_manifest": {
        "description": "Get AB 2013 (California) + EU AI Act Article 53 compliance manifests for dataset usage. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Dataset ID", "default": "alexandria-aeternum"},
                "regulation": {"type": "string", "description": "Filter: ab2013, eu_ai_act, or all", "default": "all"},
            },
        },
    },
    # --- Nano Banana Pro (Imagen 3) ---
    "generate_image_nano": {
        "description": "Fast concept generation using Google Imagen 3. Great for rapid iteration before HD renders. Prompts are enhanced by AI and checked for safety.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt for image generation (enhanced by AI for optimal output)"},
                "width": {"type": "integer", "description": "Image width (1024 or 2048)", "default": 1024},
                "height": {"type": "integer", "description": "Image height (1024 or 2048)", "default": 1024},
                "enhance_prompt": {"type": "boolean", "description": "Whether to enhance the prompt via AI (default true)", "default": True},
            },
            "required": ["prompt"],
        },
    },
    # --- Image Utilities ---
    "resize_image": {
        "description": "Resize an image to target dimensions. Supports fit modes: 'cover' (crop to fill), 'contain' (fit within, letterbox), 'stretch' (exact size). Useful for preparing images for specific platforms, thumbnails, or social media. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "width": {"type": "integer", "description": "Target width in pixels (1-8192)", "minimum": 1, "maximum": 8192},
                "height": {"type": "integer", "description": "Target height in pixels (1-8192)", "minimum": 1, "maximum": 8192},
                "mode": {"type": "string", "description": "Resize mode: 'contain' (fit within bounds, preserve aspect ratio), 'cover' (crop to fill), 'stretch' (exact size, may distort)", "default": "contain", "enum": ["contain", "cover", "stretch"]},
                "format": {"type": "string", "description": "Output format", "default": "png", "enum": ["png", "jpeg", "webp"]},
                "quality": {"type": "integer", "description": "JPEG/WebP quality (1-100)", "default": 90, "minimum": 1, "maximum": 100},
            },
            "required": ["image", "width", "height"],
        },
    },
    # --- Creative Processing Tools ---
    "extract_palette": {
        "description": "Extract dominant color palette from an image. Returns hex/RGB/HSL colors with percentages, CSS names, and complementary colors. Great for design systems, mood boards, and color matching. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "num_colors": {"type": "integer", "description": "Number of colors to extract (3-12)", "default": 6, "minimum": 3, "maximum": 12},
                "format": {"type": "string", "description": "Color format in output", "default": "hex", "enum": ["hex", "rgb", "hsl"]},
            },
            "required": ["image"],
        },
    },
    "remove_background": {
        "description": "Remove image background using AI (U2-Net). Returns RGBA PNG/WebP with transparent background. Perfect for product photos, portraits, and design assets. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "output_format": {"type": "string", "description": "Output format", "default": "png", "enum": ["png", "webp"]},
            },
            "required": ["image"],
        },
    },
    "mockup_image": {
        "description": "Place your design onto product mockups (t-shirt, poster, canvas, phone case, mug, tote bag). Instant product visualization for e-commerce and print-on-demand. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded design image"},
                "product": {"type": "string", "description": "Product type", "default": "tshirt", "enum": ["tshirt", "poster", "canvas", "phone_case", "mug", "tote_bag"]},
                "background_color": {"type": "string", "description": "Background hex color", "default": "#f5f5f5"},
            },
            "required": ["image"],
        },
    },
    "convert_color_profile": {
        "description": "Convert between sRGB and CMYK color profiles. Essential for print production. CMYK output as TIFF with embedded DPI. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "target_profile": {"type": "string", "description": "Target color profile", "default": "cmyk", "enum": ["cmyk", "srgb"]},
                "dpi": {"type": "integer", "description": "Output DPI (72-1200)", "default": 300, "minimum": 72, "maximum": 1200},
            },
            "required": ["image"],
        },
    },
    "print_ready": {
        "description": "Prepare images for professional printing with DPI, bleed margins, crop marks. Supports A4, A3, Letter, poster (24x36), custom sizes. Output as TIFF or PDF. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "dpi": {"type": "integer", "description": "Output DPI", "default": 300, "enum": [150, 300, 600]},
                "bleed_mm": {"type": "number", "description": "Bleed margin in mm (0-10)", "default": 3.0},
                "crop_marks": {"type": "boolean", "description": "Draw crop marks in bleed area", "default": True},
                "output_format": {"type": "string", "description": "Output format", "default": "tiff", "enum": ["tiff", "pdf"]},
                "product_size": {"type": "string", "description": "Standard paper size", "default": "a4", "enum": ["a4", "a3", "letter", "poster_24x36", "custom"]},
                "custom_width_mm": {"type": "number", "description": "Custom width in mm (required if product_size=custom)"},
                "custom_height_mm": {"type": "number", "description": "Custom height in mm (required if product_size=custom)"},
            },
            "required": ["image"],
        },
    },
    "vectorize_image": {
        "description": "Convert raster images to SVG vector format. Supports color and binary modes with precision controls. Returns raw SVG XML string. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "color_precision": {"type": "integer", "description": "Color clustering precision (1-10, higher = more colors)", "default": 6, "minimum": 1, "maximum": 10},
                "filter_speckle": {"type": "integer", "description": "Speckle filter (0-100, higher = fewer small artifacts)", "default": 4, "minimum": 0, "maximum": 100},
                "mode": {"type": "string", "description": "Vectorization mode", "default": "color", "enum": ["color", "binary"]},
            },
            "required": ["image"],
        },
    },
    "watermark_embed": {
        "description": "Embed invisible DCT-domain watermark into an image. Encodes a text payload into luminance channel frequency coefficients. Survives light compression. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
                "payload": {"type": "string", "description": "Text payload to embed (max 256 chars)", "maxLength": 256},
                "strength": {"type": "number", "description": "Embedding strength (0.1-1.0, higher = more robust but more visible)", "default": 0.5, "minimum": 0.1, "maximum": 1.0},
            },
            "required": ["image", "payload"],
        },
    },
    "watermark_detect": {
        "description": "Detect and extract invisible DCT watermark from an image. Returns the embedded text payload if found. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Base64-encoded PNG/JPEG image"},
            },
            "required": ["image"],
        },
    },
    # --- Agent Storage ---
    "save_asset": {
        "description": "Save an image or data to your personal wallet storage. 100MB free per wallet, 500 assets max.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Your EVM wallet address (0x...)"},
                "key": {"type": "string", "description": "Unique name for this asset (e.g., 'my-landscape', 'pipeline-001')"},
                "data": {"type": "string", "description": "Base64-encoded data (image, JSON, etc.) — max 10MB"},
                "content_type": {"type": "string", "description": "MIME type", "default": "image/png"},
                "metadata": {"type": "object", "description": "Optional metadata JSON to store alongside"},
            },
            "required": ["wallet", "key", "data"],
        },
    },
    "get_asset": {
        "description": "Retrieve a stored asset from your wallet storage by key. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Your EVM wallet address (0x...)"},
                "key": {"type": "string", "description": "Asset key to retrieve"},
            },
            "required": ["wallet", "key"],
        },
    },
    "list_assets": {
        "description": "List all assets in your wallet storage with sizes and metadata. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Your EVM wallet address (0x...)"},
            },
            "required": ["wallet"],
        },
    },
    "delete_asset": {
        "description": "Delete an asset from your wallet storage. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Your EVM wallet address (0x...)"},
                "key": {"type": "string", "description": "Asset key to delete"},
            },
            "required": ["wallet", "key"],
        },
    },
    # --- Account tools ---
    "register_wallet": {
        "description": "Register your wallet to create a GCX account. Purchase credits via GCX packs. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Your EVM wallet address (0x...)"},
            },
            "required": ["wallet"],
        },
    },
    "check_balance": {
        "description": "Check your GCX credit balance, loyalty rewards, and volume tier. FREE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "wallet": {"type": "string", "description": "Your EVM wallet address (0x...)"},
            },
            "required": ["wallet"],
        },
    },
    # --- Meta-tools (Progressive Discovery) ---
    "search_tools": {
        "description": "Discover available tools by category or price without loading all schemas. Start here to save tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query to filter tools by name or description", "default": ""},
                "category": {
                    "type": "string",
                    "description": "Filter by category",
                    "enum": ["creative", "dataset", "storage", "account", "free", "all"],
                    "default": "all",
                },
                "max_price_usd": {"type": "number", "description": "Max price per call in USD (0 = free only)", "default": -1},
            },
        },
    },
    "get_tool_schema": {
        "description": "Get the full JSON Schema and usage examples for a specific tool. Use after search_tools to load only what you need.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Tool name from search_tools results (e.g. 'generate_image')"},
            },
            "required": ["tool_name"],
        },
    },
}


def create_mcp_server(check_payment_fn) -> Server:
    """Create and configure an MCP Server with all tools registered.

    Args:
        check_payment_fn: Callable(tool_name, headers) -> (method, details) | None
            Payment verification function. Returns None if payment required.
    """
    server = Server("StudioMCPHub")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for name, schema in TOOL_SCHEMAS.items():
            if not _is_tool_enabled(name):
                continue
            price = PRICING.get(name)
            price_note = f" (${price.x402_cents / 100:.2f} / {price.gcx_credits} GCX)" if price and price.gcx_credits > 0 else " (FREE)"
            tools.append(Tool(
                name=name,
                description=schema["description"] + price_note,
                inputSchema=schema["inputSchema"],
                annotations=TOOL_ANNOTATIONS.get(name),
            ))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name not in TOOL_SCHEMAS or not _is_tool_enabled(name):
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        # Payment gating is handled at the HTTP layer (check_payment in server.py).
        # By the time we reach here, payment has already been verified by the
        # Flask /mcp handler. We just dispatch and return.
        try:
            from ..tools import dispatch_tool
            result = dispatch_tool(name, arguments)
            return [TextContent(type="text", text=json.dumps({
                "tool": name,
                "status": "success",
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))]
        except Exception as e:
            logger.error(f"MCP tool {name} failed: {e}")
            return [TextContent(type="text", text=json.dumps({
                "tool": name,
                "status": "error",
                "error": str(e),
            }))]

    return server
