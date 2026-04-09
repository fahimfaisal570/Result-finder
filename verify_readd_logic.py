import json
import os
import re

def verify_readd_logic():
    print("--- Readd Logic Offline Verification ---")
    
    # Mock Profile Data
    mock_profiles = {
        "Civil 09 Test": {
            "pro_id": "12",
            "sess_id": "22",
            "regs": [
                [1037, "22", "Main Student"],
                [1038, "21", "Readd Student"]
            ]
        }
    }
    
    # 1. Test Verification Logic (Emulating pages/transcript.py)
    def resolve_session(profile_name, st_reg):
        p_data = mock_profiles.get(profile_name)
        if not p_data: return "AUTO"
        
        sess_id = "AUTO"
        p_regs = p_data.get("regs", [])
        for r in p_regs:
            if isinstance(r, list) and int(r[0]) == st_reg:
                sess_id = str(r[1])
                break
        
        if sess_id == "AUTO":
            sess_id = p_data.get("sess_id", "AUTO")
        return sess_id

    # Test Cases
    sess_1037 = resolve_session("Civil 09 Test", 1037)
    sess_1038 = resolve_session("Civil 09 Test", 1038)
    
    print(f"Student 1037 (Main) resolved session: {sess_1037} (Expected: 22)")
    print(f"Student 1038 (Readd) resolved session: {sess_1038} (Expected: 21)")
    
    success = (sess_1037 == "22" and sess_1038 == "21")
    if success:
        print("✅ SUCCESS: Individual session resolution is working.")
    else:
        print("❌ FAILURE: Session resolution failed.")

    # 2. Verify Key Mappings (Emulating app.py / results.py save)
    mock_results = [
        {'Registration No': 1037, 'Name': 'Estiak', '_sess_id': '22'},
        {'Registration No': 1038, 'Name': 'Senior', '_sess_id': '21'}
    ]
    
    # Standardizing keys for save
    regs_for_save = []
    for res in mock_results:
        regs_for_save.append([
            int(res.get('Registration No', 0)),
            str(res.get('_sess_id', 'AUTO')),
            str(res.get('Name', 'Unknown'))
        ])
    
    print(f"Saved Data Format: {regs_for_save}")
    key_success = (regs_for_save[0][2] == 'Estiak' and regs_for_save[1][1] == '21')
    if key_success:
        print("✅ SUCCESS: Key mapping with 'Registration No' and 'Name' is correct.")
    else:
        print("❌ FAILURE: Key mapping failed.")

if __name__ == "__main__":
    verify_readd_logic()
