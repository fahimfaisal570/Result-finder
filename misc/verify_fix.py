import os
import libsql_client
import streamlit as st

# Load secrets manually if running locally for debugging
# In a real scenario, this would be in .streamlit/secrets.toml
# For this test, I'll assume they are available via st.secrets or environment
turso_url = "https://result-finder-fahimfaisal570.turso.io"
turso_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

def test_remote_insert():
    client = libsql_client.create_client_sync(turso_url, auth_token=turso_token)
    
    print("--- Dropping table if exists ---")
    try:
        client.execute("DROP TABLE IF EXISTS test_table")
    except Exception as e:
        print(f"Drop error: {e}")

    print("--- Creating table without 'main.' prefix ---")
    try:
        client.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
        print("Success: Created table without prefix.")
    except Exception as e:
        print(f"Create error: {e}")

    print("--- Attempting insert ---")
    try:
        client.execute("INSERT INTO test_table (name) VALUES ('test_user')")
        print("Success: Inserted row.")
    except Exception as e:
        print(f"Insert error: {e}")

    print("--- Checking tables ---")
    try:
        res = client.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for row in res.rows:
            print(f"Table found: {row[0]}")
    except Exception as e:
        print(f"Check error: {e}")

    client.close()

if __name__ == "__main__":
    test_remote_insert()
