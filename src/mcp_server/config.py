"""StudioMCPHub configuration."""

import os
from dataclasses import dataclass, field


@dataclass
class ToolPricing:
    """Per-call pricing.

    Pricing aligns with PRICING_V2 (approved Feb 23, 2026).
    1 GCX = $0.10 base rate (Starter/Creator pack).
    x402 USDC = same as base GCX rate (no account = no discount).
    GCX holders get volume discounts via tier pricing:
      Curator: $0.095/GCX, Studio: $0.082/GCX, Gallery: $0.0625/GCX
    """
    gcx_credits: int         # GCX cost per call (canonical pricing unit)
    x402_cents: int = 0      # Auto-calculated: gcx * 10 (base rate)
    stripe_cents: int = 0    # Auto-calculated: gcx * 10 (same as x402)

    def __post_init__(self):
        if self.x402_cents == 0 and self.gcx_credits > 0:
            self.x402_cents = self.gcx_credits * 10   # 1 GCX = $0.10
        if self.stripe_cents == 0 and self.gcx_credits > 0:
            self.stripe_cents = self.gcx_credits * 10  # Same base rate


# Tool pricing table — aligned with PRICING_V2
# Matches golden-codex.com SaaS operation costs exactly
PRICING = {
    "generate_image":    ToolPricing(gcx_credits=2),   # $0.20 — SD 3.5L+T5XXL ($0.10 nano + $0.20 model)
    "upscale_image":     ToolPricing(gcx_credits=2),   # $0.20 — matches existing Flux cost
    "enrich_metadata":   ToolPricing(gcx_credits=2),   # $0.20 — matches existing Nova cost
    "infuse_metadata":   ToolPricing(gcx_credits=1),   # $0.10 — matches existing Atlas cost
    "register_hash":     ToolPricing(gcx_credits=1),   # $0.10 — light compute
    "store_permanent":   ToolPricing(gcx_credits=15),  # $1.50 — Arweave L1 storage
    "mint_nft":          ToolPricing(gcx_credits=10),  # $1.00 — Polygon gas + contract
    "verify_provenance": ToolPricing(gcx_credits=0),   # FREE  — adoption hook
    "full_pipeline":     ToolPricing(gcx_credits=5),   # $0.50 — enrich+upscale+infuse (no gen/mint)
    # --- Alexandria Aeternum Dataset Tools ---
    "search_artworks":      ToolPricing(gcx_credits=0),   # FREE  — discovery hook (50/hr rate limit)
    "get_artwork":           ToolPricing(gcx_credits=1),   # $0.10 — Human_Standard metadata + image
    "get_artwork_oracle":    ToolPricing(gcx_credits=2),   # $0.20 — Hybrid_Premium 111-field NEST analysis
    "batch_download":        ToolPricing(gcx_credits=50),  # $5.00 — 100+ images bulk download
    "compliance_manifest":   ToolPricing(gcx_credits=0),   # FREE  — AB 2013 + EU AI Act compliance
    # --- Nano Banana Pro (Imagen 3) ---
    "generate_image_nano":   ToolPricing(gcx_credits=1),   # $0.10 — Imagen 3 fast (concept iteration)
    # --- Image Utilities (ALL FREE — zero marginal cost, local Pillow/numpy) ---
    "resize_image":          ToolPricing(gcx_credits=0),   # FREE  — resize/crop/fit
    "extract_palette":       ToolPricing(gcx_credits=0),   # FREE  — color extraction
    "remove_background":     ToolPricing(gcx_credits=0),   # FREE  — AI bg removal (U2-Net, local)
    "mockup_image":          ToolPricing(gcx_credits=1),   # $0.10 — product mockup compositing (compute-heavy)
    "convert_color_profile": ToolPricing(gcx_credits=0),   # FREE  — sRGB/CMYK conversion
    "print_ready":           ToolPricing(gcx_credits=0),   # FREE  — print prep (DPI/bleed/marks)
    "vectorize_image":       ToolPricing(gcx_credits=0),   # FREE  — raster to SVG
    "watermark_embed":       ToolPricing(gcx_credits=0),   # FREE  — DCT watermark embedding
    "watermark_detect":      ToolPricing(gcx_credits=0),   # FREE  — watermark detection
    # --- Agent Storage ---
    "save_asset":            ToolPricing(gcx_credits=1),   # $0.10 — save to wallet storage (10MB max)
    "get_asset":             ToolPricing(gcx_credits=0),   # FREE  — retrieve stored asset
    "list_assets":           ToolPricing(gcx_credits=0),   # FREE  — list stored assets
    "delete_asset":          ToolPricing(gcx_credits=0),   # FREE  — delete stored asset
    # --- Account tools ---
    "register_wallet":       ToolPricing(gcx_credits=0),   # FREE  — onboarding (welcome bonus: WELCOME_BONUS_GCX)
    "check_balance":         ToolPricing(gcx_credits=0),   # FREE  — account status check
    # --- Meta-tools (Progressive Discovery) ---
    "search_tools":          ToolPricing(gcx_credits=0),   # FREE  — discover tools without loading schemas
    "get_tool_schema":       ToolPricing(gcx_credits=0),   # FREE  — fetch full schema for one tool
}

# Composite pipelines (for reference / UI display)
PIPELINE_COMBOS = {
    "creative_pipeline":  8,   # generate(2) + upscale(2) + enrich(2) + infuse(1) + register(1)
    "full_with_mint":     33,  # creative(8) + store(15) + mint(10)
}

