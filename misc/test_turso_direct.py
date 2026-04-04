import libsql
import time

URL = "libsql://result-finder-fahimfaisal570.aws-ap-south-1.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

def test():
    print(f"Connecting to: {URL}")
    conn = libsql.connect(URL, auth_token=TOKEN)
    cur = conn.cursor()
    
    print("Testing manual table creation...")
    try:
        cur.execute("DROP TABLE IF EXISTS test_sync")
        cur.execute("CREATE TABLE test_sync (id INTEGER PRIMARY KEY, val TEXT)")
        cur.execute("INSERT INTO test_sync (id, val) VALUES (1, 'Hello Turso')")
        print("Committing...")
        conn.commit() # Explicit commit
        
        print("Verifying immediate persistence...")
        cur.execute("SELECT * FROM test_sync")
        print("Result:", cur.fetchone())
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        print("Tables known to server:", [r[0] for r in cur.fetchall()])
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
