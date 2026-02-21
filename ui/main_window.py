"""
Main Window for the PDF Text Extraction application.

Assembles all UI components (PDFTreeView, DataTable, PDFViewer) into
a 3-column layout with a top toolbar and bottom status bar.

Implements all toolbar actions:
- Import PDF files from a folder
- Save/Load project as JSON
- Clear extracted data
- Delete PDF files
- Apply drawn box to selected pages
- Export to Excel
- Recognize text (OCR)
"""

import os
import sys
import time
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QToolBar,
    QAction,
    QStatusBar,
    QProgressBar,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QApplication,
    QCheckBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QFont

# Absolute path to the project root (parent of this ui/ package).
# Passed to subprocess workers so they can import project modules.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from models.data_models import (
    ProjectData,
    PDFFileInfo,
    PageData,
    BoxInfo,
    ExtractedDataColumn,
)
from utils.pdf_processing import (
    find_pdf_files,
    get_pdf_info,
    render_pdf_page,
    extract_text_from_relative_region,
    is_ocr_available,
)
from utils.excel_export import export_to_excel
from ui.pdf_tree_view import PDFTreeView
from ui.data_table import DataTable
from ui.pdf_viewer import PDFViewer


class ImportWorker(QThread):
    """
    Worker thread for importing PDF files from a directory.
    
    Signals:
        progress(int, int): (current, total) progress update.
        file_loaded(dict): Info dict for a loaded file.
        finished_import(): Emitted when import completes.
        error(str): Emitted on error.
    """
    progress = pyqtSignal(int, int)
    file_loaded = pyqtSignal(dict)
    finished_import = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, directory: str, parent=None):
        super().__init__(parent)
        self.directory = directory
    
    def run(self):
        try:
            pdf_paths = find_pdf_files(self.directory)
            total = len(pdf_paths)
            
            for i, path in enumerate(pdf_paths):
                try:
                    info = get_pdf_info(path)
                    self.file_loaded.emit(info)
                except Exception as e:
                    self.error.emit(f"Error loading {path}: {e}")
                
                self.progress.emit(i + 1, total)
            
            self.finished_import.emit()
        except Exception as e:
            self.error.emit(f"Import error: {e}")
            self.finished_import.emit()


