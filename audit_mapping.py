import json

def audit_mapping():
    try:
        with open('credit_mapping.json', 'r') as f:
            mapping = json.load(f)
    except:
        print("credit_mapping.json not found or invalid.")
        return

    stats = {'CSE': 0, 'EEE': 0, 'CE': 0, 'MATH': 0, 'HUM': 0, 'GED': 0, 'PHY': 0, 'CHEM': 0}
    for code in mapping:
        for key in stats:
            if key in code:
                stats[key] += 1
                break
    
    print("--- Credit Mapping Audit ---")
    for k, v in stats.items():
        print(f"{k}: {v} subjects")
    print(f"Total: {len(mapping)} subjects")

if __name__ == "__main__":
    audit_mapping()
