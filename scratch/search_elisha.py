import sqlite3

def main():
    conn = sqlite3.connect("../creator_forge.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    
    print("Searching database for 'elisha' or 'damu'...")
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table});")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Build query to search text columns for 'elisha'
        conditions = []
        for col in columns:
            conditions.append(f"CAST({col} AS TEXT) LIKE '%elisha%'")
            conditions.append(f"CAST({col} AS TEXT) LIKE '%damu%'")
            
        if not conditions:
            continue
            
        query = f"SELECT * FROM {table} WHERE " + " OR ".join(conditions)
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            if rows:
                print(f"Match found in table '{table}':")
                for r in rows:
                    print("  ", r)
        except Exception as e:
            print(f"Error searching {table}: {e}")
            
    conn.close()

if __name__ == '__main__':
    main()