class RecognizeWorker(QThread):
    """
    Worker thread for text recognition on selected pages.

    Uses a ``ProcessPoolExecutor`` to run box-level extraction jobs in
    parallel across multiple CPU cores while reporting live progress and
    supporting mid-run cancellation.

    Signals:
        progress(int, int): (completed_tasks, total_tasks) progress update.
        text_extracted(str, int, str, str): (file_path, page_num, column_name, text).
        finished_recognize(): Emitted when done (including after cancel).
        error(str): Emitted on per-task errors.
    """
    progress = pyqtSignal(int, int)
    text_extracted = pyqtSignal(str, int, str, str)
    finished_recognize = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, pages_and_boxes, project_root: str, parent=None):
        """
        Args:
            pages_and_boxes: List of (file_path, page_number, boxes_list) tuples.
            project_root: Absolute path to the project root directory so that
                subprocess workers can add it to sys.path.
        """
        super().__init__(parent)
        self.pages_and_boxes = pages_and_boxes
        self.project_root = project_root
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation.  Already-running subprocesses finish normally;
        queued tasks are discarded and no further signals (except
        finished_recognize) will be emitted."""
        self._cancel_event.set()

    def run(self):
        from utils.pdf_processing import _extract_box_task, _init_subprocess

        # Flatten (file_path, page_num, boxes) into individual box tasks.
        tasks: list = []
        for file_path, page_num, boxes in self.pages_and_boxes:
            for box in boxes:
                tasks.append((
                    file_path, page_num, box.column_name,
                    box.x, box.y, box.width, box.height,
                ))

        total = len(tasks)
        if total == 0:
            self.finished_recognize.emit()
            return

        completed = 0
        # Limit workers: at most 4 or the number of CPUs (min with task count).
        max_workers = min(4, total, max(1, (os.cpu_count() or 2)))

        try:
            with ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=_init_subprocess,
                initargs=(self.project_root,),
            ) as executor:
                futures = {
                    executor.submit(_extract_box_task, task): task
                    for task in tasks
                }

                for future in as_completed(futures):
                    if self._cancel_event.is_set():
                        # Cancel all still-pending futures and stop collecting.
                        for f in futures:
                            f.cancel()
                        break

                    try:
                        fp, pn, col, text = future.result()
                        self.text_extracted.emit(fp, pn, col, text)
                    except Exception as exc:
                        task = futures[future]
                        self.error.emit(
                            f"Error on {task[0]} p{task[1] + 1}: {exc}"
                        )

                    completed += 1
                    self.progress.emit(completed, total)

        except Exception as exc:
            self.error.emit(f"Multiprocessing error: {exc}")

        self.finished_recognize.emit()


class MainWindow(QMainWindow):
    """
    Main application window for the PDF Text Extraction tool.
    
    Layout:
    ┌──────────────────────────────────────────┐
    │                 Toolbar                    │
    ├──────────┬───────────────┬────────────────┤
    │ PDF Tree │  Data Table   │  PDF Viewer    │
    │ (1st)    │  (2nd)        │  (3rd)         │
    ├──────────┴───────────────┴────────────────┤
    │               Status Bar                   │
    └──────────────────────────────────────────┘
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDF Text Extraction Tool")
        self.setMinimumSize(1200, 700)
        
        # Data model
        self._project_data = ProjectData()
        self._current_file_path: str = ""
        self._current_page_num: int = -1
        
        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        
        self._update_status("Ready")
        # L1/L5: Check OCR availability on startup so the indicator is correct immediately
        self._update_ocr_status()
    
    def _setup_ui(self):
        """Set up the 3-column layout with splitters."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Splitter for 3 columns
        self.splitter = QSplitter(Qt.Horizontal)
        
        # 1st column: PDF Tree View
        self.pdf_tree = PDFTreeView()
        self.splitter.addWidget(self.pdf_tree)
        
        # 2nd column: Data Table
        self.data_table = DataTable()
        self.splitter.addWidget(self.data_table)
        
        # 3rd column: PDF Viewer
        self.pdf_viewer = PDFViewer()
        self.splitter.addWidget(self.pdf_viewer)
        
        # Set initial proportions
        self.splitter.setSizes([200, 400, 500])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 3)
        
        main_layout.addWidget(self.splitter)
    
    def _setup_toolbar(self):
        """Set up the top toolbar with all action buttons."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        
        # Import PDF Files
        self.action_import = QAction("Import PDFs", self)
        self.action_import.setToolTip("Select a folder to import PDF files from all subfolders")
        self.action_import.triggered.connect(self._on_import)
        toolbar.addAction(self.action_import)
        
        toolbar.addSeparator()
        
        # Save
        self.action_save = QAction("Save", self)
        self.action_save.setToolTip("Save project as JSON file")
        self.action_save.setShortcut("Ctrl+S")
        self.action_save.triggered.connect(self._on_save)
        toolbar.addAction(self.action_save)
        
        # Load
        self.action_load = QAction("Load", self)
        self.action_load.setToolTip("Load project from JSON file")
        self.action_load.setShortcut("Ctrl+O")
        self.action_load.triggered.connect(self._on_load)
        toolbar.addAction(self.action_load)
        
        toolbar.addSeparator()
        
        # Clear Extracted Data
        self.action_clear = QAction("Clear Data", self)
        self.action_clear.setToolTip("Clear extracted data for selected pages")
        self.action_clear.triggered.connect(self._on_clear_data)
        toolbar.addAction(self.action_clear)
        
        # Delete PDF Files
        self.action_delete = QAction("Delete PDFs", self)
        self.action_delete.setToolTip("Remove selected PDF files from the project")
        self.action_delete.triggered.connect(self._on_delete_files)
        toolbar.addAction(self.action_delete)
        
        toolbar.addSeparator()
        
        # Apply Drawn Box
        self.action_apply_box = QAction("Apply Box", self)
        self.action_apply_box.setToolTip("Apply the drawn box coordinates to selected pages")
        self.action_apply_box.triggered.connect(self._on_apply_box)
        toolbar.addAction(self.action_apply_box)
        
        # Recognize Text
        self.action_recognize = QAction("Recognize Text", self)
        self.action_recognize.setToolTip("Extract text data from drawn boxes for selected pages")
        self.action_recognize.triggered.connect(self._on_recognize_text)
        toolbar.addAction(self.action_recognize)
        
        toolbar.addSeparator()
        
        # Export to Excel
        self.action_export = QAction("Export Excel", self)
        self.action_export.setToolTip("Export all data to an Excel file")
        self.action_export.triggered.connect(self._on_export_excel)
        toolbar.addAction(self.action_export)

        toolbar.addSeparator()

        # Single Page Mode toggle
        self.chk_single_page_mode = QCheckBox("Single Page Mode")
        self.chk_single_page_mode.setToolTip(
            "Show only the data for the currently selected page in the table"
        )
        self.chk_single_page_mode.setChecked(False)
        self.chk_single_page_mode.toggled.connect(self._on_single_page_mode_toggled)
        toolbar.addWidget(self.chk_single_page_mode)
    
    def _setup_statusbar(self):
        """Set up the bottom status bar with labels and progress bar."""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        self.status_label = QLabel("Ready")
        self.statusbar.addWidget(self.status_label, 1)
        
        self.info_label = QLabel("Files: 0 | Pages: 0")
        self.statusbar.addPermanentWidget(self.info_label)

        # OCR availability indicator (shown in status bar)
        self.ocr_label = QLabel("OCR: unknown")
        self.ocr_label.setToolTip("OCR availability")
        self.statusbar.addPermanentWidget(self.ocr_label)

        # Cancel button — visible only while text recognition is running.
        self.btn_cancel_recognize = QPushButton("Cancel")
        self.btn_cancel_recognize.setToolTip("Cancel the running text recognition")
        self.btn_cancel_recognize.setVisible(False)
        self.btn_cancel_recognize.clicked.connect(self._on_cancel_recognize)
        self.statusbar.addPermanentWidget(self.btn_cancel_recognize)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.statusbar.addPermanentWidget(self.progress_bar)
    
    def _connect_signals(self):
        """Connect signals between components."""
        # Tree -> show page in viewer and highlight in table
        self.pdf_tree.page_selected.connect(self._on_page_selected)
        
        # Table cell selected -> highlight box in viewer and set active column
        self.data_table.cell_selected.connect(self._on_table_cell_selected)
        
        # Table data edited -> update model
        self.data_table.data_edited.connect(self._on_data_edited)
        
        # Table SPM navigation -> update viewer and tree selection
        self.data_table.page_navigated.connect(self._on_spm_page_navigated)

        # Viewer box drawn -> update model and table
        self.pdf_viewer.box_drawn.connect(self._on_box_drawn)
        self.pdf_viewer.box_changed.connect(self._on_box_changed)
        self.pdf_viewer.box_deleted.connect(self._on_box_deleted)
        self.pdf_viewer.box_selected.connect(self._on_box_selected_in_viewer)
    
    def _update_status(self, message: str) -> None:
        """Update the status bar message."""
        self.status_label.setText(message)
    
    def _update_info(self) -> None:
        """Update the file/page count in the status bar."""
        num_files = len(self._project_data.pdf_files)
        num_pages = sum(len(f.pages) for f in self._project_data.pdf_files)
        self.info_label.setText(f"Files: {num_files} | Pages: {num_pages}")

    def _update_ocr_status(self) -> None:
        """Update the OCR availability indicator in the status bar.
        
        C1: Sets green colour for 'OCR: on' and red for 'OCR: off' as per spec.
        """
        try:
            available = is_ocr_available()
            if available:
                self.ocr_label.setText("OCR: on")
                self.ocr_label.setToolTip("OCR fallback is available")
                self.ocr_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.ocr_label.setText("OCR: off")
                self.ocr_label.setToolTip("OCR not available (pytesseract/pyMuPDF OCR missing)")
                self.ocr_label.setStyleSheet("color: red; font-weight: bold;")
        except Exception:
            self.ocr_label.setText("OCR: unknown")
            self.ocr_label.setToolTip("Unable to determine OCR availability")
            self.ocr_label.setStyleSheet("")
    
    def _show_progress(self, current: int, total: int) -> None:
        """Update the progress bar."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if current >= total:
            self.progress_bar.setVisible(False)
    
    def _refresh_all(self) -> None:
        """Refresh all UI components from the project data."""
        self.pdf_tree.populate(self._project_data)
        self.data_table.set_project_data(self._project_data)
        self._update_info()
    
    # ===== Page Selection =====
    
    def _on_page_selected(self, file_path: str, page_number: int) -> None:
        """Handle page selection from the tree view."""
        self._current_file_path = file_path
        self._current_page_num = page_number
        
        # Render and display the page
        self._update_status(f"Loading page {page_number + 1}...")
        QApplication.processEvents()
        
        image_data = render_pdf_page(file_path, page_number, zoom=1.5)
        if image_data:
            self.pdf_viewer.set_image(image_data)
        else:
            self.pdf_viewer.clear_image()
            self._update_status("Failed to render page")
            return
        
        # Show boxes for this page
        pdf_file = self._project_data.get_file_by_path(file_path)
        if pdf_file:
            page = pdf_file.get_page(page_number)
            if page:
                self.pdf_viewer.set_boxes(page.boxes)
        
        # Highlight corresponding row in table (and update SPM navigation)
        self.data_table.navigate_to_page(file_path, page_number)
        self.data_table.highlight_row_for_page(file_path, page_number)
        
        # Save selection state
        self._project_data.last_selected_file = file_path
        self._project_data.last_selected_page = page_number
        
        self._update_status(f"Viewing: {os.path.basename(file_path)} - Page {page_number + 1}")
    
    # ===== Table Cell Selection =====
    
    def _on_table_cell_selected(self, file_path: str, page_number: int, column_name: str) -> None:
        """Handle cell selection in the data table."""
        # Set active column for drawing
        self.pdf_viewer.set_active_column(column_name)
        
        # If the page differs from current, load it
        if file_path != self._current_file_path or page_number != self._current_page_num:
            self._on_page_selected(file_path, page_number)
            self.pdf_tree.select_page(file_path, page_number)
        
        # Highlight corresponding box
        if column_name:
            self.pdf_viewer.highlight_box(column_name)
            # Centre/view the drawn box in the PDF viewer so the user can see it
            self.pdf_viewer.center_on_box(column_name)
    
    def _on_data_edited(self, file_path: str, page_number: int, column_name: str, new_value: str) -> None:
        """Handle manual data edit in the table."""
        pdf_file = self._project_data.get_file_by_path(file_path)
        if pdf_file:
            page = pdf_file.get_page(page_number)
            if page:
                page.extracted_data[column_name] = new_value
    
    # ===== Box Interactions =====
    
    def _on_box_drawn(self, column_name: str, rel_x: float, rel_y: float, rel_w: float, rel_h: float) -> None:
        """Handle new box drawn in the viewer."""
        if not self._current_file_path or self._current_page_num < 0:
            return
        
        pdf_file = self._project_data.get_file_by_path(self._current_file_path)
        if pdf_file:
            page = pdf_file.get_page(self._current_page_num)
            if page:
                box = BoxInfo(column_name=column_name, x=rel_x, y=rel_y, width=rel_w, height=rel_h)
                page.set_box_for_column(box)
                
                # Auto-extract text
                text = extract_text_from_relative_region(
                    self._current_file_path, self._current_page_num,
                    rel_x, rel_y, rel_w, rel_h,
                )
                box.extracted_text = text
                page.extracted_data[column_name] = text
                
                # Update table
                self.data_table.update_cell_value(
                    self._current_file_path, self._current_page_num,
                    column_name, text,
                )
                self._update_status(f"Box drawn for '{column_name}' - Text extracted")
    
    def _on_box_changed(self, column_name: str, rel_x: float, rel_y: float, rel_w: float, rel_h: float) -> None:
        """Handle box moved/resized in the viewer."""
        if not self._current_file_path or self._current_page_num < 0:
            return
        
        pdf_file = self._project_data.get_file_by_path(self._current_file_path)
        if pdf_file:
            page = pdf_file.get_page(self._current_page_num)
            if page:
                box = page.get_box_for_column(column_name)
                if box:
                    box.x = rel_x
                    box.y = rel_y
                    box.width = rel_w
                    box.height = rel_h
                    
                    # Re-extract text
                    text = extract_text_from_relative_region(
                        self._current_file_path, self._current_page_num,
                        rel_x, rel_y, rel_w, rel_h,
                    )
                    box.extracted_text = text
                    page.extracted_data[column_name] = text
                    
                    self.data_table.update_cell_value(
                        self._current_file_path, self._current_page_num,
                        column_name, text,
                    )
    
    def _on_box_deleted(self, column_name: str) -> None:
        """Handle box deletion in the viewer."""
        if not self._current_file_path or self._current_page_num < 0:
            return
        
        pdf_file = self._project_data.get_file_by_path(self._current_file_path)
        if pdf_file:
            page = pdf_file.get_page(self._current_page_num)
            if page:
                page.remove_box_for_column(column_name)
                page.extracted_data.pop(column_name, None)
                
                self.data_table.update_cell_value(
                    self._current_file_path, self._current_page_num,
                    column_name, "",
                )
                self._update_status(f"Box for '{column_name}' deleted")
    
    def _on_box_selected_in_viewer(self, column_name: str) -> None:
        """Handle box selection in the viewer - highlight in table."""
        self.pdf_viewer.set_active_column(column_name)

    # ===== Single Page Mode =====

    def _on_single_page_mode_toggled(self, enabled: bool) -> None:
        """Enable or disable Single Page Mode in the data table."""
        self.data_table.set_single_page_mode(enabled)
        # If a page is already selected, make sure the SPM view is in sync
        if enabled and self._current_file_path and self._current_page_num >= 0:
            self.data_table.navigate_to_page(self._current_file_path, self._current_page_num)

    def _on_spm_page_navigated(self, file_path: str, page_number: int) -> None:
        """Handle SPM Previous / Next button navigation from the data table."""
        # Update tree selection so the highlight stays in sync
        self.pdf_tree.select_page(file_path, page_number)
        # Load the page in the viewer (does not re-emit page_selected)
        self._on_page_selected(file_path, page_number)

    # ===== Toolbar Actions =====
    
    def _on_import(self) -> None:
        """Import PDF files from a selected folder."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Folder to Import PDF Files"
        )
        if not directory:
            return
        
        self._update_status("Importing PDF files...")
        self.action_import.setEnabled(False)
        
        self._import_worker = ImportWorker(directory)
        self._import_worker.progress.connect(self._show_progress)
        self._import_worker.file_loaded.connect(self._on_file_imported)
        self._import_worker.error.connect(lambda msg: self._update_status(msg))
        self._import_worker.finished_import.connect(self._on_import_finished)
        self._import_worker.start()
    
    def _on_file_imported(self, info: dict) -> None:
        """Handle a single file being imported."""
        # Check if already imported
        if self._project_data.get_file_by_path(info["file_path"]):
            return
        
        pdf_file = PDFFileInfo(
            file_name=info["file_name"],
            file_path=info["file_path"],
            num_pages=info["num_pages"],
            file_size=info["file_size"],
        )
        
        # Create PageData for each page
        for i in range(info["num_pages"]):
            pdf_file.pages.append(PageData(page_number=i))
        
        self._project_data.pdf_files.append(pdf_file)
    
    def _on_import_finished(self) -> None:
        """Handle import completion."""
        self._refresh_all()
        self.action_import.setEnabled(True)
        self._update_status(f"Import complete. {len(self._project_data.pdf_files)} files loaded.")
        # L5: Refresh OCR status after import (environment may have changed)
        self._update_ocr_status()
    
    def _on_save(self) -> None:
        """Save project to JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "JSON Files (*.json)"
        )
        if not file_path:
            return
        
        try:
            self._update_status("Saving project...")
            self._project_data.save_to_json(file_path)
            self._update_status(f"Project saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")
            self._update_status("Save failed")
    
    def _on_load(self) -> None:
        """Load project from JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "JSON Files (*.json)"
        )
        if not file_path:
            return
        
        try:
            self._update_status("Loading project...")
            self._project_data = ProjectData.load_from_json(file_path)
            self._refresh_all()
            
            # Restore last selection
            if self._project_data.last_selected_file and self._project_data.last_selected_page >= 0:
                self.pdf_tree.select_page(
                    self._project_data.last_selected_file,
                    self._project_data.last_selected_page,
                )
                self._on_page_selected(
                    self._project_data.last_selected_file,
                    self._project_data.last_selected_page,
                )
            
            self._update_status(f"Project loaded from {file_path}")
        except ValueError as e:
            # D2: Version incompatibility reported clearly
            QMessageBox.critical(self, "Incompatible File", str(e))
            self._update_status("Load failed")
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load: {e}")
            self._update_status("Load failed")
    
    def _on_clear_data(self) -> None:
        """Clear extracted data for selected pages."""
        selected = self.pdf_tree.get_selected_pages()
        if not selected:
            QMessageBox.information(self, "Info", "No pages selected.")
            return
        
        reply = QMessageBox.question(
            self, "Confirm",
            f"Clear extracted data for {len(selected)} page(s)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        # C2: Show progress bar for clear operation
        self._update_status("Clearing extracted data...")
        total = len(selected)
        for idx, (file_path, page_num) in enumerate(selected):
            pdf_file = self._project_data.get_file_by_path(file_path)
            if pdf_file:
                page = pdf_file.get_page(page_num)
                if page:
                    page.clear_all_data()
            self._show_progress(idx + 1, total)
        
        self._refresh_all()
        
        # Refresh viewer boxes if current page was affected
        if (self._current_file_path, self._current_page_num) in selected:
            self.pdf_viewer.set_boxes([])
        
        self._update_status("Extracted data cleared")
    
    def _on_delete_files(self) -> None:
        """Delete selected PDF files from the project."""
        file_paths = self.pdf_tree.get_selected_file_paths()
        if not file_paths:
            QMessageBox.information(self, "Info", "No files selected.")
            return
        
        reply = QMessageBox.question(
            self, "Confirm",
            f"Remove {len(file_paths)} file(s) from the project?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        self._update_status("Deleting PDF files...")
        for path in file_paths:
            self._project_data.remove_pdf_file(path)
        
        self.pdf_viewer.clear_image()
        self._current_file_path = ""
        self._current_page_num = -1
        self._refresh_all()
        self._update_status("PDF files removed")
    
    def _on_apply_box(self) -> None:
        """Apply drawn box coordinates to selected pages."""
        selected = self.pdf_tree.get_selected_pages()
        if not selected:
            QMessageBox.information(self, "Info", "No pages selected.")
            return
        
        # Get boxes from the current page
        if not self._current_file_path or self._current_page_num < 0:
            QMessageBox.information(self, "Info", "No page currently displayed.")
            return
        
        source_file = self._project_data.get_file_by_path(self._current_file_path)
        if not source_file:
            return
        source_page = source_file.get_page(self._current_page_num)
        if not source_page or not source_page.boxes:
            QMessageBox.information(self, "Info", "No boxes drawn on the current page.")
            return
        
        reply = QMessageBox.question(
            self, "Confirm",
            f"Apply box coordinates from current page to {len(selected)} page(s)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        self._update_status("Applying drawn box to selected pages...")
        count = 0
        total = len(selected)
        applied = 0
        
        for file_path, page_num in selected:
            # Skip the source page
            if file_path == self._current_file_path and page_num == self._current_page_num:
                count += 1
                self._show_progress(count, total)
                continue
            
            pdf_file = self._project_data.get_file_by_path(file_path)
            if pdf_file:
                page = pdf_file.get_page(page_num)
                if page:
                    for source_box in source_page.boxes:
                        new_box = BoxInfo(
                            column_name=source_box.column_name,
                            x=source_box.x,
                            y=source_box.y,
                            width=source_box.width,
                            height=source_box.height,
                        )
                        page.set_box_for_column(new_box)
                    applied += 1
            
            count += 1
            self._show_progress(count, total)
        
        self.data_table.refresh()
        # L3: Report the number actually modified (excluding source page)
        self._update_status(f"Box coordinates applied to {applied} page(s)")
    
    def _on_recognize_text(self) -> None:
        """Extract text from drawn boxes for selected pages."""
        selected = self.pdf_tree.get_selected_pages()
        if not selected:
            QMessageBox.information(self, "Info", "No pages selected.")
            return
        
        # Gather pages with boxes
        pages_and_boxes = []
        for file_path, page_num in selected:
            pdf_file = self._project_data.get_file_by_path(file_path)
            if pdf_file:
                page = pdf_file.get_page(page_num)
                if page and page.boxes:
                    pages_and_boxes.append((file_path, page_num, page.boxes))
        
        if not pages_and_boxes:
            QMessageBox.information(self, "Info", "No boxes found on selected pages.")
            return
        
        self._update_status("Recognizing text...")
        self.action_recognize.setEnabled(False)
        self.btn_cancel_recognize.setVisible(True)
        self.btn_cancel_recognize.setEnabled(True)

        self._recognize_worker = RecognizeWorker(
            pages_and_boxes, project_root=_PROJECT_ROOT
        )
        self._recognize_worker.progress.connect(self._show_progress)
        self._recognize_worker.text_extracted.connect(self._on_text_extracted)
        self._recognize_worker.error.connect(lambda msg: self._update_status(msg))
        self._recognize_worker.finished_recognize.connect(self._on_recognize_finished)
        self._recognize_worker.start()
    
    def _on_text_extracted(self, file_path: str, page_num: int, column_name: str, text: str) -> None:
        """Handle text extracted from a box."""
        pdf_file = self._project_data.get_file_by_path(file_path)
        if pdf_file:
            page = pdf_file.get_page(page_num)
            if page:
                page.extracted_data[column_name] = text
                box = page.get_box_for_column(column_name)
                if box:
                    box.extracted_text = text
    
    def _on_cancel_recognize(self) -> None:
        """Handle the Cancel button click during text recognition."""
        if hasattr(self, "_recognize_worker") and self._recognize_worker.isRunning():
            self._recognize_worker.cancel()
            self.btn_cancel_recognize.setEnabled(False)
            self._update_status("Cancelling text recognition…")

    def _on_recognize_finished(self) -> None:
        """Handle text recognition completion (normal or cancelled)."""
        self.data_table.refresh()
        self.action_recognize.setEnabled(True)
        self.btn_cancel_recognize.setVisible(False)
        cancelled = (
            hasattr(self, "_recognize_worker")
            and self._recognize_worker._cancel_event.is_set()
        )
        self._update_status(
            "Text recognition cancelled" if cancelled else "Text recognition complete"
        )
        # L2: Refresh the viewer boxes for the currently displayed page so that
        # box labels stay in sync with any newly extracted text.
        if self._current_file_path and self._current_page_num >= 0:
            pdf_file = self._project_data.get_file_by_path(self._current_file_path)
            if pdf_file:
                page = pdf_file.get_page(self._current_page_num)
                if page:
                    self.pdf_viewer.set_boxes(page.boxes)
    
    def _on_export_excel(self) -> None:
        """Export project data to an Excel file."""
        if not self._project_data.pdf_files:
            QMessageBox.information(self, "Info", "No data to export.")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", "", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return
        
        try:
            # C2: Show progress indicator while exporting
            self._show_progress(0, 1)
            self._update_status("Exporting to Excel...")
            QApplication.processEvents()
            export_to_excel(self._project_data, file_path)
            self._show_progress(1, 1)
            self._update_status(f"Exported to {file_path}")
        except PermissionError:
            # D6: PermissionError usually means the file is already open in Excel
            QMessageBox.critical(
                self, "Export Error",
                f"Cannot write to '{file_path}'.\n"
                "The file may already be open in Excel. Please close it and try again."
            )
            self._update_status("Export failed")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")
            self._update_status("Export failed")
