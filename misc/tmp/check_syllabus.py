from pypdf import PdfReader
import re

pdf_path = "eee new.pdf"
reader = PdfReader(pdf_path)
text = ""
for page in reader.pages:
    text += page.extract_text() or ""

# Find EEE 2202 in the syllabus
match = re.search(r'EEE\s*2202.*?(?=\n\n|\Z)', text, re.I | re.S)
if match:
    print("--- EEE 2202 Syllabus Info ---")
    print(match.group(0))
else:
    print("EEE 2202 not found in syllabus PDF.")

# Also list all 22xx courses to see the pattern
matches = re.findall(r'([A-Z]{2,6}\s*22\d{2})\s+([^\n]+)', text)
print("\n--- 2nd Year 2nd Sem Courses (22xx) ---")
for code, name in matches:
    if '22' in code:
        print(f"{code}: {name}")
