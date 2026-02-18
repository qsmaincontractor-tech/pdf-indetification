#Objective & Operation:
- To extract the folder document path and content and export to a excel file.
- The extracted data column can be defined by user, but all for the text-based data
- If no vector-based text data can be extracted from the PDF page, then OCR will be applied to extract the text data

#UI Design:
1. All ui compoenets will be saved in ui folder Function\Identification\ui
2. 3 columns design + Top Toolbar + Bottom status bar:

    1st column: PDF Page List
        - Tree view to show the list of PDF pages for imported PDF files
        - Header contains <strong>Expand All</strong> / <strong>Collapse All</strong> buttons to expand/collapse file entries
        - When selecting a PDF page, the content of the page will be shown in the 3rd column
        - the 2nd column will be highlighted with the extracted data of the selected PDF page
        - File nodes are expanded by default when populated

    2nd column: Table for extracted data
        - file name, file path (Default - Hide), extracted data 1, extracted data 2, ...
        - the extracted data can be defined by user, for example, it can be the number of pages, the number of tables, the number of images, etc.
        - can be sorted/filtered by file name, file path, extracted data 1, extracted data 2, ...
        - clicking a data cell will select that column for box drawing and — if a drawn box already exists for that cell — the PDF viewer will focus and centre on that box so it is immediately visible
        - the bottom of the table has button
            - Add new extracted data: Name
            - Remove extracted data: Name
            - button to pop-up menu: hide/show table column including the file name and file path column

    3rd column: PDF Page Content
        - Show the image of the selected PDF page in the 1st column
        - can be zoomed in/out, and fit to width/height
        - ctrl + mouse wheel to zoom in/out
        - zoom percentage spin text box to show the current zoom percentage, and can be edited to set the zoom percentage
        - the zoom percentage increment/decrement step is 5%
        - ctrl + press middle mouse button to pan the image
        - Draw the box on the PDF page to prepare for data extraction
            - the box can be moved, resized, and deleted
            - the box will be highlighted in the 2nd column when selected
            - Select the cell in the 2nd column and the corresponding box will be highlighted in the 3rd column; the viewer will also attempt to centre/focus that box so it is visible to the user
            - if drag the box anywhere outside the existing box, it will be changed to new box
            - for example, I click the "Page" (custom extracted data) column cell in 2nd column, then the corresponding box will be highlighted in the 3rd column, if I drag the box to anywhere outside the existing box, then it will be changed to new box, and the "Page" column cell in 2nd column will be updated with the new box position and size
        - All extracted data can be manually edited in the 2nd column. if the user want to restored the result of the auto extraction, he can click "Recongize Text" at top toolbar

    Top Toolbar:
        - Import PDF file(s) button: select a folder directory, and walk through all folder and subfolder to find PDF files, then extract the PDF page list and show in the 1st column, and extract the data defined by user and show in the 2nd column
        - Save Button: save as JSON file, including the PDF file list, PDF page list, extracted data, and the box information, last saved time, last pdf page selected for future opening and loading
        - Load Button: load the JSON file 
        - Clear Extracted Data button: clear all extracted data in 2nd column for selected PDF page(s) in the 1st column, and clear the corresponding boxes in the 3rd column
        - Delete PDF file(s) button: delete the selected PDF file(s) in the 1st column, and remove the corresponding data in the 2nd column and the corresponding boxes in the 3rd column
        - Apply the drawn box to selected PDF page(s) button: apply the drawn box relative coordinates to the selected PDF page(s) in the 1st column, and update the corresponding cell in the 2nd column with the box relative coordinates, and update the corresponding box in the 3rd column with the box relative coordinates
        - Export to Excel button, the excel has sheet:
            - PDF File List: file name, file path, number of pages, file size
            - PDF Page List: file name, file path, page number, extracted data 1, extracted data 2, ...
        - Recongize Text: Extract text data according to the drawn box for the selected PDF page(s) in the 1st column, and update the corresponding cell in the 2nd column with the extracted text data

    Status Bar:
        - Show the status of the application, such as "Ready", "Importing PDF files...", "Exporting to Excel...", "Clearing extracted data...", "Deleting PDF files...", "Applying drawn box to selected PDF pages...", etc.
        - Show the number of PDF files imported, the number of PDF pages extracted
        - Progress bar to show the progress of importing PDF files, exporting to Excel, clearing extracted data, deleting PDF files, applying drawn box to selected PDF pages, etc.
        - OCR availability indicator: displays `OCR: on` (green) or `OCR: off` (red) so the user can quickly see whether OCR fallback (Tesseract/PyMuPDF OCR) is available in the running environment.

#Technical Specification:
- The application will be developed using Python and PyQt5 for the UI, and use PyMuPDF for PDF processing and OCR.
- The application will be structured in a modular way, with separate modules for UI, PDF processing, data models, and utilities.
- The application will use a data model to store the PDF file list, PDF page list, extracted data, and box information, and use JSON for saving and loading the data.
- The application will handle errors gracefully, such as when importing PDF files, extracting data, applying drawn box to selected PDF pages, etc., and show appropriate error messages in the status bar.

#Test Cases:
- All test cases will be implemented using pytest framework
- save to Function\Identification\Test

#Documentation:
- The code will be well-documented with docstrings for all functions and classes, and comments for complex logic and important steps.
- in HTML format, with practical examples, diagrams. the html should be interactive and easy to navigate, with a clear structure and layout.
- Content of the documentation:
    - Introduction: Overview of the application, its features, and its use cases.
    - Installation: Step-by-step guide on how to install the application and its dependencies.
    - User Guide: Detailed instructions on how to use the application
    - Developer Guide: Explanation of the code structure, modules, data structures
    - Methodology: Explanation of the algorithms and techniques used for PDF processing, data extraction, and OCR.
    - API Reference: Detailed documentation of all functions, classes, and methods in the codebase, including their parameters, return values, and examples of usage.
    - Excel Export Format: Explanation of the format of the exported Excel file, including the structure of the sheets, columns, and data types. and the mapping between the extracted data and the Excel columns.
    - Test Cases: Explanation of the test cases implemented for the application, including the test scenarios, expected results, and how to run the tests.
    - Troubleshooting: Common issues and their solutions, such as errors during PDF import, data extraction, applying drawn box to selected PDF pages, etc.




