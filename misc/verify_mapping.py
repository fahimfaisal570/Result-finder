import json

def verify_isolation():
    try:
        with open('credit_mapping.json', 'r') as f:
            mapping = json.load(f)
            
        print("--- Structural Verification ---")
        for dept in ["CSE", "EEE", "Civil"]:
            if dept in mapping:
                count = len(mapping[dept])
                print(f"[Department: {dept}] Found {count} courses.")
                
                # Spot check common codes
                for code in ["CSE-1101", "MATH-1105", "PHY-101"]:
                    if code in mapping[dept]:
                        print(f"  - {code}: {mapping[dept][code]} credits")
            else:
                print(f"[!] {dept} bucket is MISSING!")
        
        print("\n--- Summary ---")
        total = sum(len(m) for m in mapping.values())
        print(f"Total unique department-course pairs: {total}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_isolation()
