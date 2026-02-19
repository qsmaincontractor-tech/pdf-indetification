"""
Data Table widget (2nd column).

Displays extracted data in a table format with sortable/filterable columns.
Supports:
- Default columns: File Name, File Path (hidden by default)
- User-defined extracted data columns
- Adding/removing columns
- Showing/hiding columns
- Manual cell editing
- Highlighting the row for the currently selected PDF page

Signals:
    cell_selected: Emitted when a cell in a data column is clicked (file_path, page_number, column_name).
    data_edited: Emitted when cell data is manually edited (file_path, page_number, column_name, new_value).
"""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QInputDialog,
    QMenu,
    QAction,
    QLabel,
    QAbstractItemView,
    QMessageBox,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont, QColor, QBrush
from typing import Optional, List, Tuple

from models.data_models import ProjectData


# QTableWidgetItem subclass that supports a separate sort key (used for numeric sorting)
class SortableTableWidgetItem(QTableWidgetItem):
    """Table item that will compare using an explicit sort-key when present.

    - Store the sort key in a dedicated custom item data role (Qt.UserRole + 3)
    - __lt__ will prefer that key for comparison so numeric columns sort
      numerically while still displaying formatted text.
    """
    SORT_KEY_ROLE = Qt.UserRole + 3

    def __init__(self, text: str = "", sort_key=None):
        super().__init__(text)
        if sort_key is not None:
            self.setData(self.SORT_KEY_ROLE, sort_key)

    def __lt__(self, other: QTableWidgetItem) -> bool:  # type: ignore[override]
        a = self.data(self.SORT_KEY_ROLE)
        b = other.data(self.SORT_KEY_ROLE)
        if a is not None and b is not None:
            try:
                return a < b
            except Exception:
                pass
        return super().__lt__(other)


