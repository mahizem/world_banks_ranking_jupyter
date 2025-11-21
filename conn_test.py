import psycopg2

DB_CONFIG = {
    'host': 'localhost',
    'database': 'postgres',
    'user': 'postgres',
    'password': 'ilovemum21@6', # Use UNENCODED password for direct psycopg2 test
    'port': '5432'
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    print("SUCCESS: Connection established.")
    conn.close()
except Exception as e:
    print(f"FAILURE: Could not connect. Error: {e}")