"""
Clause extraction engine.

Two modes:
  1. Regex/heuristic mode (default, always available, no API key needed).
  2. LLM mode (optional) - if an ANTHROPIC_API_KEY is configured, contracts
     are sent to Claude for higher-accuracy structured extraction, with the
     regex pass kept as a fallback / cross-check.

Both modes populate the same `Contract` dataclass so the rest of the app
doesn't care which one ran.
"""

import re
import os
import json
from datetime import datetime, timedelta
from dateutil import parser as dateparser

from models import Contract

# --------------------------------------------------------------------------
# Regex patterns
# --------------------------------------------------------------------------

DATE_PATTERN = re.compile(
    r"""(
        (?:January|February|March|April|May|June|July|August|September|October|November|December)
        \s+\d{1,2},?\s+\d{4}
        |
        \d{1,2}/\d{1,2}/\d{2,4}
        |
        \d{4}-\d{2}-\d{2}
        |
        \d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}
    )""",
    re.IGNORECASE | re.VERBOSE,
)

AUTO_RENEW_PATTERN = re.compile(
    r"(automatically\s+renew|auto[-\s]?renew|shall\s+renew|will\s+renew|renews?\s+automatically)",
    re.IGNORECASE,
)

NO_AUTO_RENEW_PATTERN = re.compile(
    r"(shall\s+not\s+renew|will\s+not\s+automatically\s+renew|does\s+not\s+automatically\s+renew)",
    re.IGNORECASE,
)

NOTICE_PATTERN = re.compile(
    r"notice.{0,80}?\(?\s*(\d{1,3})\s*\)?\s*(calendar\s+days|business\s+days|calendar\s+day|business\s+day|days|day)",
    re.IGNORECASE,
)

NOTICE_PATTERN_ALT = re.compile(
    r"\(?\s*(\d{1,3})\s*\)?\s*(calendar\s+days|business\s+days|calendar\s+day|business\s+day|days|day)\s*(?:\'|’)?s?\s*(?:prior\s+)?(?:written\s+)?notice",
    re.IGNORECASE,
)

TERM_END_PATTERN = re.compile(
    r"\b(?:term|agreement|contract)\b.{0,80}?\b(?:end(?:s|ing)?|expir\w*|terminat\w*|through|until)\b.{0,60}?"
    + DATE_PATTERN.pattern,
    re.IGNORECASE | re.VERBOSE,
)

PRICE_PATTERN = re.compile(
    r"""(?:USD\s*)?\$\s?([\d,]+(?:\.\d{2})?)\s*
        (?:
            (?:per|/)\s*(year|annum|annually|month|monthly|quarter|quarterly|user|seat)
        )?
    """,
    re.IGNORECASE | re.VERBOSE,
)

VENDOR_HINT_PATTERN = re.compile(
    r"(?:between|by and between)\s+([A-Z][A-Za-z0-9&.,\-\s]{2,60}?)\s+(?:\(|and|,)",
)

