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

# Extract statement date like DD-MM-YYYY from the PDF filename.
FILENAME_DATE_PATTERN = re.compile(r"\d{2}-\d{2}-(?P<year>\d{4})")
# Parasite date often added at the end of card labels (example: "... 11/10").
TRAILING_LABEL_DATE_PATTERN = re.compile(r"\s+\d{2}/\d{2}$")

# Characters sometimes leaked by PDF text extraction and not part of content.
TRAILING_NOISE_CHARS = "¨"


@dataclass(frozen=True)
class KeywordRule:
    """Business rule attached to a banking keyword prefix."""

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
    """Normalize an extracted line before applying parser regex."""
    cleaned = raw_line.rstrip()
    cleaned = cleaned.rstrip(TRAILING_NOISE_CHARS).rstrip()
    return cleaned


def _resolve_operation_year(source_pdf: Path, now: datetime) -> int:
    """Resolve year from filename date DD-MM-YYYY, fallback to current year."""

    print("DEBUG filename =", source_pdf.name)

    match = FILENAME_DATE_PATTERN.search(source_pdf.name)

    print("DEBUG regex pattern =", FILENAME_DATE_PATTERN.pattern)
    print("DEBUG match =", match)

    if match:
        print("DEBUG extracted year =", match.group("year"))

        year = int(match.group("year"))

        logger.info("Year resolved from PDF filename: %s (file=%s)", year, source_pdf.name)

        return year

    fallback_year = now.year

    print("DEBUG fallback triggered")

    logger.warning(
        "No DD-MM-YYYY date found in PDF filename. Falling back to current year %s (file=%s)",
        fallback_year,
        source_pdf.name,
    )

    return fallback_year


def _parse_statement_date(op_date_str: str, year: int) -> date:
    """Rebuild operation date using resolved statement year."""
    return datetime.strptime(f"{op_date_str}.{year}", "%d.%m.%Y").date()


def _parse_amount(raw_amount: str) -> float:
    """Convert amount text to Python float."""
    normalized = raw_amount.replace(" ", "").replace(".", "").replace(",", ".")
    return float(normalized)


def _remove_trailing_label_date(text: str) -> str:
    """Remove parasite ending date token JJ/MM from label/tiers only."""
    return TRAILING_LABEL_DATE_PATTERN.sub("", text).strip()


def _extract_tiers(label: str, rule: KeywordRule | None) -> str:
    """Extract tiers from label using the matched keyword rule."""
    if rule and rule.strip_prefix_for_tiers and label.startswith(rule.prefix):
        remainder = label[len(rule.prefix) :].strip(" -")
        tiers = _remove_trailing_label_date(remainder)
        if tiers:
            return tiers

    # Fallback: keep the full label (also cleaned from trailing parasite date).
    fallback = _remove_trailing_label_date(label.strip())
    return fallback or "INCONNU"


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
    """Parse operations from extracted PDF text."""
    operations: List[Dict[str, Any]] = []
    now = datetime.now()
    operation_year = _resolve_operation_year(source_pdf, now)
    print("DEBUG source_pdf =", source_pdf)
    print("DEBUG source_pdf.name =", source_pdf.name)
    print("DEBUG operation_year =", operation_year)

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
            value_date_str = match.group("value_date")
            raw_label = match.group("label").strip()
            clean_label = _remove_trailing_label_date(raw_label)
            raw_amount = match.group("amount")

            try:
                operation_date = _parse_statement_date(op_date_str, operation_year)
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

            matched_rule = _match_keyword_rule(clean_label)
            tiers = _extract_tiers(clean_label, matched_rule)
            signed_amount = _apply_amount_sign(normalized_amount, matched_rule)

            rule_name = matched_rule.prefix if matched_rule else "<none>"
            logger.debug(
                "[p%s:l%s] Parsed op_date=%s value_date=%s year=%s rule=%s tiers=%s raw_label=%r label=%r raw_amount=%s amount=%s",
                page_idx,
                line_idx,
                operation_date,
                value_date_str,
                operation_year,
                rule_name,
                tiers,
                raw_label,
                clean_label,
                raw_amount,
                signed_amount,
            )

            operation_id_seed = f"{operation_date.isoformat()}|{clean_label}|{signed_amount:.2f}|{source_pdf.name}"
            operation_id = sha1(operation_id_seed.encode("utf-8")).hexdigest()[:16]

            operations.append(
                {
                    "Date": operation_date,
                    "Tiers": tiers,
                    "Libellé brut": clean_label,
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

    logger.info(
        "Parsed %s operations from %s page(s) using year %s",
        len(df),
        len(pages_text),
        operation_year,
    )
    return df