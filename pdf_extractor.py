"""
pdf_extractor.py — Strictly Isolated Department-Aware Credit Mapper
-------------------------------------------------------------------
Extracts subject credit hours from the three official syllabus PDFs 
and stores them in a NESTED credit_mapping.json:

{
  "CSE":   { "CSE-1101": 2.0, ... },
  "EEE":   { "EEE-1101": 3.0, "CSE-1101": 3.0, ... },
  "Civil": { "CE-101": 3.0, ... }
}

This ensures that the same course code across different departments 
can maintain strictly independent credit values.
"""

from pypdf import PdfReader
import re
import json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_code(raw: str) -> str:
    """Turn any spacing/case variant into DEPT-XXXX uppercase."""
    code = raw.strip().upper()
    code = re.sub(r'[\s\.]+', '-', code)
    code = re.sub(r'-+', '-', code)
    return code


def _last_valid_credit(text_segment: str) -> float | None:
    """Return the last number in 0.5–6.0 found in text_segment."""
    nums = re.findall(r'(\d+(?:\.\d+)?)', text_segment)
    for n in reversed(nums):
        try:
            v = float(n)
            if 0.5 <= v <= 6.0: return v
        except ValueError: pass
    return None


def _get_default_credit(code: str) -> float:
    """
    Last digit odd = Theory (3.0), Last digit even = Lab (1.5).
    """
    try:
        last_digit = int(code[-1])
        return 3.0 if last_digit % 2 != 0 else 1.5
    except: return 3.0


def _extract_all_text(pdf_path: str) -> str:
    print(f"[*] Reading {pdf_path}...")
    try:
        reader = PdfReader(pdf_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        print(f"    [!] Error reading PDF: {e}")
        return ""


# ---------------------------------------------------------------------------
# Universal Serial-Table Parser (EEE and Civil)
# ---------------------------------------------------------------------------

def _parse_serial_table(text: str, valid_prefixes: list) -> dict:
    text = re.sub(r'\*+', '', text)
    prefix_re = '|'.join(re.escape(p) for p in valid_prefixes)
    pattern = re.compile(
        r'(\d{1,2})\s+((?:' + prefix_re + r')\s+\d{3,4})',
        re.IGNORECASE
    )
    matches = list(pattern.finditer(text))
    
    mapping = {}
    for i, m in enumerate(matches):
        code = _normalize_code(m.group(2))
        start_idx = m.end()
        end_idx = matches[i+1].start() if i+1 < len(matches) else len(text)
        segment = text[start_idx:end_idx]
        
        credit = _last_valid_credit(segment)
        if not credit:
            credit = _get_default_credit(code)
        mapping[code] = credit
    return mapping


# ---------------------------------------------------------------------------
# CSE Parser
# ---------------------------------------------------------------------------

def _parse_cse(text: str) -> dict:
    text = re.sub(r'[\*\(\)]', ' ', text)
    anchor_pattern = re.compile(r'\b([A-Z]{2,6}[\-\s]\d{3,4})\b', re.IGNORECASE)
    matches = list(anchor_pattern.finditer(text))
    
    mapping = {}
    for i, m in enumerate(matches):
        code = _normalize_code(m.group(1))
        if "XXX" in code: continue
        
        start_idx = m.end()
        end_idx = matches[i+1].start() if i+1 < len(matches) else len(text)
        segment = text[start_idx:min(end_idx, start_idx + 300)]
        
        credit = _last_valid_credit(segment)
        if not credit:
            credit = _get_default_credit(code)
        mapping[code] = credit
    return mapping


# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------

def build_credit_mapping():
    # Final results: NESTED by department
    nested_results = {
        "CSE": {},
        "EEE": {},
        "Civil": {}
    }
    
    EEE_DEPS = ['EEE', 'CSE', 'PHY', 'CHEM', 'MATH', 'GED', 'ME', 'CE']
    CIVIL_DEPS = ['CE', 'PHY', 'CHEM', 'MATH', 'HUM', 'EEE', 'CSE', 'SHOP']
    
    config = [
        ("cse new.pdf",   _parse_cse, "CSE"),
        ("eee new.pdf",   lambda t: _parse_serial_table(t, EEE_DEPS), "EEE"),
        ("civil new.pdf", lambda t: _parse_serial_table(t, CIVIL_DEPS), "Civil"),
    ]
    
    for pdf_path, parser_fn, dept_key in config:
        print(f"[*] Extracting for department '{dept_key}' from {pdf_path}...")
        text = _extract_all_text(pdf_path)
        if not text: continue
        
        dept_map = parser_fn(text)
        print(f"    -> Found {len(dept_map)} unique courses for {dept_key}")
        nested_results[dept_key] = dept_map
            
    with open("credit_mapping.json", "w") as f:
        json.dump(nested_results, f, indent=4, sort_keys=True)
        
    print(f"\n[+] Strictly isolated credit mapping saved to credit_mapping.json")

if __name__ == "__main__":
    build_credit_mapping()
