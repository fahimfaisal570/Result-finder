import requests
import json

URL = "https://result-finder-fahimfaisal570.aws-ap-south-1.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

def debug_response():
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    payload = {
        "requests": [{"type": "execute", "stmt": {"sql": "SELECT COUNT(*) FROM profiles"}}]
    }
    r = requests.post(f"{URL}/v2/pipeline", headers=headers, json=payload)
    print("Status:", r.status_code)
    print("Response JSON Structure:")
    print(json.dumps(r.json(), indent=2))

if __name__ == "__main__":
    debug_response()
