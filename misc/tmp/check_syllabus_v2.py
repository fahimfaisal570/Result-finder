from pypdf import PdfReader
import re

pdf_path = "eee new.pdf"
reader = PdfReader(pdf_path)
text = ""
for page in reader.pages:
    text += page.extract_text() or ""

# Look for all codes in 2nd year 2nd sem (usually 22xx)
codes = re.findall(r'([A-Z]{2,6}\s*22\d{2})\b', text)
print(f"Unique 22xx codes found: {sorted(set(codes))}")

# Print context for 2201 and 2202
for code in ['2201', '2202']:
    pattern = re.compile(rf'([A-Z]{{2,6}}\s*{code}.*?)(?=\n[A-Z]{{2,6}}\s*\d{{4}}|\n\n|\Z)', re.I | re.S)
    match = pattern.search(text)
    if match:
        print(f"\n--- {code} Context ---")
        print(match.group(0))
    else:
        print(f"\n--- {code} not found ---")

# Also look for 2nd Year 2nd Semester heading
heading = re.search(r'2nd\s*Year\s*2nd\s*Semester.*?(?=\n\n|\Z)', text, re.I | re.S)
if heading:
    print("\n--- 2nd Year 2nd Sem Syllabus Table/Header ---")
    print(heading.group(0))

# Try to find the summary table of credits/marks
summary = re.search(r'Summary of.*?(?=\n\n|\Z)', text, re.I | re.S)
if summary:
    print("\n--- Summary Info ---")
    print(summary.group(0))
