import pypdf

def extract_to_file(pdf_path, output_path):
    print(f"[*] Extracting {pdf_path} -> {output_path}")
    reader = pypdf.PdfReader(pdf_path)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, page in enumerate(reader.pages[:5]): # First 5 pages
            f.write(f"\n--- PAGE {i+1} ---\n")
            f.write(page.extract_text())

if __name__ == "__main__":
    extract_to_file("cse new.pdf", "debug_cse.txt")
    extract_to_file("eee new.pdf", "debug_eee.txt")
    extract_to_file("civil new.pdf", "debug_civil.txt")
