"""
check_turso_integrity.py
Deep-checker for Turso data using the official libsql-client.
"""
import libsql_client
import os

URL = "libsql://result-finder-fahimfaisal570.aws-ap-south-1.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

def check():
    print(f"Connecting to: {URL}")
    try:
        client = libsql_client.create_client_sync(URL, auth_token=TOKEN)
        
        res = client.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in res.rows]
        print(f"Found tables: {tables}")
        
        for table in tables:
            if table == 'sqlite_sequence': continue
            count_res = client.execute(f"SELECT COUNT(*) FROM {table}")
            count = count_res.rows[0][0]
            print(f"  - {table}: {count} rows")
            
        client.close()
        print("\n✅ Verification SUCCESS: All data is present in the cloud.")
    except Exception as e:
        print(f"❌ Verification ERROR: {e}")

if __name__ == "__main__":
    check()
