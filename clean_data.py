"""Temporary parsing / cleaning layer.

This version is tailored for the current bank statement structure while keeping
the code easy to extend with additional banking keywords.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

# Real statement line format (example):
# 08.10 08.10 Virement Vir Inst vers gar foot 16,00
#  ^op_date ^value_date                ^amount (always last token)
#
# Amount accepts optional thousands groups separated by spaces:
# - 16,00
# - 135,00
# - 1 000,00
LINE_PATTERN = re.compile(
    r"^(?P<op_date>\d{2}\.\d{2})\s+(?P<value_date>\d{2}\.\d{2})\s+(?P<label>.+?)\s+(?P<amount>\d{1,3}(?:\s\d{3})*[\.,]\d{2}|\d+[\.,]\d{2})$"
)

# Characters sometimes leaked by PDF text extraction and not part of content.
TRAILING_NOISE_CHARS = "¨"


@dataclass(frozen=True)
class KeywordRule:
    """Business rule attached to a banking keyword prefix.

    Attributes:
        prefix: Label prefix to match.
        force_negative: If True, amount is always forced negative.
        strip_prefix_for_tiers: If True, tiers is the remaining label after prefix.
    """

    prefix: str
    force_negative: bool
    strip_prefix_for_tiers: bool = True


# Ordered from most specific to most generic to avoid ambiguous matches.
KEYWORD_RULES: List[KeywordRule] = [
    KeywordRule(prefix="Virement Vir Inst vers", force_negative=True),
    KeywordRule(prefix="Virement Web", force_negative=True),
    KeywordRule(prefix="Carte X1840", force_negative=True),
    KeywordRule(prefix="Prlv", force_negative=True),
    KeywordRule(prefix="Cotis", force_negative=True),
    # "Virement" alone (or as start of label) is considered incoming money.
    KeywordRule(prefix="Virement", force_negative=False),
]


def _clean_raw_line(raw_line: str) -> str:
    """Normalize an extracted line before applying parser regex.

    - Removes trailing spaces.
    - Removes known parasitic trailing characters (e.g. "¨").
    - Trims again to avoid leftover spaces after cleanup.
    """
    cleaned = raw_line.rstrip()
    cleaned = cleaned.rstrip(TRAILING_NOISE_CHARS).rstrip()
    return cleaned


def _parse_statement_date(op_date_str: str, now: datetime) -> date:
    """Rebuild operation date using current year from system time."""
    return datetime.strptime(f"{op_date_str}.{now.year}", "%d.%m.%Y").date()


def _parse_amount(raw_amount: str) -> float:
    """Convert amount text to Python float.

    Handles thousands spaces and French decimal comma.
    Examples:
    - "16,00" -> 16.00
    - "1 000,00" -> 1000.00
    """
    normalized = raw_amount.replace(" ", "").replace(".", "").replace(",", ".")
    return float(normalized)


def _extract_tiers(label: str, rule: KeywordRule | None) -> str:
    """Extract tiers from label using the matched keyword rule."""
    if rule and rule.strip_prefix_for_tiers and label.startswith(rule.prefix):
        remainder = label[len(rule.prefix) :].strip(" -")
        if remainder:
            return remainder

    # Fallback: keep the full label if no rule matched or no remainder exists.
    return label.strip() or "INCONNU"


def _apply_amount_sign(amount: float, rule: KeywordRule | None) -> float:
    """Apply business sign rule: specific prefixes are expenses (negative)."""
    if rule and rule.force_negative:
        return -abs(amount)
    return abs(amount)


def _match_keyword_rule(label: str) -> KeywordRule | None:
    """Return the first matching keyword rule for the label, if any."""
    for rule in KEYWORD_RULES:
        if label.startswith(rule.prefix):
            return rule
    return None


def parse_operations_from_pages(pages_text: List[str], source_pdf: Path) -> pd.DataFrame:
    """Parse operations from extracted PDF text.

    Current strategy:
    - Clean extracted lines to remove known PDF parasitic trailing characters
    - Parse lines matching: DD.MM DD.MM <label> <amount>
    - Ignore the second date (value date)
    - Build operation date with current year
    - Determine tiers and amount sign through configurable keyword rules
    """
    operations: List[Dict[str, Any]] = []
    now = datetime.now()

    for page_idx, page_text in enumerate(pages_text, start=1):
        logger.debug("Parsing page %s", page_idx)

        for line_idx, raw_line in enumerate(page_text.splitlines(), start=1):
            line = _clean_raw_line(raw_line)
            if not line:
                logger.debug("[p%s:l%s] Ignored (empty after cleanup)", page_idx, line_idx)
                continue

            match = LINE_PATTERN.match(line)
            if not match:
                logger.debug(
                    "[p%s:l%s] Ignored (pattern mismatch) raw=%r cleaned=%r",
                    page_idx,
                    line_idx,
                    raw_line,
                    line,
                )
                continue

            op_date_str = match.group("op_date")
            # Kept for debugging context even if ignored by business logic.
            value_date_str = match.group("value_date")
            label = match.group("label").strip()
            raw_amount = match.group("amount")

            try:
                operation_date = _parse_statement_date(op_date_str, now)
                normalized_amount = _parse_amount(raw_amount)
            except ValueError as exc:
                logger.debug(
                    "[p%s:l%s] Ignored (date/amount parse error: %s) cleaned=%r",
                    page_idx,
                    line_idx,
                    exc,
                    line,
                )
                continue

            matched_rule = _match_keyword_rule(label)
            tiers = _extract_tiers(label, matched_rule)
            signed_amount = _apply_amount_sign(normalized_amount, matched_rule)

            rule_name = matched_rule.prefix if matched_rule else "<none>"
            logger.debug(
                "[p%s:l%s] Parsed op_date=%s value_date=%s rule=%s tiers=%s raw_amount=%s amount=%s",
                page_idx,
                line_idx,
                operation_date,
                value_date_str,
                rule_name,
                tiers,
                raw_amount,
                signed_amount,
            )

            operation_id_seed = f"{operation_date.isoformat()}|{label}|{signed_amount:.2f}|{source_pdf.name}"
            operation_id = sha1(operation_id_seed.encode("utf-8")).hexdigest()[:16]

            operations.append(
                {
                    "Date": operation_date,
                    "Tiers": tiers,
                    "Libellé brut": label,
                    "Montant": signed_amount,
                    "Source PDF": source_pdf.name,
                    "Date import": now.date(),
                    "ID opération": operation_id,
                }
            )

    df = pd.DataFrame(
        operations,
        columns=[
            "Date",
            "Tiers",
            "Libellé brut",
            "Montant",
            "Source PDF",
            "Date import",
            "ID opération",
        ],
    )

    logger.info("Parsed %s operations from %s page(s)", len(df), len(pages_text))
    return df