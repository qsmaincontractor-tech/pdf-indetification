"""
Test cases for data models (models/data_models.py).

Tests:
- BoxInfo creation, serialization, coordinate conversion
- ExtractedDataColumn creation and serialization
- PageData operations (add/remove boxes, clear data)
- PDFFileInfo creation and page lookup
- ProjectData CRUD operations, save/load JSON, column management
"""

import os
import json
import pytest

from models.data_models import (
    BoxInfo,
    ExtractedDataColumn,
    PageData,
    PDFFileInfo,
    ProjectData,
)


class TestBoxInfo:
    """Tests for the BoxInfo data model."""
    
    def test_create_default(self):
        """Test creating a BoxInfo with default values."""
        box = BoxInfo(column_name="Title")
        assert box.column_name == "Title"
        assert box.x == 0.0
        assert box.y == 0.0
        assert box.width == 0.0
        assert box.height == 0.0
        assert box.extracted_text == ""
    
    def test_create_with_values(self):
        """Test creating a BoxInfo with specific values."""
        box = BoxInfo(
            column_name="Page",
            x=0.1, y=0.2, width=0.3, height=0.4,
            extracted_text="Hello",
        )
        assert box.column_name == "Page"
        assert box.x == 0.1
        assert box.y == 0.2
        assert box.width == 0.3
        assert box.height == 0.4
        assert box.extracted_text == "Hello"
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        box = BoxInfo(column_name="Title", x=0.1, y=0.2, width=0.3, height=0.4)
        d = box.to_dict()
        assert d["column_name"] == "Title"
        assert d["x"] == 0.1
        assert d["y"] == 0.2
        assert d["width"] == 0.3
        assert d["height"] == 0.4
    
    def test_from_dict(self):
        """Test deserialization from dictionary."""
        d = {"column_name": "Title", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4, "extracted_text": "Test"}
        box = BoxInfo.from_dict(d)
        assert box.column_name == "Title"
        assert box.x == 0.1
        assert box.extracted_text == "Test"
    
    def test_from_dict_missing_keys(self):
        """Test deserialization with missing keys uses defaults."""
        box = BoxInfo.from_dict({})
        assert box.column_name == ""
        assert box.x == 0.0
    
    def test_get_absolute_rect(self):
        """Test converting relative to absolute coordinates."""
        box = BoxInfo(column_name="Title", x=0.1, y=0.2, width=0.3, height=0.4)
        rect = box.get_absolute_rect(1000, 800)
        assert rect == (100.0, 160.0, 400.0, 480.0)
    
    def test_from_absolute_rect(self):
        """Test creating BoxInfo from absolute coordinates."""
        box = BoxInfo.from_absolute_rect("Title", 100, 160, 400, 480, 1000, 800)
        assert abs(box.x - 0.1) < 1e-9
        assert abs(box.y - 0.2) < 1e-9
        assert abs(box.width - 0.3) < 1e-9
        assert abs(box.height - 0.4) < 1e-9
    
    def test_from_absolute_rect_inverted(self):
        """Test creating BoxInfo from inverted absolute coordinates."""
        box = BoxInfo.from_absolute_rect("Title", 400, 480, 100, 160, 1000, 800)
        assert abs(box.x - 0.1) < 1e-9
        assert abs(box.y - 0.2) < 1e-9


class TestExtractedDataColumn:
    """Tests for the ExtractedDataColumn data model."""
    
    def test_create(self):
        """Test creating a column."""
        col = ExtractedDataColumn(name="Title")
        assert col.name == "Title"
        assert col.visible is True
    
    def test_create_hidden(self):
        """Test creating a hidden column."""
        col = ExtractedDataColumn(name="Title", visible=False)
        assert col.visible is False
    
    def test_serialization_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        col = ExtractedDataColumn(name="Page", visible=False)
        d = col.to_dict()
        col2 = ExtractedDataColumn.from_dict(d)
        assert col2.name == "Page"
        assert col2.visible is False


class TestPageData:
    """Tests for the PageData data model."""
    
    def test_create_default(self):
        """Test creating a PageData with defaults."""
        page = PageData(page_number=0)
        assert page.page_number == 0
        assert page.extracted_data == {}
        assert page.boxes == []
    
    def test_set_box_for_column_new(self):
        """Test adding a new box."""
        page = PageData(page_number=0)
        box = BoxInfo(column_name="Title", x=0.1, y=0.1, width=0.3, height=0.05)
        page.set_box_for_column(box)
        assert len(page.boxes) == 1
        assert page.boxes[0].column_name == "Title"
    
    def test_set_box_for_column_replace(self):
        """Test replacing an existing box."""
        page = PageData(page_number=0)
        box1 = BoxInfo(column_name="Title", x=0.1, y=0.1, width=0.3, height=0.05)
        box2 = BoxInfo(column_name="Title", x=0.2, y=0.2, width=0.4, height=0.1)
        page.set_box_for_column(box1)
        page.set_box_for_column(box2)
        assert len(page.boxes) == 1
        assert page.boxes[0].x == 0.2
    
    def test_get_box_for_column(self):
        """Test getting a box by column name."""
        page = PageData(page_number=0)
        box = BoxInfo(column_name="Title", x=0.1, y=0.1, width=0.3, height=0.05)
        page.set_box_for_column(box)
        found = page.get_box_for_column("Title")
        assert found is not None
        assert found.x == 0.1
    
    def test_get_box_for_column_not_found(self):
        """Test getting a non-existent box."""
        page = PageData(page_number=0)
        assert page.get_box_for_column("Missing") is None
    
    def test_remove_box_for_column(self):
        """Test removing a box."""
        page = PageData(page_number=0)
        page.set_box_for_column(BoxInfo(column_name="Title"))
        page.set_box_for_column(BoxInfo(column_name="Page"))
        page.remove_box_for_column("Title")
        assert len(page.boxes) == 1
        assert page.boxes[0].column_name == "Page"
    
    def test_clear_all_data(self):
        """Test clearing all data and boxes."""
        page = PageData(page_number=0)
        page.extracted_data = {"Title": "Test", "Page": "1"}
        page.boxes.append(BoxInfo(column_name="Title"))
        page.clear_all_data()
        assert page.extracted_data == {}
        assert page.boxes == []
    
    def test_serialization_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        page = PageData(page_number=5)
        page.extracted_data = {"Title": "Test"}
        page.boxes.append(BoxInfo(column_name="Title", x=0.1, y=0.2, width=0.3, height=0.4))
        
        d = page.to_dict()
        page2 = PageData.from_dict(d)
        assert page2.page_number == 5
        assert page2.extracted_data["Title"] == "Test"
        assert len(page2.boxes) == 1
        assert page2.boxes[0].x == 0.1


