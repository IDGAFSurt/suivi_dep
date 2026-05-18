# Import d'opérations bancaires PDF -> Excel

## Objectif
Application Python simple pour :
- sélectionner un relevé PDF texte,
- sélectionner un fichier Excel existant,
- extraire le texte brut du PDF en mode debug,
- importer des opérations vers une feuille `Operations`.

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Lancement
```bash
python main.py
```

## Mode debug (étape actuelle)
Bouton **"Extraire le texte brut du PDF"** :
- lit le PDF page par page avec `pdfplumber`,
- écrit un fichier `debug_extraction.txt` à côté du PDF,
- loggue les lignes extraites en console.

Ce fichier debug est prévu pour être copié-collé ensuite afin d'affiner `clean_data.py`.

## Import (version provisoire)
Bouton **"Importer les opérations"** :
- extraction texte du PDF,
- parsing heuristique simple (à améliorer),
- ajout dans `Operations` sans écraser les données,
- dédoublonnage via `ID opération`.

## Structure
- `main.py` : point d'entrée
- `gui.py` : interface Tkinter
- `extract_pdf.py` : extraction brut PDF
- `clean_data.py` : parsing temporaire
- `excel_writer.py` : écriture Excel
- `requirements.txt` : dépendances

## Notes
Le parsing est volontairement simple pour cette première itération.
