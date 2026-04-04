import re

def _normalize_code(raw: str) -> str:
    code = raw.strip().upper()
    code = re.sub(r'[\s\.]+', '-', code)
    code = re.sub(r'-+', '-', code)
    return code

def _last_valid_credit(text_segment: str) -> float:
    nums = re.findall(r'\b(\d+(?:\.\d+)?)\b', text_segment)
    for n in reversed(nums):
        try:
            v = float(n)
            if 0.5 <= v <= 6.0: return v
        except: pass
    return None

def test_eee_parser(text):
    text = re.sub(r'\*+', '', text)
    # The problem is EEE has multiple entries per line for electives
    # Let's find ALL patterns like "11 EEE 4117"
    pattern = re.compile(r'(\d{1,2})\s+([A-Z]{2,6}\s+\d{3,4})', re.IGNORECASE)
    matches = list(pattern.finditer(text))
    
    results = {}
    for i, m in enumerate(matches):
        serial = m.group(1)
        code = _normalize_code(m.group(2))
        
        # Segment is between this match and next match
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        segment = text[start:end]
        
        credit = _last_valid_credit(segment)
        if credit:
            results[code] = credit
        else:
            print(f"FAILED TO FIND CREDIT for {code} in segment: '{segment.strip()}'")
            
    print(f"Total found: {len(results)}")
    return results

if __name__ == "__main__":
    with open("debug_eee.txt", "r") as f:
        content = f.read()
    test_eee_parser(content)
