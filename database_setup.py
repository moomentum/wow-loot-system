import sqlite3

connection = sqlite3.connect('loot_system.db')
connection.execute("PRAGMA foreign_keys = ON")
cursor = connection.cursor()

# Logs-Tabelle: Erweitert um eine optionale raid_id
cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeitstempel TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        aktion TEXT NOT NULL,
        details TEXT NOT NULL,
        raid_id INTEGER
    )
''')

# --- Alle anderen Tabellen (unverändert) ---
cursor.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_name TEXT NOT NULL UNIQUE, boss_name TEXT NOT NULL, raid_instanz TEXT NOT NULL, ruestungstyp TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member')''')
cursor.execute('''CREATE TABLE IF NOT EXISTS charaktere (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, charakter_name TEXT NOT NULL UNIQUE, klasse TEXT NOT NULL, rollen TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS raids (id INTEGER PRIMARY KEY AUTOINCREMENT, raid_instanz TEXT NOT NULL, raid_datum DATE NOT NULL, raid_zeit TIME NOT NULL, raid_titel TEXT, status TEXT NOT NULL DEFAULT 'Offen', punkte_vergeben INTEGER NOT NULL DEFAULT 0, erstellt_am TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS anmeldungen (id INTEGER PRIMARY KEY AUTOINCREMENT, spieler_id INTEGER NOT NULL, raid_id INTEGER NOT NULL, rolle_angemeldet TEXT NOT NULL, FOREIGN KEY (spieler_id) REFERENCES charaktere (id) ON DELETE CASCADE, FOREIGN KEY (raid_id) REFERENCES raids (id) ON DELETE CASCADE)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS loot_punkte (spieler_id INTEGER, item_id INTEGER, punkte INTEGER NOT NULL DEFAULT 0, FOREIGN KEY (spieler_id) REFERENCES charaktere (id) ON DELETE CASCADE, FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE, PRIMARY KEY (spieler_id, item_id))''')
cursor.execute('''CREATE TABLE IF NOT EXISTS reservierungen (anmeldung_id INTEGER NOT NULL, item_id INTEGER NOT NULL, FOREIGN KEY (anmeldung_id) REFERENCES anmeldungen (id) ON DELETE CASCADE, FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE, PRIMARY KEY (anmeldung_id, item_id))''')
cursor.execute('''CREATE TABLE IF NOT EXISTS wishlist (charakter_id INTEGER NOT NULL, item_id INTEGER NOT NULL, prioritaet INTEGER NOT NULL, FOREIGN KEY (charakter_id) REFERENCES charaktere (id) ON DELETE CASCADE, FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE, PRIMARY KEY (charakter_id, item_id))''')

connection.commit()
connection.close()
print("Finale Datenbankstruktur mit Raid-Archiv-Unterstützung wurde erstellt!")