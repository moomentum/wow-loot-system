import sqlite3, csv, sys
def import_items_from_csv(filename):
    conn = sqlite3.connect('loot_system.db')
    cursor = conn.cursor()
    try:
        with open(filename, mode='r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)
            next(csv_reader)
            item_count = 0
            for row in csv_reader:
                if len(row) >= 4:
                    item_name, boss_name, raid_instanz, ruestungstyp = [col.strip() for col in row]
                    cursor.execute("INSERT OR REPLACE INTO items (item_name, boss_name, raid_instanz, ruestungstyp) VALUES (?, ?, ?, ?)",
                                 (item_name, boss_name, raid_instanz, ruestungstyp))
                    item_count += 1
        conn.commit()
        conn.close()
        print(f"\nImport aus '{filename}' erfolgreich. {item_count} Items verarbeitet.")
    except Exception as e: print(f"\nFehler: {e}")
if __name__ == '__main__':
    if len(sys.argv) > 1: import_items_from_csv(sys.argv[1])
    else: print("Beispiel: python importer.py dateiname.csv")