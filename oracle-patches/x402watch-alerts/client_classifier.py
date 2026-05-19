"""
Six-tier MCP / HTTP client classifier — drop-in for x402watch.

Permanent location on Oracle: /home/ubuntu/x402watch/app/client_classifier.py

The classifier looks at a request's User-Agent + (optionally) headers and
returns a `(tier, label, emoji, action)` tuple. The tier drives alert
routing in telegram_notify.py:

  TIER 1  PAID_USER         💎  immediate alert (real paid call, X-PAYMENT present)
  TIER 2  AI_CLIENT         🔵  immediate alert (Cursor / Claude Desktop / etc.)
  TIER 3  AGENT_FRAMEWORK   🟡  immediate alert (LangChain / AutoGen / CrewAI / …)
  TIER 4  DIRECTORY_BOT     ⚪  daily summary only (Smithery / Glama / x402scan / …)
  TIER 5  GENERIC_HTTP      ⚪  daily summary only (python-requests / curl / …)
  TIER 6  SUSPECT           🔴  immediate + burst rate-limit (unfamiliar UA + high freq)

A 7th out-of-band bucket — `UNKNOWN` — fires a single ❓ alert per UA per
24h, so the first time an unrecognised client shows up Moa hears about it
and can decide whether to add a pattern.

This is a clean-room implementation in the spirit of KR Crypto's
client_classifier.py. KR Crypto's 45+ pattern list is the authoritative
catalogue; this file covers the ~30 most common patterns and is easy to
merge / extend. Sharing one classifier across both services via PYTHONPATH
is a fine future move if the catalogues converge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ─── Public types ────────────────────────────────────────────────────
@dataclass(frozen=True)
class Classification:
    tier: int                     # 1..6
    label: str                    # short human label e.g. "Cursor IDE"
    emoji: str                    # one-char emoji for the alert prefix
    action: str                   # "immediate" | "daily" | "first_only"
    pattern: Optional[str] = None # which pattern matched, for debug


# ─── Tier patterns ───────────────────────────────────────────────────
# Order matters within a tier — earliest match wins. Across tiers the
# rule is: paid-user wins, then AI client, then framework, then bot,
# then generic. Suspect only fires when nothing else matched + the
# request comes from a freshly seen UA at high frequency (handled in
# telegram_notify.py, not here).

# (label, regex against UA — case-insensitive)
TIER2_AI_CLIENT_PATTERNS: list[tuple[str, str]] = [
    ("Cursor IDE",            r"\bcursor\b"),
    ("Claude Desktop",        r"\bclaude[-_ ]desktop\b|\banthropic[-_ ]desktop\b"),
    ("Claude Code",           r"\bclaude[-_ ]code\b"),
    ("ChatGPT Desktop",       r"\bchatgpt[-_ ]desktop\b|\bopenai[-_ ]desktop\b"),
    ("Continue.dev",          r"\bcontinue(\.dev|/[0-9])"),
    ("Codeium",               r"\bcodeium\b"),
    ("Cody (Sourcegraph)",    r"\bcody\b|\bsourcegraph\b"),
    ("Bolt.new",              r"\bbolt(\.new)?/"),
    ("Aider",                 r"\baider/"),
    ("Zed Editor",            r"\bzed/"),
    ("Anthropic SDK",         r"\banthropic-ai|anthropic-sdk\b"),
    ("OpenAI SDK",            r"\bopenai-python\b|\bopenai-node\b|\bopenai/"),
    ("Mistral client",        r"\bmistral(-?client|-?ai)\b"),
    ("Perplexity",            r"\bperplexity\b"),
]

TIER3_AGENT_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    ("LangChain",             r"\blangchain\b"),
    ("LangGraph",             r"\blanggraph\b"),
    ("LlamaIndex",            r"\bllamaindex\b|\bllama[-_ ]index\b"),
    ("AutoGen",               r"\bautogen\b|\bmicrosoft[-_ ]autogen\b"),
    ("CrewAI",                r"\bcrewai\b|\bcrew[-_ ]ai\b"),
    ("Haystack",              r"\bhaystack/"),
    ("Semantic Kernel",       r"\bsemantic[-_ ]kernel\b"),
    ("DSPy",                  r"\bdspy/"),
    ("Phidata / Agno",        r"\bphidata\b|\bagno\b"),
    ("Letta / MemGPT",        r"\bletta\b|\bmemgpt\b"),
    ("Pydantic AI",           r"\bpydantic[-_ ]ai\b"),
    ("LiveKit Agents",        r"\blivekit[-_ ]agents\b"),
    ("Vercel AI SDK",         r"\bai-sdk\b|\bvercel-ai\b"),
]

TIER4_DIRECTORY_BOT_PATTERNS: list[tuple[str, str]] = [
    ("Smithery scanner",      r"\bsmithery\b"),
    ("Glama scanner",         r"\bglama\b"),
    ("MCP Registry",          r"\bmcp[-_ ]registry\b|\bregistry\.modelcontextprotocol\b"),
    ("Coinbase x402 / Bazaar",r"\bcoinbase[-_ ]x402\b|\bbazaar(bot)?\b"),
    ("AgentCash discovery",   r"\bagentcash\b"),
    ("x402scan",              r"\bx402scan\b"),
    ("x402-surface-check",    r"\bx402[-_ ]surface[-_ ]check\b"),
    ("Anthropic claude.ai bot", r"\bclaude\.ai\b|\banthropic\.com\b"),
    ("OpenAI GPTBot",         r"\bgptbot\b|\boai-searchbot\b|\bchatgpt-user\b"),
    ("Common SEO crawlers",   r"\bgooglebot\b|\bbingbot\b|\bduckduckbot\b|\byandexbot\b"),
    ("Diffbot",               r"\bdiffbot\b"),
    ("CommonCrawl",           r"\bccbot\b|\bcommon[-_ ]crawl\b"),
]

TIER5_GENERIC_HTTP_PATTERNS: list[tuple[str, str]] = [
    ("python-requests",       r"\bpython-requests/"),
    ("httpx",                 r"\bpython-httpx/|\bhttpx/"),
    ("aiohttp",               r"\baiohttp/"),
    ("urllib3",               r"\bpython-urllib3/|\burllib3/"),
    ("curl",                  r"^curl/"),
    ("wget",                  r"\bwget/"),
    ("Node fetch / undici",   r"\bnode-fetch/|\bundici/"),
    ("axios",                 r"\baxios/"),
    ("Go http client",        r"^Go-http-client/"),
    ("Rust reqwest",          r"\breqwest/"),
    ("Ruby Faraday",          r"\bfaraday/|\bruby/"),
    ("Java HttpClient",       r"\bjava/|\bapache-httpclient/"),
    ("Postman / Insomnia",    r"\bpostman\b|\binsomnia\b"),
]

# Compiled once at import.
def _compile(group: list[tuple[str, str]]) -> list[tuple[str, re.Pattern]]:
    return [(label, re.compile(pat, re.IGNORECASE)) for label, pat in group]

_T2 = _compile(TIER2_AI_CLIENT_PATTERNS)
_T3 = _compile(TIER3_AGENT_FRAMEWORK_PATTERNS)
_T4 = _compile(TIER4_DIRECTORY_BOT_PATTERNS)
_T5 = _compile(TIER5_GENERIC_HTTP_PATTERNS)


# ─── Classifier ──────────────────────────────────────────────────────
def classify(
    user_agent: str = "",
    *,
    has_x_payment: bool = False,
    headers: Optional[dict] = None,
) -> Classification:
    """Return the classification for a request.

    - `has_x_payment=True` short-circuits to Tier 1 PAID_USER regardless
      of UA (the payment itself is the strongest signal).
    - `headers` is currently only used to detect MCP transport hints
      (`x-mcp-session-id`, etc.) but is reserved for future signals.
    """
    if has_x_payment:
        return Classification(tier=1, label="Paid x402 user", emoji="💎",
                              action="immediate", pattern="x-payment-header")

    ua = (user_agent or "").strip()
    if not ua:
        # Empty UA on its own isn't suspect — many ASGI clients drop it.
        # Mark as unknown so the first-seen rule in telegram_notify fires.
        return Classification(tier=0, label="unknown (no UA)", emoji="❓",
                              action="first_only", pattern="empty-ua")

    for label, rx in _T2:
        if rx.search(ua):
            return Classification(tier=2, label=label, emoji="🔵",
                                  action="immediate", pattern=rx.pattern)
    for label, rx in _T3:
        if rx.search(ua):
            return Classification(tier=3, label=label, emoji="🟡",
                                  action="immediate", pattern=rx.pattern)
    for label, rx in _T4:
        if rx.search(ua):
            return Classification(tier=4, label=label, emoji="⚪",
                                  action="daily", pattern=rx.pattern)
    for label, rx in _T5:
        if rx.search(ua):
            return Classification(tier=5, label=label, emoji="⚪",
                                  action="daily", pattern=rx.pattern)
    # Nothing matched — caller can promote to Tier 6 (suspect) based on
    # burst rate; default action is "first_only" so unknown UAs surface
    # exactly once per 24h.
    return Classification(tier=0, label=f"unknown ({ua[:60]})", emoji="❓",
                          action="first_only", pattern=None)


def promote_to_suspect(c: Classification) -> Classification:
    """Caller can promote an Unknown / Tier-5 classification to Tier 6
    SUSPECT when its UA has driven > N requests in the last hour. We
    don't track rates here — that lives in the alert layer."""
    if c.tier in (0, 5):
        return Classification(tier=6, label=f"suspect: {c.label}", emoji="🔴",
                              action="immediate", pattern=c.pattern)
    return c


# ─── Convenience for free-text contexts (logs, daily summaries) ──────
def short_summary(c: Classification) -> str:
    """One-line summary for log lines and the daily KST 09:00 digest."""
    return f"{c.emoji} T{c.tier} {c.label}"


__all__ = [
    "Classification",
    "classify",
    "promote_to_suspect",
    "short_summary",
    "TIER2_AI_CLIENT_PATTERNS",
    "TIER3_AGENT_FRAMEWORK_PATTERNS",
    "TIER4_DIRECTORY_BOT_PATTERNS",
    "TIER5_GENERIC_HTTP_PATTERNS",
]
