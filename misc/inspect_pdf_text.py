import pypdf
import re

def inspect_pdf(pdf_path):
    print(f"\n--- Inspecting {pdf_path} ---")
    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages[:2]: # First 2 pages should be enough
        text += page.extract_text() + "\n"
    
    # Print a few lines that look like subject definitions
    lines = text.split('\n')
    for line in lines[:50]:
        if re.search(r'\d+\.\d+', line) and len(line) > 10:
            print(f"DEBUG: {line}")

if __name__ == "__main__":
    inspect_pdf("eee new.pdf")
    inspect_pdf("civil new.pdf")
    inspect_pdf("cse new.pdf") # For comparison