class TestPDFFileInfo:
    """Tests for the PDFFileInfo data model."""
    
    def test_create(self):
        """Test creating a PDFFileInfo."""
        info = PDFFileInfo(
            file_name="test.pdf",
            file_path="/path/test.pdf",
            num_pages=10,
            file_size=5000,
        )
        assert info.file_name == "test.pdf"
        assert info.num_pages == 10
    
    def test_get_page(self):
        """Test getting a page by number."""
        info = PDFFileInfo(file_name="test.pdf")
        info.pages = [PageData(page_number=0), PageData(page_number=1)]
        assert info.get_page(0) is not None
        assert info.get_page(1) is not None
        assert info.get_page(2) is None
    
    def test_serialization_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        info = PDFFileInfo(
            file_name="test.pdf", file_path="/test.pdf",
            num_pages=2, file_size=1000,
        )
        info.pages = [PageData(page_number=0), PageData(page_number=1)]
        
        d = info.to_dict()
        info2 = PDFFileInfo.from_dict(d)
        assert info2.file_name == "test.pdf"
        assert len(info2.pages) == 2


class TestProjectData:
    """Tests for the ProjectData data model."""
    
    def test_create_empty(self):
        """Test creating an empty project."""
        project = ProjectData()
        assert project.pdf_files == []
        assert project.columns == []
    
    def test_add_column(self):
        """Test adding columns."""
        project = ProjectData()
        col = project.add_column("Title")
        assert col.name == "Title"
        assert len(project.columns) == 1
    
    def test_add_duplicate_column_raises(self):
        """Test that adding a duplicate column raises ValueError."""
        project = ProjectData()
        project.add_column("Title")
        with pytest.raises(ValueError):
            project.add_column("Title")
    
    def test_remove_column(self):
        """Test removing a column removes data and boxes too."""
        project = ProjectData()
        project.add_column("Title")
        
        pdf_file = PDFFileInfo(file_name="test.pdf", file_path="/test.pdf")
        page = PageData(page_number=0)
        page.extracted_data = {"Title": "Test"}
        page.boxes = [BoxInfo(column_name="Title", x=0.1, y=0.1, width=0.3, height=0.05)]
        pdf_file.pages.append(page)
        project.pdf_files.append(pdf_file)
        
        project.remove_column("Title")
        assert len(project.columns) == 0
        assert "Title" not in page.extracted_data
        assert len(page.boxes) == 0
    
    def test_get_column_names(self):
        """Test getting column names."""
        project = ProjectData()
        project.add_column("Title")
        project.add_column("Page")
        assert project.get_column_names() == ["Title", "Page"]
    
    def test_get_file_by_path(self):
        """Test finding a file by path."""
        project = ProjectData()
        pdf = PDFFileInfo(file_name="a.pdf", file_path="/a.pdf")
        project.pdf_files.append(pdf)
        assert project.get_file_by_path("/a.pdf") is not None
        assert project.get_file_by_path("/b.pdf") is None
    
    def test_remove_pdf_file(self):
        """Test removing a PDF file."""
        project = ProjectData()
        project.pdf_files.append(PDFFileInfo(file_name="a.pdf", file_path="/a.pdf"))
        project.pdf_files.append(PDFFileInfo(file_name="b.pdf", file_path="/b.pdf"))
        project.remove_pdf_file("/a.pdf")
        assert len(project.pdf_files) == 1
        assert project.pdf_files[0].file_path == "/b.pdf"
    
    def test_save_and_load_json(self, temp_dir, sample_project_data):
        """Test saving and loading a project to/from JSON."""
        path = os.path.join(temp_dir, "project.json")
        sample_project_data.save_to_json(path)
        
        assert os.path.exists(path)
        
        loaded = ProjectData.load_from_json(path)
        assert len(loaded.pdf_files) == 1
        assert len(loaded.columns) == 2
        assert loaded.pdf_files[0].file_name == "test.pdf"
        assert loaded.last_saved_time != ""
    
    def test_load_json_not_found(self):
        """Test loading from a non-existent file."""
        with pytest.raises(FileNotFoundError):
            ProjectData.load_from_json("/nonexistent/path.json")
    
    def test_save_json_content(self, temp_dir):
        """Test that saved JSON has correct structure."""
        project = ProjectData()
        project.add_column("Title")
        
        path = os.path.join(temp_dir, "test.json")
        project.save_to_json(path)
        
        with open(path, "r") as f:
            data = json.load(f)
        
        assert "pdf_files" in data
        assert "columns" in data
        assert "last_saved_time" in data
        assert data["columns"][0]["name"] == "Title"
