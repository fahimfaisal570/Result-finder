import re

def test_precision_inference():
    # Mock data
    scraped_codes = ["EEE-2201", "EEE-2202", "MATH-2201", "GED-2201"]
    dept_map = {
        "EEE-1101": 3.0,
        "EEE-1102": 1.5,
        "EEE-2201": 3.0,
        "EEE-2209": 3.0,  # This one IS missing and SHOULD be inferred
        "EEE-3101": 4.0,
        "MATH-2201": 3.0
    }
    
    # New logic simulation
    scraped_levels = set()
    for c in scraped_codes:
        m = re.match(r'^([A-Z]{2,6}[\-\s]*\d{2})', c, re.I)
        if m: scraped_levels.add(m.group(1).upper())
    
    print(f"Scraped Levels identified: {scraped_levels}")
    
    inferred = []
    for code in dept_map:
        m = re.match(r'^([A-Z]{2,6}[\-\s]*\d{2})', code, re.I)
        level = m.group(1).upper() if m else None
        
        if level in scraped_levels and code not in scraped_codes:
            print(f"  [+] Inferring Failure: {code} (Matches level {level})")
            inferred.append(code)
        elif code not in scraped_codes:
            print(f"  [-] Ignoring: {code} (Level {level} not in scrape)")

    print("\n--- Summary ---")
    print(f"Total inferred: {len(inferred)}")
    if "EEE-2209" in inferred and "EEE-1101" not in inferred:
        print("✅ SUCCESS: Precision Level Inference working correctly.")
    else:
        print("❌ FAILURE: Logic still too broad or too narrow.")

if __name__ == "__main__":
    test_precision_inference()
