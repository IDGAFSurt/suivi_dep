"""PDF extraction utilities.

This module handles low-level PDF text extraction with pdfplumber.
"""

from __future__ import annotations

from pathlib import Path
import logging
from typing import List

import pdfplumber

logger = logging.getLogger(__name__)


def extract_raw_text_by_page(pdf_path: Path) -> List[str]:
    """Extract raw text from a PDF, page by page.

    Args:
        pdf_path: Path to PDF file.

    Returns:
        List of text blocks (one item per page).
    """
    pages_text: List[str] = []

    logger.info("Opening PDF: %s", pdf_path)
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            pages_text.append(page_text)
            logger.debug("Page %s extracted (%s chars)", page_index, len(page_text))

    logger.info("PDF extraction complete: %s pages", len(pages_text))
    return pages_text


def save_debug_extraction(pdf_path: Path, output_path: Path) -> Path:
    """Extract raw text and save a debug file.

    Also logs each extracted line to console to help parsing iterations.

    Args:
        pdf_path: PDF to read.
        output_path: Destination text file.

    Returns:
        Path to the generated debug file.
    """
    pages_text = extract_raw_text_by_page(pdf_path)

    logger.info("Writing debug extraction to: %s", output_path)
    with output_path.open("w", encoding="utf-8") as f:
        for page_number, text in enumerate(pages_text, start=1):
            f.write(f"===== PAGE {page_number} =====\n")
            f.write(text)
            f.write("\n\n")

            # Print line-by-line in console for quick debugging.
            logger.debug("----- PAGE %s -----", page_number)
            for line in text.splitlines():
                logger.debug(line)

    return output_path