# GCX token economy — aligned with PRICING_V2
GCX_BASE_RATE = 0.10  # $0.10 per GCX (Starter/Creator pack)
GCX_PER_DOLLAR = 10   # $1 = 10 GCX at base rate

# GCX packs (one-time purchase via Stripe or x402)
GCX_PACKS = [
    {"name": "Starter",  "price_usd": 5,   "gcx": 50,    "per_gcx": 0.100, "savings": "Base rate"},
    {"name": "Creator",  "price_usd": 10,  "gcx": 100,   "per_gcx": 0.100, "savings": "Base rate"},
    {"name": "Pro",      "price_usd": 50,  "gcx": 600,   "per_gcx": 0.083, "savings": "17% off"},
    {"name": "Studio",   "price_usd": 100, "gcx": 1600,  "per_gcx": 0.0625, "savings": "38% off"},
]

# Subscription tiers (monthly via Stripe)
SUBSCRIPTION_TIERS = {
    "free":    {"price_usd": 0,  "gcx_monthly": 50,   "per_gcx": 0.000,  "name": "Artisan"},
    "curator": {"price_usd": 19, "gcx_monthly": 200,  "per_gcx": 0.095,  "name": "Curator"},
    "studio":  {"price_usd": 49, "gcx_monthly": 600,  "per_gcx": 0.082,  "name": "Studio"},
    "gallery": {"price_usd": 99, "gcx_monthly": 1600, "per_gcx": 0.0625, "name": "Gallery"},
}

# Volume discounts for x402 agents (30-day rolling per wallet)
AGENT_VOLUME_TIERS = [
    {"min_spend_usd": 0,   "discount_pct": 0,  "label": "Standard"},
    {"min_spend_usd": 50,  "discount_pct": 10, "label": "Active"},
    {"min_spend_usd": 100, "discount_pct": 20, "label": "Pro"},
    {"min_spend_usd": 200, "discount_pct": 30, "label": "Studio"},
]

# Enterprise trigger: auto-outreach at this threshold
ENTERPRISE_TRIGGER_USD = 200


@dataclass
class Config:
    """Server configuration from environment."""

    # GCP
    gcp_project: str = os.getenv("GCP_PROJECT", "the-golden-codex-1111")
    gcp_region: str = os.getenv("GCP_REGION", "us-west1")

    # Firestore
    firestore_database: str = os.getenv("FIRESTORE_DATABASE", "golden-codex-database")

    # Backend service URLs (Golden Codex pipeline agents)
    sd35_url: str = os.getenv("SD35_SERVICE_URL", "https://sd35-l4-172867820131.us-east4.run.app")
    esrgan_url: str = os.getenv("ESRGAN_SERVICE_URL", "https://esrgan-l4-172867820131.us-central1.run.app")
    nova_url: str = os.getenv("NOVA_SERVICE_URL", "https://nova-agent-172867820131.us-west1.run.app")
    atlas_url: str = os.getenv("ATLAS_SERVICE_URL", "https://atlas-agent-172867820131.us-west1.run.app")
    archivus_url: str = os.getenv("ARCHIVUS_SERVICE_URL", "https://archivus-agent-172867820131.us-west1.run.app")
    mintra_url: str = os.getenv("MINTRA_SERVICE_URL", "https://mintra-agent-172867820131.us-west1.run.app")
    data_portal_url: str = os.getenv("DATA_PORTAL_URL", "https://data-portal-172867820131.us-west1.run.app")

    # Storage
    archive_bucket: str = os.getenv("ARCHIVE_BUCKET", "codex-archive-bucket")
    intake_bucket: str = os.getenv("INTAKE_BUCKET", "codex-intake-bucket")

    # x402 payment
    x402_wallet: str = os.getenv("X402_WALLET", "0xFE141943a93c184606F3060103D975662327063B")
    x402_chain: str = os.getenv("X402_CHAIN", "base")  # Base L2

    # Base L2 minting (Aeternum Collection)
    base_rpc_url: str = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
    base_contract_address: str = os.getenv("BASE_CONTRACT_ADDRESS", "")
    minter_private_key: str = os.getenv("MINTER_PRIVATE_KEY", "")  # From GCP Secret Manager

    # Stripe
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")

    # Server
    port: int = int(os.getenv("PORT", "8080"))
    host: str = os.getenv("HOST", "0.0.0.0")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Admin panel
    admin_secret: str = os.getenv("ADMIN_SECRET", "")

    # OAuth 2.1
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    oauth_issuer: str = os.getenv("OAUTH_ISSUER", "https://studiomcphub.com")

    # Tool profile: "full" = all 32 tools, "directory" = Anthropic-safe subset (no generation/minting)
    tool_profile: str = os.getenv("TOOL_PROFILE", "full")

    # MCP Server metadata
    server_name: str = "StudioMCPHub"
    server_version: str = "0.5.0"
    server_description: str = (
        "Creative AI tools, compliance infrastructure, and museum art datasets "
        "for autonomous agents. C2PA provenance, EU AI Act compliance, ESRGAN upscaling, "
        "background removal, mockups, color conversion, print prep, vectorization, "
        "watermarking, metadata enrichment, and 53K+ museum artworks."
    )


config = Config()


# CSO interim 2026-10-29 (REVISIT #69): a wallet address is an unauthenticated identity,
# so any 0x+40-hex string minted free GCX. The welcome grant is 0 until register proves
# ownership (EIP-191 signature). Restore a grant only together with that proof.
WELCOME_BONUS_GCX = 0
