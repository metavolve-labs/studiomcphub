# StudioMCPHub

**Creative AI tools and art datasets for autonomous agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Streamable_HTTP-blue)](https://studiomcphub.com/.well-known/mcp.json)
[![Glama](https://glama.ai/mcp/servers/badge)](https://glama.ai/mcp/servers/@codex-curator/studiomcphub)
[![StudioMCPHub on AI Agents Listing](https://aiagentslisting.com/studiomcphub/badge.svg?claim=8513e429a7c000a605d965609c9d8ab6)](https://aiagentslisting.com/mcp/studiomcphub)

StudioMCPHub is a production MCP server offering 32 tools (18 free): image generation, upscaling, background removal, product mockups, CMYK conversion, print-ready PDF, SVG vectorization, invisible watermarking, AI metadata enrichment, provenance registration, permanent Arweave storage, NFT minting, and access to 53,000+ museum artworks from Alexandria Aeternum. Agents pay per call with x402 USDC on Base L2 — no API keys, no accounts, no sign-up.

## Quick Start

**One-click install for Cursor:**

[Install in Cursor](https://cursor.directory/mcp?install=cursor://anysphere.cursor-deeplink/mcp/install?name=StudioMCPHub&config=eyJ1cmwiOiAiaHR0cHM6Ly9zdHVkaW9tY3BodWIuY29tL21jcCIsICJ0cmFuc3BvcnQiOiAic3RyZWFtYWJsZS1odHRwIn0=)

Or add to any MCP client config:

```json
{
  "mcpServers": {
    "studiomcphub": {
      "url": "https://studiomcphub.com/mcp",
      "transport": "streamable-http"
    }
  }
}
```

Then call `search_tools` to discover available tools without loading all 32 schemas:

```
search_tools({ "category": "all" })
```

## Tools

### Discovery (FREE)

| Tool | Description |
|------|-------------|
| `search_tools` | Discover tools by category, price, or keyword (~98% token savings) |
| `get_tool_schema` | Get full JSON Schema + examples for a specific tool |

### Creative Pipeline

| Tool | Price | Description |
|------|-------|-------------|
| `generate_image` | $0.20 | SD 3.5 Large text-to-image on NVIDIA L4 GPU |
| `upscale_image` | $0.20 | Real-ESRGAN 4x super-resolution |
| `enrich_metadata` | $0.20 | Gemini-powered 111-field Golden Codex analysis |
| `infuse_metadata` | $0.10 | ExifTool XMP/IPTC/C2PA metadata embedding |
| `register_hash` | $0.10 | 256-bit perceptual hash with LSH band indexing |
| `store_permanent` | $1.50 | Arweave L1 permanent immutable storage |
| `mint_nft` | $1.00 | Polygon NFT with on-chain provenance link |
| `verify_provenance` | FREE | Perceptual hash lookup against Aegis index |
| `full_pipeline` | $0.50 | All stages in one call |

### Alexandria Aeternum Dataset

53,000+ public domain artworks from 7 world-class institutions.

| Tool | Price | Description |
|------|-------|-------------|
| `search_artworks` | FREE | Search by keyword, artist, period, or style |
| `get_artwork` | $0.10 | Human-sourced metadata + signed image URL |
| `get_artwork_oracle` | $0.20 | 111-field NEST deep visual analysis |
| `batch_download` | $5.00 | Bulk metadata + images (min 100) |
| `compliance_manifest` | FREE | AB 2013 + EU AI Act compliance docs |

## Payment

**x402 (recommended for agents)**: Pay per call with USDC on Base L2. Server returns HTTP 402 with payment instructions. No account needed.

**Stripe**: Traditional card payment per call with API key.

**GCX Credits**: Pre-purchase tokens at volume discounts — $5 (50 GCX), $50 (600 GCX, 17% off), $100 (1600 GCX, 38% off).

### Volume Discounts

Automatic per-wallet discounts based on 30-day rolling spend:

| Tier | Spend | Discount |
|------|-------|----------|
| Standard | $0–49 | 0% |
| Active | $50–99 | 10% |
| Pro | $100–199 | 20% |
| Studio | $200+ | 30% |

Check your tier: `GET https://studiomcphub.com/api/agent/tier/{wallet_address}`

### Loyalty

Every paid call earns 5% credit-back as loyalty GCX. No sign-up, no expiration.

## Discovery Endpoints

| Endpoint | Description |
|----------|-------------|
| `https://studiomcphub.com/mcp` | MCP Streamable HTTP endpoint |
| `https://studiomcphub.com/.well-known/mcp.json` | MCP server discovery |
| `https://studiomcphub.com/.well-known/agent.json` | A2A Agent Card |
| `https://studiomcphub.com/llms.txt` | LLM-readable documentation |
| `https://studiomcphub.com/pricing` | Pricing page |

## Self-Hosting

```bash
git clone https://github.com/codex-curator/studiomcphub.git
cd studiomcphub
pip install -r requirements.txt
# Set required environment variables (see .env.example)
gunicorn --bind 0.0.0.0:8080 --workers 2 --threads 4 src.mcp_server.server:app
```

Or with Docker:

```bash
docker build -t studiomcphub .
docker run -p 8080:8080 studiomcphub
```

## Research

Alexandria Aeternum metadata density improves VLM visual perception by +25.5% and semantic coverage by +160.3%. See [The Density Imperative](https://doi.org/10.5281/zenodo.18667735).

## Links

- [Golden Codex Studio](https://golden-codex.com)
- [HuggingFace Dataset](https://huggingface.co/datasets/Metavolve-Labs/alexandria-aeternum-genesis)
- [Metavolve Labs](https://metavolve.com)

## License

[MIT](LICENSE) — Metavolve Labs, Inc.
