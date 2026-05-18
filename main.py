"""Application entry point."""

from __future__ import annotations

import logging
import tkinter as tk

from gui import AppGUI


def configure_logging() -> None:
    """Configure global logging for console debug."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    configure_logging()
    root = tk.Tk()
    AppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
