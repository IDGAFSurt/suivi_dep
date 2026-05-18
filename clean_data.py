"""Temporary parsing / cleaning layer.

This first version keeps parsing deliberately simple so it can be adapted after
reviewing debug_extraction.txt from real statements.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import List, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)


LINE_PATTERN = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<label>.+?)\s+(?P<amount>-?\d+[\.,]\d{2})$"
)


def parse_operations_from_pages(pages_text: List[str], source_pdf: Path) -> pd.DataFrame:
    """Parse operations from extracted text.

    Heuristic v1:
    - Each operation on one line
    - Starts with DD/MM/YYYY
    - Ends with amount (e.g. 123,45 or -123,45)

    Returns a DataFrame with final target columns.
    """
    operations: List[Dict[str, Any]] = []

    for page_idx, page_text in enumerate(pages_text, start=1):
        for raw_line in page_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = LINE_PATTERN.match(line)
            if not match:
                continue

            date_str = match.group("date")
            label = match.group("label").strip()
            amount_str = match.group("amount").replace(".", "").replace(",", ".")

            try:
                operation_date = datetime.strptime(date_str, "%d/%m/%Y").date()
                amount = float(amount_str)
            except ValueError:
                logger.debug("Skipped unparsable line: %s", line)
                continue

            # Temporary split: tier = first chunk before '-' if available.
            tiers_guess = label.split("-")[0].strip()
            tiers = tiers_guess if tiers_guess else "INCONNU"

            operation_id_seed = f"{operation_date.isoformat()}|{label}|{amount:.2f}|{source_pdf.name}"
            operation_id = sha1(operation_id_seed.encode("utf-8")).hexdigest()[:16]

            operations.append(
                {
                    "Date": operation_date,
                    "Tiers": tiers,
                    "Libellé brut": label,
                    "Montant": amount,
                    "Source PDF": source_pdf.name,
                    "Date import": datetime.now().date(),
                    "ID opération": operation_id,
                }
            )

        logger.debug("Page %s parsed; current ops=%s", page_idx, len(operations))

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

    logger.info("Parsed %s operations", len(df))
    return df
