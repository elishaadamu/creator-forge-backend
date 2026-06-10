import sqlite3

def main():
    conn = sqlite3.connect("../creator_forge.db")
    cursor = conn.cursor()
    
    print("--- Recent Audit Logs ---")
    cursor.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 50;")
    for row in cursor.fetchall():
        print(row)
        
    print("\n--- Suppression List ---")
    cursor.execute("SELECT * FROM suppression_list;")
    for row in cursor.fetchall():
        print(row)

    print("\n--- User Profiles ---")
    cursor.execute("SELECT * FROM user_profiles;")
    for row in cursor.fetchall():
        print(row)

    conn.close()

if __name__ == '__main__':
    main()
