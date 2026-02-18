
try:
    from utils.pdf_processing import is_ocr_available
except ImportError:
    # Need to make sure we can import relative to root
    import sys
    import os
    sys.path.append(os.getcwd())
    from utils.pdf_processing import is_ocr_available

print(f"Checking is_ocr_available()...")
result = is_ocr_available()
print(f"Result: {result}")
if not result:
    print("Correctly detected that OCR is unavailable.")
else:
    print("WARNING: detected OCR is available, but reproduction showed it wasn't!")
