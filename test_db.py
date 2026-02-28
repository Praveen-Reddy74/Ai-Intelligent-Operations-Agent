from database import get_connection

conn = get_connection()
cur = conn.cursor()

cur.execute("SELECT * FROM inventory;")
rows = cur.fetchall()

for row in rows:
    print(row)

cur.close()
conn.close()