VENDOR_LABEL_PATTERN = re.compile(
    r"^\s*vendor\s*:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _find_sentences_with(text: str, pattern: re.Pattern, max_results=3):
    sentences = SENTENCE_SPLIT.split(text)
    hits = []
    for s in sentences:
        if pattern.search(s):
            hits.append(s.strip())
            if len(hits) >= max_results:
                break
    return hits


def _parse_date_safe(raw: str):
    try:
        dt = dateparser.parse(raw, fuzzy=True, default=datetime(datetime.now().year, 1, 1))
        return dt.date().isoformat()
    except Exception:
        return None


def _guess_vendor(text: str, filename: str) -> str:
    m = VENDOR_LABEL_PATTERN.search(text)
    if m:
        candidate = m.group(1).strip().strip(",")
        if 2 < len(candidate) < 60:
            return candidate
    m = VENDOR_HINT_PATTERN.search(text)
    if m:
        candidate = m.group(1).strip().strip(",")
        if 2 < len(candidate) < 60:
            return candidate
    # fallback: filename without extension, cleaned up
    base = re.sub(r"\.(pdf|docx|txt|md)$", "", filename, flags=re.IGNORECASE)
    base = re.sub(r"[_\-]+", " ", base).strip()
    return base.title() if base else "Unknown Vendor"


def _notice_days(text: str):
    for pat in (NOTICE_PATTERN, NOTICE_PATTERN_ALT):
        m = pat.search(text)
        if m:
            try:
                days = int(m.group(1))
                unit = m.group(2).lower()
                if "business" in unit:
                    # rough conversion to calendar days for consistent math
                    days = int(round(days * 7 / 5))
                return days
            except Exception:
                continue
    return None


def _extract_price(text: str):
    matches = PRICE_PATTERN.findall(text)
    if not matches:
        return "", None, ""
    # pick the largest dollar figure found as the likely headline price
    best = None
    best_period = ""
    for amount_str, period in matches:
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            continue
        if best is None or amount > best:
            best = amount
            best_period = period.lower() if period else ""
    sentences = _find_sentences_with(text, re.compile(r"\$\s?[\d,]+"), max_results=2)
    price_text = " | ".join(sentences)
    return price_text, best, best_period


def _extract_end_date(text: str):
    # Prefer an explicit term/expiry clause. TERM_END_PATTERN itself ends in
    # DATE_PATTERN, so the date we want is the LAST date inside the match
    # (not just the first date in the sentence, which may be a start date).
    m = TERM_END_PATTERN.search(text)
    if m:
        matched = m.group(0)
        dates_in_match = DATE_PATTERN.findall(matched)
        if dates_in_match:
            return _parse_date_safe(dates_in_match[-1]), matched
    # fallback: any date near the word "renewal" or "expiration"
    for s in _find_sentences_with(text, re.compile(r"(renewal|expir|end date)", re.IGNORECASE), max_results=3):
        dates_in_sentence = DATE_PATTERN.findall(s)
        if dates_in_sentence:
            return _parse_date_safe(dates_in_sentence[-1]), s
    return None, ""


def regex_extract(filename: str, text: str) -> Contract:
    c = Contract()
    c.filename = filename
    c.vendor_name = _guess_vendor(text, filename)
    c.contract_title = filename

    end_date, end_sentence = _extract_end_date(text)
    c.end_date = end_date

    if AUTO_RENEW_PATTERN.search(text) and not NO_AUTO_RENEW_PATTERN.search(text):
        c.auto_renews = True
    elif NO_AUTO_RENEW_PATTERN.search(text):
        c.auto_renews = False
    else:
        c.auto_renews = None  # unknown

    renewal_sentences = _find_sentences_with(text, AUTO_RENEW_PATTERN, max_results=2)
    c.renewal_term_text = " | ".join(renewal_sentences) or end_sentence

    c.notice_period_days = _notice_days(text)

    price_text, amount, period = _extract_price(text)
    c.price_text = price_text
    c.price_amount = amount
    c.price_period = period

    if c.end_date and c.notice_period_days is not None:
        try:
            end_dt = datetime.fromisoformat(c.end_date)
            deadline = end_dt - timedelta(days=c.notice_period_days)
            c.cancellation_deadline = deadline.date().isoformat()
        except Exception:
            c.cancellation_deadline = None

    c.raw_text_excerpt = text[:600]
    c.extraction_method = "regex"
    return c


# --------------------------------------------------------------------------
# Optional LLM-assisted extraction (Claude)
# --------------------------------------------------------------------------

LLM_SYSTEM_PROMPT = """You are a contract analysis engine. Extract renewal-risk data from the
vendor/SaaS contract text the user provides. Respond with ONLY a single JSON object
(no prose, no markdown fences) with exactly these keys:

{
  "vendor_name": string,
  "contract_title": string,
  "start_date": "YYYY-MM-DD" or null,
  "end_date": "YYYY-MM-DD" or null,
  "auto_renews": true | false | null,
  "renewal_term_text": string (the sentence(s) describing the renewal terms, or ""),
  "notice_period_days": integer or null (how many calendar days' written notice is required to cancel / prevent auto-renewal),
  "price_text": string (sentence(s) describing pricing, or ""),
  "price_amount": number or null (the headline recurring price, numeric only),
  "price_currency": string (e.g. "USD"),
  "price_period": string ("year", "month", "one-time", or ""),
  "notes": string (anything unusual worth flagging, e.g. price escalation clauses, or "")
}

If a field cannot be determined from the text, use null (or "" for strings). Never invent dates or numbers."""


def llm_extract(filename: str, text: str, api_key: str, model: str = "claude-sonnet-4-6") -> Contract:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    truncated = text[:15000]  # keep prompt reasonable

    resp = client.messages.create(
        model=model,
        max_tokens=1000,
        system=LLM_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Filename: {filename}\n\nContract text:\n{truncated}"}],
    )

    raw = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(json)?", "", raw).rstrip("`").strip()

    data = json.loads(raw)

    c = Contract()
    c.filename = filename
    c.vendor_name = data.get("vendor_name") or _guess_vendor(text, filename)
    c.contract_title = data.get("contract_title") or filename
    c.start_date = data.get("start_date")
    c.end_date = data.get("end_date")
    c.auto_renews = data.get("auto_renews")
    c.renewal_term_text = data.get("renewal_term_text", "")
    c.notice_period_days = data.get("notice_period_days")
    c.price_text = data.get("price_text", "")
    c.price_amount = data.get("price_amount")
    c.price_currency = data.get("price_currency") or "USD"
    c.price_period = data.get("price_period", "")
    c.notes = data.get("notes", "")
    c.raw_text_excerpt = text[:600]
    c.extraction_method = "llm"

    if c.end_date and c.notice_period_days is not None:
        try:
            end_dt = datetime.fromisoformat(c.end_date)
            deadline = end_dt - timedelta(days=c.notice_period_days)
            c.cancellation_deadline = deadline.date().isoformat()
        except Exception:
            c.cancellation_deadline = None

    return c


def extract_contract(filename: str, text: str, use_llm: bool = False, api_key: str = None) -> Contract:
    """Main entry point. Falls back to regex extraction if LLM mode fails or is unavailable."""
    if use_llm and api_key:
        try:
            return llm_extract(filename, text, api_key)
        except Exception as e:
            fallback = regex_extract(filename, text)
            fallback.notes = f"(LLM extraction failed, used regex fallback: {e})"
            return fallback
    return regex_extract(filename, text)
