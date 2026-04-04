import libsql_client

URL = "https://result-finder-fahimfaisal570.aws-ap-south-1.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUzMjQ4MjEsImlkIjoiMDE5ZDU5OTktOWQwMS03NjJjLWI3Y2MtYmVlNTRiMmUzZWZiIiwicmlkIjoiN2U2ZjU3NDMtYjExMy00MjA5LWE4MWQtMTg2MGM5NjZmNTIxIn0.NOUrZRL2VX2oNoI1cE_XBs5kz0ZmF3eu_5CHcRetj2i_ul0CoQ3y9oYF_zUN6EV3ad_q2Ongr6YMWqcI_f06CQ"

def test():
    print(f"Testing HTTPS Connection to: {URL}")
    try:
        client = libsql_client.create_client_sync(URL, auth_token=TOKEN)
        res = client.execute("SELECT 1")
        print("✅ SUCCESS! Result:", res.rows[0][0])
        client.close()
    except Exception as e:
        print(f"❌ FAILED: {e}")

if __name__ == "__main__":
    test()