class DataTable(QWidget):
    """
    Table widget for displaying and editing extracted data.
    
    Columns:
    - File Name (always present, visible by default)
    - File Path (always present, hidden by default)
    - User-defined extracted data columns
    
    Signals:
        cell_selected(str, int, str): Emitted with (file_path, page_number, column_name).
        data_edited(str, int, str, str): Emitted with (file_path, page_number, column_name, new_value).
    """
    
    cell_selected = pyqtSignal(str, int, str)
    data_edited = pyqtSignal(str, int, str, str)
    
    # Fixed columns
    COL_FILE_NAME = 0
    COL_FILE_PATH = 1
    COL_PAGE_NUM = 2
    FIXED_COL_COUNT = 3
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._project_data: Optional[ProjectData] = None
        self._editing = False
        self._highlighted_row = -1
        self._setup_ui()
    
    def _setup_ui(self):
        """Initialize the UI layout with table and buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Extracted Data")
        header.setFont(QFont("Segoe UI", 10, QFont.Bold))
        header.setStyleSheet("padding: 6px; background-color: #f0f0f0; border-bottom: 1px solid #ccc;")
        layout.addWidget(header)
        
        # Table
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)
        
        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(4, 4, 4, 4)
        
        self.btn_add_column = QPushButton("+ Add Column")
        self.btn_add_column.setToolTip("Add a new extracted data column")
        self.btn_add_column.clicked.connect(self._on_add_column)
        btn_layout.addWidget(self.btn_add_column)
        
        self.btn_remove_column = QPushButton("- Remove Column")
        self.btn_remove_column.setToolTip("Remove an extracted data column")
        self.btn_remove_column.clicked.connect(self._on_remove_column)
        btn_layout.addWidget(self.btn_remove_column)
        
        self.btn_columns_visibility = QPushButton("Show/Hide Columns")
        self.btn_columns_visibility.setToolTip("Toggle column visibility")
        self.btn_columns_visibility.clicked.connect(self._on_columns_visibility)
        btn_layout.addWidget(self.btn_columns_visibility)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def set_project_data(self, project_data: ProjectData) -> None:
        """
        Set the project data and refresh the table.
        
        Args:
            project_data: The ProjectData to display.
        """
        self._project_data = project_data
        self.refresh()
    
    def refresh(self) -> None:
        """Rebuild the table from the current project data."""
        if self._project_data is None:
            return
        
        # Temporarily disable sorting to avoid row reordering mid-update
        _sorting_was_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        
        self._editing = True  # Suppress cellChanged during rebuild
        
        # Build column headers
        column_names = self._project_data.get_column_names()
        headers = ["File Name", "File Path", "Page #"] + column_names
        
        # Count total rows (one per page)
        total_rows = sum(len(f.pages) for f in self._project_data.pdf_files)
        
        self.table.setColumnCount(len(headers))
        self.table.setRowCount(total_rows)
        self.table.setHorizontalHeaderLabels(headers)
        
        # Hide File Path column by default
        self.table.setColumnHidden(self.COL_FILE_PATH, True)
        
        # Apply column visibility settings
        for idx, col in enumerate(self._project_data.columns):
            col_index = self.FIXED_COL_COUNT + idx
            if col_index < self.table.columnCount():
                self.table.setColumnHidden(col_index, not col.visible)
        
        # Populate rows
        row = 0
        for pdf_file in self._project_data.pdf_files:
            for page in pdf_file.pages:
                # File Name (read-only)
                item_fn = QTableWidgetItem(pdf_file.file_name)
                item_fn.setFlags(item_fn.flags() & ~Qt.ItemIsEditable)
                item_fn.setData(Qt.UserRole, pdf_file.file_path)
                item_fn.setData(Qt.UserRole + 1, page.page_number)
                self.table.setItem(row, self.COL_FILE_NAME, item_fn)
                
                # File Path (read-only)
                item_fp = QTableWidgetItem(pdf_file.file_path)
                item_fp.setFlags(item_fp.flags() & ~Qt.ItemIsEditable)
                item_fp.setData(Qt.UserRole, pdf_file.file_path)
                item_fp.setData(Qt.UserRole + 1, page.page_number)
                self.table.setItem(row, self.COL_FILE_PATH, item_fp)
                
                # Page Number (read-only) — use SortableTableWidgetItem so sorting is numeric
                item_pn = SortableTableWidgetItem(str(page.page_number + 1), sort_key=(page.page_number + 1))
                item_pn.setFlags(item_pn.flags() & ~Qt.ItemIsEditable)
                item_pn.setData(Qt.UserRole, pdf_file.file_path)
                item_pn.setData(Qt.UserRole + 1, page.page_number)
                self.table.setItem(row, self.COL_PAGE_NUM, item_pn)
                
                # Extracted data columns (editable)
                for col_idx, col_name in enumerate(column_names):
                    value = page.extracted_data.get(col_name, "")
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.UserRole, pdf_file.file_path)
                    item.setData(Qt.UserRole + 1, page.page_number)
                    item.setData(Qt.UserRole + 2, col_name)
                    self.table.setItem(row, self.FIXED_COL_COUNT + col_idx, item)
                
                row += 1
        
        # Resize columns to content
        self.table.resizeColumnsToContents()
        
        self._editing = False
        # Restore sorting state
        self.table.setSortingEnabled(_sorting_was_enabled)
        
        # If project remembers last selection, restore highlight for that page
        try:
            last_file = getattr(self._project_data, "last_selected_file", "")
            last_page = getattr(self._project_data, "last_selected_page", -1)
            if last_file and last_page >= 0:
                self.highlight_row_for_page(last_file, last_page)
        except Exception:
            pass
    
    def highlight_row_for_page(self, file_path: str, page_number: int) -> None:
        """
        Highlight the table row corresponding to a specific PDF page.
        
        Args:
            file_path: Path of the PDF file.
            page_number: Zero-based page number.
        """
        highlight_color = QBrush(QColor("#D6EAF8"))
        default_color1 = QBrush(QColor("#FFFFFF"))
        default_color2 = QBrush(QColor("#F5F5F5"))
        
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILE_NAME)
            if item is None:
                continue
            
            row_file = item.data(Qt.UserRole)
            row_page = item.data(Qt.UserRole + 1)
            
            if row_file == file_path and row_page == page_number:
                color = highlight_color
                self._highlighted_row = row
            else:
                color = default_color1 if row % 2 == 0 else default_color2
            
            for col in range(self.table.columnCount()):
                cell = self.table.item(row, col)
                if cell:
                    cell.setBackground(color)
    
    def get_selected_cell_info(self) -> Optional[Tuple[str, int, str]]:
        """
        Get the info of the currently selected cell.
        
        Returns:
            Tuple of (file_path, page_number, column_name), or None.
        """
        item = self.table.currentItem()
        if item is None:
            return None
        
        file_path = item.data(Qt.UserRole)
        page_number = item.data(Qt.UserRole + 1)
        column_name = item.data(Qt.UserRole + 2)
        
        if file_path is None or page_number is None:
            return None
        
        return (file_path, page_number, column_name or "")
    
    def _on_cell_clicked(self, row: int, column: int) -> None:
        """Handle cell click to emit cell_selected signal."""
        item = self.table.item(row, column)
        if item is None:
            return
        
        file_path = item.data(Qt.UserRole)
        page_number = item.data(Qt.UserRole + 1)
        column_name = item.data(Qt.UserRole + 2)
        
        if file_path and page_number is not None and column_name:
            self.cell_selected.emit(file_path, page_number, column_name)
    
    def _on_cell_changed(self, row: int, column: int) -> None:
        """Handle cell edit to emit data_edited signal and update model."""
        if self._editing:
            return
        
        item = self.table.item(row, column)
        if item is None:
            return
        
        file_path = item.data(Qt.UserRole)
        page_number = item.data(Qt.UserRole + 1)
        column_name = item.data(Qt.UserRole + 2)
        
        if file_path and page_number is not None and column_name:
            new_value = item.text()
            # Update the model
            if self._project_data:
                pdf_file = self._project_data.get_file_by_path(file_path)
                if pdf_file:
                    page = pdf_file.get_page(page_number)
                    if page:
                        page.extracted_data[column_name] = new_value
            self.data_edited.emit(file_path, page_number, column_name, new_value)
    
    def _on_add_column(self) -> None:
        """Show dialog to add a new extracted data column."""
        if self._project_data is None:
            return
        
        name, ok = QInputDialog.getText(
            self, "Add Column", "Enter column name:"
        )
        if ok and name.strip():
            name = name.strip()
            try:
                self._project_data.add_column(name)
                self.refresh()
            except ValueError as e:
                QMessageBox.warning(self, "Error", str(e))
    
    def _on_remove_column(self) -> None:
        """Show dialog to remove an extracted data column."""
        if self._project_data is None:
            return
        
        column_names = self._project_data.get_column_names()
        if not column_names:
            QMessageBox.information(self, "Info", "No columns to remove.")
            return
        
        name, ok = QInputDialog.getItem(
            self, "Remove Column", "Select column to remove:",
            column_names, 0, False
        )
        if ok and name:
            reply = QMessageBox.question(
                self, "Confirm",
                f"Remove column '{name}' and all its data?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._project_data.remove_column(name)
                self.refresh()
    
    def _on_columns_visibility(self) -> None:
        """Show a pop-up menu to toggle column visibility."""
        menu = QMenu(self)
        
        # File Name
        action_fn = QAction("File Name", menu)
        action_fn.setCheckable(True)
        action_fn.setChecked(not self.table.isColumnHidden(self.COL_FILE_NAME))
        action_fn.triggered.connect(
            lambda checked: self.table.setColumnHidden(self.COL_FILE_NAME, not checked)
        )
        menu.addAction(action_fn)
        
        # File Path
        action_fp = QAction("File Path", menu)
        action_fp.setCheckable(True)
        action_fp.setChecked(not self.table.isColumnHidden(self.COL_FILE_PATH))
        action_fp.triggered.connect(
            lambda checked: self.table.setColumnHidden(self.COL_FILE_PATH, not checked)
        )
        menu.addAction(action_fp)
        
        # Page Number
        action_pn = QAction("Page #", menu)
        action_pn.setCheckable(True)
        action_pn.setChecked(not self.table.isColumnHidden(self.COL_PAGE_NUM))
        action_pn.triggered.connect(
            lambda checked: self.table.setColumnHidden(self.COL_PAGE_NUM, not checked)
        )
        menu.addAction(action_pn)
        
        menu.addSeparator()
        
        # User-defined columns
        if self._project_data:
            for idx, col in enumerate(self._project_data.columns):
                col_index = self.FIXED_COL_COUNT + idx
                action = QAction(col.name, menu)
                action.setCheckable(True)
                action.setChecked(col.visible)
                
                def toggle_col(checked, ci=col_index, c=col):
                    c.visible = checked
                    self.table.setColumnHidden(ci, not checked)
                
                action.triggered.connect(toggle_col)
                menu.addAction(action)
        
        menu.exec_(self.btn_columns_visibility.mapToGlobal(
            self.btn_columns_visibility.rect().bottomLeft()
        ))
    
    def update_cell_value(self, file_path: str, page_number: int, column_name: str, value: str) -> None:
        """
        Update a specific cell value in the table.
        
        Args:
            file_path: Path of the PDF file.
            page_number: Zero-based page number.
            column_name: Name of the data column.
            value: New value to set.
        """
        # Disable sorting while updating a single cell to avoid row reordering
        _sorting_was_enabled = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)

        self._editing = True
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.COL_FILE_NAME)
            if item is None:
                continue
            if item.data(Qt.UserRole) == file_path and item.data(Qt.UserRole + 1) == page_number:
                # Find the column
                if self._project_data:
                    col_names = self._project_data.get_column_names()
                    if column_name in col_names:
                        col_idx = self.FIXED_COL_COUNT + col_names.index(column_name)
                        cell = self.table.item(row, col_idx)
                        if cell:
                            cell.setText(value)
                break
        self._editing = False

        # Restore sorting and reapply highlight for the updated page so the visual state stays correct
        self.table.setSortingEnabled(_sorting_was_enabled)
        try:
            self.highlight_row_for_page(file_path, page_number)
        except Exception:
            pass
