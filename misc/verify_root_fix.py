import json
import re
import sqlite3
import os

# Mock the database mapping for testing
MOCK_SYLLABUS = {
    "CE": {
        "CE-401": 3.0,
        "CE-402": 3.0,
        "CE-403": 3.0,
        "MATH-401": 3.0
    }
}

def mock_get_dept(p): return "CE"

def test_universal_regex():
    html = """
    <table id='results'>
        <tr class='header'><th>Code</th><th>Name</th><th>Grade</th><th>GP</th></tr>
        <tr style='background:white'><td>1</td><td>CE 402</td><td>Mechanics</td><td>B</td><td>3.00</td></tr>
        <tr class='fail'><td>2</td><td>CE 403</td><td>Hydraulics</td><td style='color:red'>F</td><td>0.00</td></tr>
        <tr><td>3</td><td>HUM 401</td><td>Economics</td><td>A</td><td>3.75</td></tr>
    </table>
    """
    
    subjects = []
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    for row_content in rows:
        cells = re.findall(r'<(?:td|th)[^>]*>(.*?)</(?:td|th)>', row_content, re.DOTALL | re.IGNORECASE)
        cells = [re.sub(r'<[^>]*>', '', c).strip() for c in cells]
        
        # Identification logic
        code = None
        for c in cells:
            if re.match(r'^[A-Z]{2,6}[\-\s]*\d{3,4}[\*]*$', c, re.I):
                code = c; break
        if not code: continue
        
        gp_val = "0.00"
        for c in reversed(cells):
            if re.match(r'^[\d\.]+$', c) or c in ['-', 'F']:
                try: gp_val = str(round(float(c), 2))
                except: gp_val = "0.00"
                break
        
        subjects.append({'code': code, 'gp': float(gp_val)})
    
    print("--- Scraper Test Result ---")
    for s in subjects:
        print(f"  Found {s['code']} -> GP: {s['gp']}")
    return subjects

def test_inference(scraped):
    print("\n--- Syllabus-Aware Inference Test ---")
    scraped_codes = {s['code'].upper().replace(' ', '-') for s in scraped}
    dept_map = MOCK_SYLLABUS["CE"]
    
    inferred = []
    for code in dept_map:
        if code not in scraped_codes:
            print(f"  [!] Missing {code} from scrape. Inferring Failure (GP 0.0)")
            inferred.append(code)
    
    if not inferred:
        print("  All syllabus subjects present in scrape.")

if __name__ == "__main__":
    found = test_universal_regex()
    test_inference(found)
