# PDF Text Extraction Tool

A desktop application for extracting structured text data from PDF files using vector text extraction with OCR fallback, built with Python and PyQt5.

## Features

- **Batch PDF import** — Scan an entire folder tree and import all PDF files at once
- **Interactive box drawing** — Draw extraction regions on PDF pages to define what text to capture
- **Vector + OCR extraction** — Uses PyMuPDF vector text first; automatically falls back to Tesseract OCR for scanned pages
- **Custom data columns** — Define any number of named extraction columns (e.g. Title, Date, Reference No.)
- **Project save/load** — Save all box positions, extracted data, and settings to a JSON file and reload later
- **Excel export** — Export all data to a formatted `.xlsx` file with two sheets: PDF File List and PDF Page List
- **3-column UI** — PDF tree view | Data table | PDF page viewer with zoom, pan, and box editing
  - Page selection behaviour: single-click changes selection only (so you can Ctrl/Shift multi-select pages); **double-click** a page in the PDF Page List to open it in the viewer.

## Requirements

- Python 3.8 or later
- Tesseract OCR (optional, required for OCR fallback on scanned PDFs)
  - Windows: https://github.com/UB-Mannheim/tesseract/wiki
  - macOS: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

## Project Structure

```
main.py                  Application entry point
requirements.txt         Python dependencies
models/
    data_models.py       Dataclasses: BoxInfo, PageData, PDFFileInfo, ProjectData
ui/
    main_window.py       Main window, toolbar actions, worker threads
    pdf_tree_view.py     1st column — PDF file/page tree
    data_table.py        2nd column — Extracted data table
    pdf_viewer.py        3rd column — PDF page viewer with box drawing
utils/
    pdf_processing.py    PDF open, render, text extract, OCR helpers
    excel_export.py      Excel workbook generation
Test/
    conftest.py          Shared pytest fixtures
    test_*.py            Unit/integration test suites
documentation/
    specification.md     Feature specification
    documentation.html   Full interactive HTML documentation
    review_2026-02-18.md Code review report
```

## Running Tests

```bash
pytest Test/
```

## Notes

- Project JSON files store **absolute file paths**. They are not portable across machines.
- The `requirements.txt` uses `>=` constraints for flexibility. For fully reproducible builds, pin exact versions with `pip freeze > requirements-lock.txt`.
