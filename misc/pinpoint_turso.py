import requests
import json

URL = "https://result-finder-fahimfaisal570.aws-ap-south-1.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

def pinpoint():
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # 1. Fetch remote schema
    payload = {
        "requests": [{"type": "execute", "stmt": {"sql": "SELECT name, sql FROM sqlite_master WHERE type='table'"}}]
    }
    r = requests.post(f"{URL}/v2/pipeline", headers=headers, json=payload)
    results = r.json().get("results", [])
    
    print("--- REMOTE SCHEMA ON TURSO ---")
    if results and results[0]["type"] == "ok":
        rows = results[0]["response"]["result"]["rows"]
        for row in rows:
            name = row[0]["value"]
            sql = row[1]["value"]
            print(f"Table: {name}")
            print(f"SQL: {sql}")
            print("-" * 30)
    else:
        print(f"Error fetching schema: {results}")

    # 2. Try a test insert that failed before
    test_sql = 'INSERT INTO "exam_results" (id, profile_name, reg_no, exam_id) VALUES(9999, "test_profile", 9999, "1699")'
    payload_test = {
        "requests": [{"type": "execute", "stmt": {"sql": test_sql}}]
    }
    r2 = requests.post(f"{URL}/v2/pipeline", headers=headers, json=payload_test)
    print("\n--- TEST INSERT RESULT ---")
    print(json.dumps(r2.json(), indent=2))

if __name__ == "__main__":
    pinpoint()
