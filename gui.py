"""Tkinter GUI for PDF-to-Excel import workflow."""

from __future__ import annotations

import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from extract_pdf import extract_raw_text_by_page, save_debug_extraction
from clean_data import parse_operations_from_pages
from excel_writer import append_operations_to_excel

logger = logging.getLogger(__name__)


class AppGUI:
    """Main application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Import opérations bancaires")
        self.root.geometry("720x300")

        self.pdf_path_var = tk.StringVar()
        self.excel_path_var = tk.StringVar()

        self._build_layout()

    def _build_layout(self) -> None:
        frame = tk.Frame(self.root, padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Relevé PDF :").grid(row=0, column=0, sticky="w", pady=4)
        tk.Entry(frame, textvariable=self.pdf_path_var, width=70).grid(row=0, column=1, padx=8)
        tk.Button(frame, text="Parcourir", command=self.select_pdf).grid(row=0, column=2)

        tk.Label(frame, text="Fichier Excel :").grid(row=1, column=0, sticky="w", pady=4)
        tk.Entry(frame, textvariable=self.excel_path_var, width=70).grid(row=1, column=1, padx=8)
        tk.Button(frame, text="Parcourir", command=self.select_excel).grid(row=1, column=2)

        tk.Button(
            frame,
            text="Extraire le texte brut du PDF",
            command=self.run_debug_extraction,
            bg="#e8f0fe",
        ).grid(row=2, column=1, sticky="we", pady=(20, 8))

        tk.Button(
            frame,
            text="Importer les opérations",
            command=self.import_operations,
            bg="#d6f5d6",
        ).grid(row=3, column=1, sticky="we")

    def select_pdf(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if selected:
            self.pdf_path_var.set(selected)

    def select_excel(self) -> None:
        selected = filedialog.askopenfilename(
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Tous fichiers", "*.*")]
        )
        if selected:
            self.excel_path_var.set(selected)

    def _validate_paths(self) -> tuple[Path, Path]:
        pdf_raw = self.pdf_path_var.get().strip()
        excel_raw = self.excel_path_var.get().strip()

        if not pdf_raw:
            raise ValueError("Aucun PDF sélectionné.")
        if not excel_raw:
            raise ValueError("Aucun fichier Excel sélectionné.")

        pdf_path = Path(pdf_raw)
        excel_path = Path(excel_raw)

        if not pdf_path.exists():
            raise FileNotFoundError("Le PDF est introuvable.")
        if not excel_path.exists():
            raise FileNotFoundError("Le fichier Excel est introuvable.")

        return pdf_path, excel_path

    def run_debug_extraction(self) -> None:
        try:
            pdf_path, _ = self._validate_paths()
            output_path = pdf_path.with_name("debug_extraction.txt")
            save_debug_extraction(pdf_path, output_path)

            message = f"Extraction terminée.\nFichier généré : {output_path}"
            logger.info(message)
            messagebox.showinfo("Succès", message)
        except Exception as exc:  # handled for UI clarity
            logger.exception("Erreur extraction debug")
            messagebox.showerror("Erreur", f"Échec de l'extraction : {exc}")

    def import_operations(self) -> None:
        try:
            pdf_path, excel_path = self._validate_paths()

            pages_text = extract_raw_text_by_page(pdf_path)
            df = parse_operations_from_pages(pages_text, pdf_path)

            if df.empty:
                raise ValueError("Aucune opération détectée.")

            appended = append_operations_to_excel(excel_path, df)

            if appended == 0:
                messagebox.showinfo("Information", "Aucune nouvelle ligne ajoutée (doublons).")
            else:
                messagebox.showinfo("Succès", f"Import terminé : {appended} ligne(s) ajoutée(s).")
        except PermissionError:
            logger.exception("Excel verrouillé")
            messagebox.showerror(
                "Erreur",
                "Le fichier Excel semble ouvert ou protégé. Fermez-le puis réessayez.",
            )
        except Exception as exc:
            logger.exception("Erreur import")
            messagebox.showerror("Erreur", f"Import impossible : {exc}")
