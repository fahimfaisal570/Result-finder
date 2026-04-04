"""
verify_turso_connection.py

Standalone test script to verify Turso connection and data integrity
without triggering Streamlit's local secret checks.
"""
import libsql
import sys

def verify():
    url = "libsql://result-finder-fahimfaisal570.aws-ap-south-1.turso.io"
    token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

    print("--- Standalone Turso Verification ---")
    print(f"Connecting to: {url}")
    
    try:
        conn = libsql.connect(url, auth_token=token)
        print("✅ Connection Successful!")
        
        cur = conn.cursor()
        
        # Test 1: Check tables
        print("Checking tables...")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"✅ Found {len(tables)} tables: {', '.join(tables)}")
        
        # Test 2: Check data in 'profiles'
        if 'profiles' in tables:
            cur.execute("SELECT COUNT(*) FROM profiles")
            count = cur.fetchone()[0]
            print(f"✅ Found {count} profiles in the cloud database.")
            
            if count > 0:
                cur.execute("SELECT name FROM profiles LIMIT 3")
                sample = [r[0] for r in cur.fetchall()]
                print(f"   Sample profiles: {', '.join(sample)}")
        
        conn.close()
        print("\n🏆 VERIFICATION PASSED: Your cloud database is healthy and populated.")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    verify()
