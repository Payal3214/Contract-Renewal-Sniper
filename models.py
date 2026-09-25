"""
Data model for a parsed contract record.
Kept dependency-free (plain dataclass) so it can be reused by the
extractor, the risk engine, the db layer and the Streamlit UI.
"""

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


@dataclass
class Contract:
    id: Optional[int] = None                 # DB primary key (None until saved)
    filename: str = ""
    vendor_name: str = ""
    contract_title: str = ""

    # --- Extracted clauses -------------------------------------------------
    start_date: Optional[str] = None          # ISO "YYYY-MM-DD" or None
    end_date: Optional[str] = None            # current term end / renewal date
    auto_renews: Optional[bool] = None        # True / False / None (unknown)
    renewal_term_text: str = ""               # raw sentence describing renewal
    notice_period_days: Optional[int] = None  # how many days' notice required to cancel
    cancellation_deadline: Optional[str] = None  # computed: end_date - notice_period_days
    price_text: str = ""                      # raw sentence(s) describing price
    price_amount: Optional[float] = None      # best-guess numeric amount
    price_currency: str = "USD"
    price_period: str = ""                    # "year" / "month" / "one-time" / ""

    # --- Meta ---------------------------------------------------------------
    raw_text_excerpt: str = ""                # short excerpt for audit/debug
    extraction_method: str = "regex"          # "regex" or "llm"
    notes: str = ""
    status: str = "active"                    # active | cancelled | renewed | archived
    created_at: Optional[str] = None

    def to_dict(self):
        return asdict(self)


RISK_LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN", "PAST"]

RISK_COLORS = {
    "CRITICAL": "#e53935",
    "HIGH": "#fb8c00",
    "MEDIUM": "#fdd835",
    "LOW": "#43a047",
    "UNKNOWN": "#9e9e9e",
    "PAST": "#6d4c41",
}
