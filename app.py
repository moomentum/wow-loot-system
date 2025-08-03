import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from collections import Counter
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'dein_sehr_geheimer_schluessel_muss_gesetzt_sein' 
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Bitte melde dich an, um diese Seite zu sehen."
login_manager.login_message_category = "error"

# =============================================================
# GLOBALE EINSTELLUNGEN
# =============================================================
ALLOW_DUPLICATE_RESERVATIONS = False
RESERVATION_SLOTS = { 'Tank': 3, 'Heal': 3, 'DPS': 2, 'default': 3 }
WISHLIST_SLOTS = 6
ITEM_CLASS_MAP = {
    'Stoff': ['Magier', 'Hexenmeister', 'Priester', 'Druide', 'Schamane'],
    'Leder': ['Schurke', 'Druide', 'Schamane', 'Krieger'],
    'Kette': ['Jäger', 'Schamane'],
    'Platte': ['Krieger', 'Paladin'],
    'Zauberstab': ['Magier', 'Hexenmeister', 'Priester'],
    'Schusswaffe': ['Jäger', 'Krieger', 'Schurke'],
    'Wurfwaffe': ['Krieger', 'Schurke'],
    'Relikt': ['Schamane', 'Druide', 'Paladin']
}
# =============================================================

class User(UserMixin):
    def __init__(self, id, username, role): self.id = id; self.username = username; self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection(); user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone(); conn.close()
    return User(id=user_data['id'], username=user_data['username'], role=user_data['role']) if user_data else None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Für diese Aktion sind Admin-Rechte erforderlich.', 'error'); return redirect(url_for('raid_liste'))
        return f(*args, **kwargs)
    return decorated_function

def get_db_connection():
    conn = sqlite3.connect('loot_system.db'); conn.execute("PRAGMA foreign_keys = ON"); conn.row_factory = sqlite3.Row
    return conn

def log_action(aktion, details, raid_id=None):
    conn = get_db_connection(); user = current_user.username if current_user.is_authenticated else "System"
    full_details = f"[{user}] {details}"; conn.execute('INSERT INTO logs (aktion, details, raid_id) VALUES (?, ?, ?)', (aktion, full_details, raid_id)); conn.commit(); conn.close()

# === BENUTZER-AUTHENTIFIZIERUNG & KONTO ===
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('raid_liste'))
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']; conn = get_db_connection()
        if conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone():
            flash('Dieser Benutzername ist bereits vergeben.', 'error'); return redirect(url_for('register'))
        password_hash = generate_password_hash(password)
        role = 'admin' if conn.execute('SELECT COUNT(id) as count FROM users').fetchone()['count'] == 0 else 'member'
        conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', (username, password_hash, role)); conn.commit(); conn.close()
        flash(f'Account erstellt! Der erste User ist automatisch Admin. Bitte einloggen.', 'success'); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('raid_liste'))
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']; conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone(); conn.close()
        if user_data and check_password_hash(user_data['password_hash'], password):
            login_user(User(id=user_data['id'], username=user_data['username'], role=user_data['role'])); return redirect(url_for('raid_liste'))
        else: flash('Falscher Benutzername oder Passwort.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); return redirect(url_for('login'))

# === ÖFFENTLICHE & BENUTZER-SEITEN ===
@app.route('/')
def index(): 
    return redirect(url_for('raid_liste'))

@app.route('/raids')
def raid_liste():
    conn = get_db_connection(); raids = conn.execute("SELECT * FROM raids WHERE status != 'Abgeschlossen' ORDER BY raid_datum DESC, raid_zeit DESC").fetchall(); conn.close()
    return render_template('raid_liste.html', raid_liste=raids)

@app.route('/punkte')
@login_required
def punkte_uebersicht():
    sort_by = request.args.get('sort', 'item_name'); order = request.args.get('order', 'asc')
    allowed_sorts = ['item_name', 'charakter_name', 'punkte']
    if sort_by not in allowed_sorts: sort_by = 'item_name'
    if order not in ['asc', 'desc']: order = 'asc'
    conn = get_db_connection()
    query = f"SELECT i.item_name, c.charakter_name, lp.punkte FROM loot_punkte lp JOIN charaktere c ON lp.spieler_id = c.id JOIN items i ON lp.item_id = i.id WHERE lp.punkte > 0 ORDER BY {sort_by} {order}"
    punkte_liste = conn.execute(query).fetchall(); conn.close()
    next_orders = {col: 'desc' if sort_by == col and order == 'asc' else 'asc' for col in allowed_sorts}
    return render_template('punkte_uebersicht.html', punkte_liste=punkte_liste, current_sort=sort_by, current_order=order, next_orders=next_orders)

@app.route('/raid/<int:raid_id>/anmelden', methods=['GET', 'POST'])
@login_required
def raid_anmelden(raid_id):
    conn = get_db_connection(); raid = conn.execute('SELECT * FROM raids WHERE id = ?', (raid_id,)).fetchone()
    if raid['status'] != 'Offen': return "Anmeldungen für diesen Raid sind geschlossen.", 403
    charaktere_des_users = conn.execute('SELECT * FROM charaktere WHERE user_id = ? ORDER BY charakter_name', (current_user.id,)).fetchall()
    if request.method == 'POST':
        spieler_id = request.form['spieler_id']
        if not conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (spieler_id, current_user.id)).fetchone():
            flash('Ungültige Charakterauswahl.', 'error'); return redirect(url_for('raid_anmelden', raid_id=raid_id))
        if conn.execute('SELECT id FROM anmeldungen WHERE spieler_id = ? AND raid_id = ?', (spieler_id, raid_id)).fetchone():
            flash('Dieser Charakter ist bereits für den Raid angemeldet.', 'error'); return redirect(url_for('raid_anmelden', raid_id=raid_id))
        rolle_angemeldet = request.form['rolle_angemeldet']; item_ids = [item_id for item_id in request.form.getlist('item_ids') if item_id]
        cursor = conn.cursor(); cursor.execute('INSERT INTO anmeldungen (spieler_id, raid_id, rolle_angemeldet) VALUES (?, ?, ?)', (spieler_id, raid_id, rolle_angemeldet))
        anmeldung_id = cursor.lastrowid
        processed_items = list(set(item_ids))
        for item_id in processed_items: conn.execute('INSERT OR IGNORE INTO reservierungen (anmeldung_id, item_id) VALUES (?, ?)', (anmeldung_id, item_id))
        conn.commit(); conn.close(); flash(f'Anmeldung erfolgreich!', 'success'); return redirect(url_for('raid_liste'))
    
    angemeldete_spieler = conn.execute('SELECT spieler_id FROM anmeldungen WHERE raid_id = ?', (raid_id,)).fetchall()
    angemeldete_spieler_ids = [row['spieler_id'] for row in angemeldete_spieler]
    item_liste_rows = conn.execute('SELECT * FROM items WHERE raid_instanz = ? ORDER BY boss_name, item_name', (raid['raid_instanz'],)).fetchall(); conn.close()
    item_liste_dicts = [dict(row) for row in item_liste_rows]
    return render_template('raid_anmelden.html', raid=raid, spieler_liste=charaktere_des_users, item_liste=item_liste_dicts, allow_duplicates=ALLOW_DUPLICATE_RESERVATIONS, angemeldete_spieler_ids=angemeldete_spieler_ids, reservation_slots=RESERVATION_SLOTS)

@app.route('/meine-anmeldungen')
@login_required
def meine_anmeldungen():
    conn = get_db_connection()
    anmeldungen = conn.execute('SELECT a.id as anmeldung_id, a.rolle_angemeldet, c.charakter_name, r.* FROM anmeldungen a JOIN charaktere c ON a.spieler_id = c.id JOIN raids r ON a.raid_id = r.id WHERE c.user_id = ? AND r.status != "Abgeschlossen" ORDER BY r.raid_datum, r.raid_zeit', (current_user.id,)).fetchall(); conn.close()
    return render_template('meine_anmeldungen.html', anmeldungen=anmeldungen)

@app.route('/anmeldung/<int:anmeldung_id>/stornieren', methods=['POST'])
@login_required
def anmeldung_stornieren(anmeldung_id):
    conn = get_db_connection()
    anmeldung = conn.execute('SELECT a.*, c.user_id, r.status, r.punkte_vergeben FROM anmeldungen a JOIN charaktere c ON a.spieler_id = c.id JOIN raids r ON a.raid_id = r.id WHERE a.id = ?', (anmeldung_id,)).fetchone()
    if not anmeldung or anmeldung['user_id'] != current_user.id:
        flash("Anmeldung nicht gefunden oder keine Berechtigung.", "error"); return redirect(url_for('meine_anmeldungen'))
    if anmeldung['status'] != 'Offen':
        flash("Stornierung nicht möglich, da der Raid bereits gesperrt ist.", "error"); return redirect(url_for('meine_anmeldungen'))
    if anmeldung['punkte_vergeben']:
        reservierungen = conn.execute('SELECT item_id FROM reservierungen WHERE anmeldung_id = ?', (anmeldung_id,)).fetchall(); item_ids = [r['item_id'] for r in reservierungen]; item_counts = Counter(item_ids)
        for item_id, anzahl in item_counts.items():
            conn.execute('UPDATE loot_punkte SET punkte = punkte - ? WHERE spieler_id = ? AND item_id = ? AND punkte >= ?', (anzahl, anmeldung['spieler_id'], item_id, anzahl))
    conn.execute('DELETE FROM anmeldungen WHERE id = ?', (anmeldung_id,)); conn.commit(); conn.close()
    log_action("Anmeldung storniert", f"Anmeldung ID {anmeldung_id} wurde storniert."); flash("Anmeldung erfolgreich storniert.", "success")
    return redirect(url_for('meine_anmeldungen'))

# === PROFIL & WISHLIST FUNKTIONEN ===
@app.route('/profil')
@login_required
def profil():
    conn = get_db_connection(); charaktere = conn.execute('SELECT * FROM charaktere WHERE user_id = ? ORDER BY charakter_name', (current_user.id,)).fetchall(); conn.close()
    return render_template('profil.html', charaktere=charaktere)

@app.route('/api/charakter/<int:charakter_id>/punkte')
@login_required
def api_charakter_punkte(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: return jsonify({'error': 'Unauthorized'}), 403
    punkte_liste = conn.execute('SELECT i.item_name, lp.punkte FROM loot_punkte lp JOIN items i ON lp.item_id = i.id WHERE lp.spieler_id = ? AND lp.punkte > 0 ORDER BY lp.punkte DESC', (charakter_id,)).fetchall(); conn.close()
    return jsonify([dict(row) for row in punkte_liste])

@app.route('/api/charakter/<int:charakter_id>/wishlist')
@login_required
def api_get_wishlist(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: return jsonify({'error': 'Unauthorized'}), 403
    wishlist = conn.execute('SELECT w.item_id, w.prioritaet, i.item_name FROM wishlist w JOIN items i ON w.item_id = i.id WHERE w.charakter_id = ? ORDER BY w.prioritaet ASC', (charakter_id,)).fetchall(); conn.close()
    return jsonify([dict(row) for row in wishlist])

@app.route('/api/items/search')
@login_required
def api_item_search():
    query = request.args.get('q', ''); charakter_klasse = request.args.get('klasse', '')
    conn = get_db_connection()
    
    universelle_typen = ['Reittier', 'Schmuckstück', 'Ring', 'Hals', 'Umhang', 'Einhand', 'Zweihand', 'Schildhand', 'Questgegenstand', 'Rezept', 'Sonstiges']
    
    allowed_types = universelle_typen[:]
    
    if charakter_klasse:
        for r_typ, klassen in ITEM_CLASS_MAP.items():
            if charakter_klasse in klassen: allowed_types.append(r_typ)
    else: 
        allowed_types.extend(ITEM_CLASS_MAP.keys())

    placeholders = ','.join('?' for _ in allowed_types)
    params = ['%'+query+'%'] + allowed_types
    
    items = conn.execute(f"SELECT * FROM items WHERE item_name LIKE ? AND ruestungstyp IN ({placeholders}) LIMIT 10", params).fetchall(); conn.close()
    return jsonify([dict(row) for row in items])

@app.route('/api/charakter/<int:charakter_id>/wishlist/add', methods=['POST'])
@login_required
def api_wishlist_add(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: return jsonify({'error': 'Unauthorized'}), 403
    item_id = request.json['item_id']
    count = conn.execute('SELECT count(item_id) as c FROM wishlist WHERE charakter_id = ?', (charakter_id,)).fetchone()['c']
    if count >= WISHLIST_SLOTS: return jsonify({'success': False, 'error': f'Wishlist ist voll (max. {WISHLIST_SLOTS} Items).'})
    prios = conn.execute('SELECT prioritaet FROM wishlist WHERE charakter_id = ?', (charakter_id,)).fetchall(); prio_zahlen = {p['prioritaet'] for p in prios}
    naechste_prio = 1
    while naechste_prio in prio_zahlen: naechste_prio += 1
    conn.execute('INSERT OR IGNORE INTO wishlist (charakter_id, item_id, prioritaet) VALUES (?, ?, ?)', (charakter_id, item_id, naechste_prio)); conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/charakter/<int:charakter_id>/wishlist/remove', methods=['POST'])
@login_required
def api_wishlist_remove(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: return jsonify({'error': 'Unauthorized'}), 403
    item_id = request.json['item_id']
    conn.execute('DELETE FROM wishlist WHERE charakter_id = ? AND item_id = ?', (charakter_id, item_id)); conn.commit()
    wishlist = conn.execute('SELECT * FROM wishlist WHERE charakter_id = ? ORDER BY prioritaet ASC', (charakter_id,)).fetchall()
    for i, item in enumerate(wishlist): conn.execute('UPDATE wishlist SET prioritaet = ? WHERE charakter_id = ? AND item_id = ?', (i + 1, charakter_id, item['item_id']))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/charakter/<int:charakter_id>/wishlist/move', methods=['POST'])
@login_required
def api_wishlist_move(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: return jsonify({'error': 'Unauthorized'}), 403
    item_id = request.json['item_id']; direction = request.json['direction']
    current_item = conn.execute('SELECT * FROM wishlist WHERE charakter_id = ? AND item_id = ?', (charakter_id, item_id)).fetchone()
    if not current_item: return jsonify({'success': False})
    current_prio = current_item['prioritaet']
    if direction == 'up' and current_prio > 1: swap_prio = current_prio - 1
    elif direction == 'down': swap_prio = current_prio + 1
    else: return jsonify({'success': False})
    swap_item = conn.execute('SELECT * FROM wishlist WHERE charakter_id = ? AND prioritaet = ?', (charakter_id, swap_prio)).fetchone()
    if swap_item:
        conn.execute('UPDATE wishlist SET prioritaet = ? WHERE charakter_id = ? AND item_id = ?', (swap_prio, charakter_id, current_item['item_id']))
        conn.execute('UPDATE wishlist SET prioritaet = ? WHERE charakter_id = ? AND item_id = ?', (current_prio, charakter_id, swap_item['item_id']))
        conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/raid/<int:raid_id>/wishlist-helper/<int:charakter_id>')
@login_required
def api_wishlist_helper(raid_id, charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT id FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: return jsonify({'error': 'Unauthorized'}), 403
    raid = conn.execute('SELECT raid_instanz FROM raids WHERE id = ?', (raid_id,)).fetchone()
    wishlist_items = conn.execute('SELECT w.item_id, w.prioritaet, i.item_name FROM wishlist w JOIN items i ON w.item_id = i.id WHERE w.charakter_id = ? AND i.raid_instanz = ? ORDER BY w.prioritaet', (charakter_id, raid['raid_instanz'])).fetchall()
    konkurrenten_reservierungen = conn.execute('SELECT r.item_id, a.spieler_id FROM reservierungen r JOIN anmeldungen a ON r.anmeldung_id = a.id WHERE a.raid_id = ? AND a.spieler_id != ?', (raid_id, charakter_id)).fetchall()
    konkurrenz_map = {}
    for res in konkurrenten_reservierungen:
        if res['item_id'] not in konkurrenz_map: konkurrenz_map[res['item_id']] = []
        konkurrenz_map[res['item_id']].append(res['spieler_id'])
    result_data = []
    for item in wishlist_items:
        item_id = item['item_id']
        deine_punkte_row = conn.execute('SELECT punkte FROM loot_punkte WHERE spieler_id = ? AND item_id = ?', (charakter_id, item_id)).fetchone()
        deine_punkte = deine_punkte_row['punkte'] if deine_punkte_row else 0
        konkurrenz_anzahl = len(konkurrenz_map.get(item_id, [])); max_konkurrenz_punkte = None
        if konkurrenz_anzahl > 0:
            konkurrenten_ids = konkurrenz_map[item_id]; placeholders = ','.join('?' for _ in konkurrenten_ids)
            punkte_row = conn.execute(f'SELECT MAX(punkte) as max_p FROM loot_punkte WHERE spieler_id IN ({placeholders}) AND item_id = ?', konkurrenten_ids + [item_id]).fetchone()
            max_konkurrenz_punkte = punkte_row['max_p'] if punkte_row and punkte_row['max_p'] is not None else 0
        result_data.append({'item_id': item_id, 'prioritaet': item['prioritaet'], 'item_name': item['item_name'], 'deine_punkte': deine_punkte, 'konkurrenz_punkte': max_konkurrenz_punkte, 'konkurrenz_anzahl': konkurrenz_anzahl})
    conn.close()
    return jsonify(result_data)

# === PERSÖNLICHE CHARAKTERVERWALTUNG ===
@app.route('/meine-charaktere')
@login_required
def meine_charaktere():
    conn = get_db_connection(); charaktere = conn.execute('SELECT * FROM charaktere WHERE user_id = ? ORDER BY charakter_name', (current_user.id,)).fetchall(); conn.close()
    return render_template('meine_charaktere.html', charaktere=charaktere)

@app.route('/charakter/neu', methods=['GET', 'POST'])
@login_required
def charakter_erstellen():
    if request.method == 'POST':
        charakter_name = request.form['charakter_name']; klasse = request.form['klasse']; rollen_liste = request.form.getlist('rollen'); rollen_string = ",".join(rollen_liste); conn = get_db_connection()
        if conn.execute('SELECT id FROM charaktere WHERE charakter_name = ?', (charakter_name,)).fetchone():
            flash('Ein Charakter mit diesem Namen existiert bereits.', 'error'); return redirect(url_for('charakter_erstellen'))
        conn.execute('INSERT INTO charaktere (user_id, charakter_name, klasse, rollen) VALUES (?, ?, ?, ?)', (current_user.id, charakter_name, klasse, rollen_string)); conn.commit(); conn.close()
        return redirect(url_for('meine_charaktere'))
    return render_template('spieler_hinzufuegen.html')

@app.route('/charakter/<int:charakter_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def charakter_bearbeiten(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT * FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if not charakter: flash('Charakter nicht gefunden oder keine Berechtigung.', 'error'); return redirect(url_for('meine_charaktere'))
    if request.method == 'POST':
        charakter_name = request.form['charakter_name']; klasse = request.form['klasse']; rollen_liste = request.form.getlist('rollen'); rollen_string = ",".join(rollen_liste)
        conn.execute('UPDATE charaktere SET charakter_name = ?, klasse = ?, rollen = ? WHERE id = ?', (charakter_name, klasse, rollen_string, charakter_id)); conn.commit(); conn.close()
        return redirect(url_for('meine_charaktere'))
    conn.close(); return render_template('spieler_bearbeiten.html', spieler=charakter)

@app.route('/charakter/<int:charakter_id>/loeschen', methods=['POST'])
@login_required
def charakter_loeschen(charakter_id):
    conn = get_db_connection(); charakter = conn.execute('SELECT * FROM charaktere WHERE id = ? AND user_id = ?', (charakter_id, current_user.id)).fetchone()
    if charakter: conn.execute('DELETE FROM charaktere WHERE id = ?', (charakter_id,)); conn.commit()
    conn.close(); return redirect(url_for('meine_charaktere'))

# === ADMIN-BEREICH ===
@app.route('/admin/logs')
@login_required
@admin_required
def log_liste():
    conn = get_db_connection(); logs = conn.execute('SELECT * FROM logs ORDER BY zeitstempel DESC').fetchall(); conn.close()
    return render_template('logs.html', log_liste=logs)

@app.route('/admin/archiv')
@login_required
@admin_required
def archiv_liste():
    conn = get_db_connection(); raids = conn.execute("SELECT * FROM raids WHERE status = 'Abgeschlossen' ORDER BY raid_datum DESC, raid_zeit DESC").fetchall(); conn.close()
    return render_template('archiv_liste.html', raid_liste=raids)

@app.route('/admin/archiv/raid/<int:raid_id>')
@login_required
@admin_required
def archiv_detail(raid_id):
    conn = get_db_connection(); raid = conn.execute("SELECT * FROM raids WHERE id = ?", (raid_id,)).fetchone()
    teilnehmerliste = conn.execute('SELECT c.charakter_name, a.rolle_angemeldet FROM anmeldungen a JOIN charaktere c ON a.spieler_id = c.id WHERE a.raid_id = ? ORDER BY c.charakter_name', (raid_id,)).fetchall()
    loot_logs = conn.execute("SELECT zeitstempel, details FROM logs WHERE raid_id = ? AND aktion = 'Item Vergeben' ORDER BY zeitstempel ASC", (raid_id,)).fetchall(); conn.close()
    return render_template('archiv_detail.html', raid=raid, teilnehmerliste=teilnehmerliste, loot_logs=loot_logs)

@app.route('/admin/charaktere')
@login_required
@admin_required
def admin_charakter_liste():
    conn = get_db_connection(); charaktere = conn.execute('SELECT c.*, u.username FROM charaktere c JOIN users u ON c.user_id = u.id ORDER BY c.charakter_name').fetchall(); conn.close()
    return render_template('admin_charakter_liste.html', spieler_liste=charaktere)

@app.route('/admin/charaktere/<int:charakter_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def admin_charakter_loeschen(charakter_id):
    conn = get_db_connection(); spieler = conn.execute('SELECT charakter_name FROM charaktere WHERE id = ?', (charakter_id,)).fetchone()
    if spieler: conn.execute('DELETE FROM charaktere WHERE id = ?', (charakter_id,)); conn.commit(); log_action("Admin: Charakter Gelöscht", f"Charakter '{spieler['charakter_name']}' wurde vom Admin gelöscht.")
    conn.close(); return redirect(url_for('admin_charakter_liste'))

@app.route('/admin/users')
@login_required
@admin_required
def admin_user_liste():
    conn = get_db_connection(); users = conn.execute('SELECT * FROM users ORDER BY username').fetchall(); conn.close()
    return render_template('admin_user_liste.html', user_liste=users)

@app.route('/admin/user/<int:user_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def admin_user_loeschen(user_id):
    if user_id == current_user.id: flash("Du kannst deinen eigenen Account nicht löschen.", "error"); return redirect(url_for('admin_user_liste'))
    conn = get_db_connection(); user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()
    if user: conn.execute('DELETE FROM users WHERE id = ?', (user_id,)); conn.commit(); log_action("Admin: Benutzer Gelöscht", f"Benutzer '{user['username']}' wurde gelöscht."); flash(f"Benutzer '{user['username']}' wurde gelöscht.", "success")
    conn.close(); return redirect(url_for('admin_user_liste'))

@app.route('/admin/user/<int:user_id>/promote', methods=['POST'])
@login_required
@admin_required
def admin_user_promote(user_id):
    conn = get_db_connection(); conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,)); conn.commit(); user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone(); conn.close()
    log_action("Admin: Benutzer befördert", f"Benutzer '{user['username']}' wurde zum Admin ernannt."); flash(f"'{user['username']}' ist jetzt ein Admin.", "success"); return redirect(url_for('admin_user_liste'))

@app.route('/admin/user/<int:user_id>/demote', methods=['POST'])
@login_required
@admin_required
def admin_user_demote(user_id):
    if user_id == 1: flash("Der Haupt-Admin kann nicht degradiert werden.", "error"); return redirect(url_for('admin_user_liste'))
    conn = get_db_connection(); conn.execute("UPDATE users SET role = 'member' WHERE id = ?", (user_id,)); conn.commit(); user = conn.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone(); conn.close()
    log_action("Admin: Benutzer degradiert", f"Benutzer '{user['username']}' wurde zum Mitglied degradiert."); flash(f"'{user['username']}' ist jetzt ein Mitglied.", "success"); return redirect(url_for('admin_user_liste'))

@app.route('/dashboard')
@login_required
@admin_required
def dashboard():
    conn = get_db_connection(); raids = conn.execute("SELECT * FROM raids WHERE status != 'Abgeschlossen' ORDER BY raid_datum DESC").fetchall(); spieler = conn.execute('SELECT * FROM charaktere ORDER BY charakter_name').fetchall(); items = conn.execute('SELECT * FROM items ORDER BY item_name').fetchall(); conn.close()
    return render_template('dashboard.html', raid_liste=raids, spieler_liste=spieler, item_liste=items)

@app.route('/dashboard/punkte_anpassen', methods=['POST'])
@login_required
@admin_required
def punkte_anpassen():
    spieler_id = request.form['spieler_id']; item_id = request.form['item_id']; punkte = request.form['punkte']; begruendung = request.form['begruendung']; conn = get_db_connection(); eintrag = conn.execute('SELECT * FROM loot_punkte WHERE spieler_id = ? AND item_id = ?', (spieler_id, item_id)).fetchone()
    if eintrag: conn.execute('UPDATE loot_punkte SET punkte = ? WHERE spieler_id = ? AND item_id = ?', (punkte, spieler_id, item_id))
    else: conn.execute('INSERT INTO loot_punkte (spieler_id, item_id, punkte) VALUES (?, ?, ?)', (spieler_id, item_id, punkte))
    conn.commit(); spieler = conn.execute('SELECT charakter_name FROM charaktere WHERE id = ?', (spieler_id,)).fetchone(); item = conn.execute('SELECT item_name FROM items WHERE id = ?', (item_id,)).fetchone(); conn.close()
    log_details = f"Punkte für '{spieler['charakter_name']}' auf Item '{item['item_name']}' manuell auf {punkte} gesetzt. Grund: {begruendung}"; log_action("Punkte Manuell Angepasst", log_details); return redirect(url_for('dashboard'))

@app.route('/dashboard/raid/<int:raid_id>')
@login_required
@admin_required
def raid_dashboard(raid_id):
    conn = get_db_connection(); raid = conn.execute('SELECT * FROM raids WHERE id = ?', (raid_id,)).fetchone(); 
    bosse = conn.execute('SELECT DISTINCT boss_name FROM items WHERE raid_instanz = ? ORDER BY boss_name', (raid['raid_instanz'],)).fetchall()
    item_liste_rows = conn.execute('SELECT * FROM items WHERE raid_instanz = ? ORDER BY item_name', (raid['raid_instanz'],)).fetchall()
    item_liste = [dict(row) for row in item_liste_rows]
    anmeldungen_raw = conn.execute('SELECT a.id as anmeldung_id, c.id as spieler_id, c.charakter_name, a.rolle_angemeldet FROM anmeldungen a JOIN charaktere c ON a.spieler_id = c.id WHERE a.raid_id = ?', (raid_id,)).fetchall(); anmeldungen = []
    for anmeldung in anmeldungen_raw:
        reservierungen = conn.execute('SELECT i.item_name, IFNULL(lp.punkte, 0) as punkte FROM reservierungen r JOIN items i ON r.item_id = i.id LEFT JOIN loot_punkte lp ON r.item_id = lp.item_id AND lp.spieler_id = ? WHERE r.anmeldung_id = ?', (anmeldung['spieler_id'], anmeldung['anmeldung_id'])).fetchall()
        anmeldungen.append({'anmeldung_id': anmeldung['anmeldung_id'], 'spieler_id': anmeldung['spieler_id'], 'charakter_name': anmeldung['charakter_name'], 'rolle_angemeldet': anmeldung['rolle_angemeldet'], 'reservierungen': reservierungen})
    conn.close(); return render_template('raid_dashboard.html', raid=raid, anmeldungen=anmeldungen, item_liste=item_liste, bosse=bosse)

@app.route('/dashboard/raid/<int:raid_id>/vergeben', methods=['POST'])
@login_required
@admin_required
def item_vergeben(raid_id):
    item_id = request.form.get('item_id'); spieler_id = request.form.get('spieler_id')
    if not spieler_id: return redirect(url_for('raid_dashboard', raid_id=raid_id))
    conn = get_db_connection(); item = conn.execute('SELECT item_name FROM items WHERE id = ?', (item_id,)).fetchone(); spieler = conn.execute('SELECT charakter_name FROM charaktere WHERE id = ?', (spieler_id,)).fetchone()
    punkte_alt = conn.execute('SELECT punkte FROM loot_punkte WHERE item_id = ? AND spieler_id = ?', (item_id, spieler_id)).fetchone(); punkte_alt_wert = punkte_alt['punkte'] if punkte_alt else 0
    conn.execute('UPDATE loot_punkte SET punkte = 0 WHERE item_id = ? AND spieler_id = ?', (item_id, spieler_id)); conn.commit(); conn.close()
    log_action("Item Vergeben", f"Item '{item['item_name']}' an '{spieler['charakter_name']}' vergeben. Punkte von {punkte_alt_wert} auf 0 gesetzt.", raid_id=raid_id); return redirect(url_for('raid_dashboard', raid_id=raid_id))

@app.route('/raids/neu', methods=['GET', 'POST'])
@login_required
@admin_required
def raid_erstellen():
    conn = get_db_connection(); instanzen = conn.execute('SELECT DISTINCT raid_instanz FROM items ORDER BY raid_instanz').fetchall()
    if request.method == 'POST':
        raid_instanz = request.form['raid_instanz']; raid_titel = request.form['raid_titel']; raid_datum = request.form['raid_datum']; raid_zeit = request.form['raid_zeit']
        conn.execute('INSERT INTO raids (raid_instanz, raid_titel, raid_datum, raid_zeit) VALUES (?, ?, ?, ?)', (raid_instanz, raid_titel, raid_datum, raid_zeit)); conn.commit(); conn.close()
        log_action("Raid Erstellt", f"Raid '{raid_instanz} - {raid_titel}' am {raid_datum} wurde erstellt."); return redirect(url_for('raid_liste'))
    conn.close(); return render_template('raid_erstellen.html', instanzen=instanzen)

@app.route('/raid/<int:raid_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
@admin_required
def raid_bearbeiten(raid_id):
    conn = get_db_connection(); raid = conn.execute('SELECT * FROM raids WHERE id = ?', (raid_id,)).fetchone(); instanzen = conn.execute('SELECT DISTINCT raid_instanz FROM items ORDER BY raid_instanz').fetchall()
    if request.method == 'POST':
        raid_instanz = request.form['raid_instanz']; raid_titel = request.form['raid_titel']; raid_datum = request.form['raid_datum']; raid_zeit = request.form['raid_zeit']
        conn.execute('UPDATE raids SET raid_instanz = ?, raid_titel = ?, raid_datum = ?, raid_zeit = ? WHERE id = ?', (raid_instanz, raid_titel, raid_datum, raid_zeit, raid_id)); conn.commit(); conn.close()
        log_action("Raid Bearbeitet", f"Raid '{raid_instanz} - {raid_titel}' wurde bearbeitet."); return redirect(url_for('raid_liste'))
    conn.close(); return render_template('raid_bearbeiten.html', raid=raid, instanzen=instanzen)
    
@app.route('/raid/<int:raid_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def raid_loeschen(raid_id):
    conn = get_db_connection(); raid = conn.execute('SELECT * FROM raids WHERE id = ?', (raid_id,)).fetchone()
    if raid['punkte_vergeben']:
        anmeldungen = conn.execute('SELECT id, spieler_id FROM anmeldungen WHERE raid_id = ?', (raid_id,)).fetchall()
        for anmeldung in anmeldungen:
            reservierungen = conn.execute('SELECT item_id FROM reservierungen WHERE anmeldung_id = ?', (anmeldung['id'],)).fetchall(); item_ids = [r['item_id'] for r in reservierungen]; item_counts = Counter(item_ids)
            for item_id, anzahl in item_counts.items(): conn.execute('UPDATE loot_punkte SET punkte = punkte - ? WHERE spieler_id = ? AND item_id = ? AND punkte >= ?', (anzahl, anmeldung['spieler_id'], item_id, anzahl))
    conn.execute('DELETE FROM raids WHERE id = ?', (raid_id,)); conn.commit(); conn.close()
    log_action("Raid Gelöscht", f"Raid '{raid['raid_instanz']}' vom {raid['raid_datum']} wurde gelöscht."); return redirect(url_for('raid_liste'))

@app.route('/raid/<int:raid_id>/toggle_lock', methods=['POST'])
@login_required
@admin_required
def raid_toggle_lock(raid_id):
    conn = get_db_connection(); raid = conn.execute('SELECT * FROM raids WHERE id = ?', (raid_id,)).fetchone()
    if raid['status'] == 'Offen':
        neuer_status = 'Gestartet'; aktion = "Raid gesperrt/gestartet"; details = f"Anmeldungen für '{raid['raid_instanz']}' geschlossen."
        if not raid['punkte_vergeben']:
            anmeldungen = conn.execute('SELECT id, spieler_id FROM anmeldungen WHERE raid_id = ?', (raid_id,)).fetchall(); punkte_vergeben_count = 0
            for anmeldung in anmeldungen:
                reservierungen = conn.execute('SELECT item_id FROM reservierungen WHERE anmeldung_id = ?', (anmeldung['id'],)).fetchall(); item_ids = [r['item_id'] for r in reservierungen]; item_counts = Counter(item_ids)
                for item_id, anzahl in item_counts.items():
                    punkt_eintrag = conn.execute('SELECT * FROM loot_punkte WHERE spieler_id = ? AND item_id = ?', (anmeldung['spieler_id'], item_id)).fetchone()
                    if punkt_eintrag: conn.execute('UPDATE loot_punkte SET punkte = punkte + ? WHERE spieler_id = ? AND item_id = ?', (anzahl, anmeldung['spieler_id'], item_id))
                    else: conn.execute('INSERT INTO loot_punkte (spieler_id, item_id, punkte) VALUES (?, ?, ?)', (anmeldung['spieler_id'], item_id, anzahl))
                    punkte_vergeben_count += anzahl
            conn.execute("UPDATE raids SET punkte_vergeben = 1 WHERE id = ?", (raid_id,)); details += f" {punkte_vergeben_count} Punkte vergeben."
    elif raid['status'] == 'Gestartet':
        neuer_status = 'Offen'; aktion = "Raid geöffnet"; details = f"Anmeldungen für '{raid['raid_instanz']}' geöffnet."
    else: neuer_status = raid['status']
    conn.execute("UPDATE raids SET status = ? WHERE id = ?", (neuer_status, raid_id)); conn.commit(); conn.close(); log_action(aktion, details); return redirect(url_for('raid_liste'))

@app.route('/raid/<int:raid_id>/abschliessen', methods=['POST'])
@login_required
@admin_required
def raid_abschliessen(raid_id):
    conn = get_db_connection(); conn.execute("UPDATE raids SET status = 'Abgeschlossen' WHERE id = ?", (raid_id,)); conn.commit(); raid = conn.execute('SELECT raid_instanz, raid_titel FROM raids WHERE id = ?', (raid_id,)).fetchone(); conn.close()
    log_action("Raid Abgeschlossen", f"Raid '{raid['raid_instanz']} - {raid['raid_titel']}' wurde abgeschlossen."); return redirect(url_for('raid_liste'))

@app.route('/anmeldung/<int:anmeldung_id>/entfernen', methods=['POST'])
@login_required
@admin_required
def anmeldung_entfernen(anmeldung_id):
    conn = get_db_connection(); anmeldung = conn.execute('SELECT * FROM anmeldungen WHERE id = ?', (anmeldung_id,)).fetchone()
    if not anmeldung: return "Anmeldung nicht gefunden", 404
    raid = conn.execute('SELECT * FROM raids WHERE id = ?', (anmeldung['raid_id'],)).fetchone()
    if raid['punkte_vergeben']:
        reservierungen = conn.execute('SELECT item_id FROM reservierungen WHERE anmeldung_id = ?', (anmeldung_id,)).fetchall(); item_ids = [r['item_id'] for r in reservierungen]; item_counts = Counter(item_ids)
        for item_id, anzahl in item_counts.items(): conn.execute('UPDATE loot_punkte SET punkte = punkte - ? WHERE spieler_id = ? AND item_id = ? AND punkte >= ?', (anzahl, anmeldung['spieler_id'], item_id, anzahl))
    conn.execute('DELETE FROM anmeldungen WHERE id = ?', (anmeldung_id,)); conn.commit(); spieler = conn.execute('SELECT charakter_name FROM charaktere WHERE id = ?', (anmeldung['spieler_id'],)).fetchone(); conn.close()
    log_action("Teilnehmer Entfernt", f"Spieler '{spieler['charakter_name']}' wurde aus Raid '{raid['raid_instanz']}' entfernt.")
    return redirect(url_for('raid_dashboard', raid_id=anmeldung['raid_id']))

@app.route('/admin/items')
@login_required
@admin_required
def item_liste():
    conn = get_db_connection(); items = conn.execute('SELECT * FROM items ORDER BY raid_instanz, boss_name, item_name').fetchall(); conn.close()
    return render_template('item_liste.html', item_liste=items)

@app.route('/admin/items/neu', methods=['GET', 'POST'])
@login_required
@admin_required
def item_hinzufuegen():
    conn = get_db_connection(); raid_instanzen = conn.execute('SELECT DISTINCT raid_instanz FROM items ORDER BY raid_instanz').fetchall(); boss_namen = conn.execute('SELECT DISTINCT boss_name FROM items ORDER BY boss_name').fetchall()
    if request.method == 'POST':
        item_name = request.form['item_name']; boss_name = request.form['boss_name']; raid_instanz = request.form['raid_instanz']; ruestungstyp = request.form['ruestungstyp']
        conn.execute('INSERT INTO items (item_name, boss_name, raid_instanz, ruestungstyp) VALUES (?, ?, ?, ?)', (item_name, boss_name, raid_instanz, ruestungstyp)); conn.commit(); conn.close()
        return redirect(url_for('item_liste'))
    conn.close(); return render_template('item_hinzufuegen.html', raid_instanzen=raid_instanzen, boss_namen=boss_namen)

@app.route('/admin/item/<int:item_id>/bearbeiten', methods=['GET', 'POST'])
@login_required
@admin_required
def item_bearbeiten(item_id):
    conn = get_db_connection(); item = conn.execute('SELECT * FROM items WHERE id = ?', (item_id,)).fetchone(); raid_instanzen = conn.execute('SELECT DISTINCT raid_instanz FROM items ORDER BY raid_instanz').fetchall(); boss_namen = conn.execute('SELECT DISTINCT boss_name FROM items ORDER BY boss_name').fetchall()
    if request.method == 'POST':
        item_name = request.form['item_name']; boss_name = request.form['boss_name']; raid_instanz = request.form['raid_instanz']; ruestungstyp = request.form['ruestungstyp']
        conn.execute('UPDATE items SET item_name = ?, boss_name = ?, raid_instanz = ?, ruestungstyp = ? WHERE id = ?', (item_name, boss_name, raid_instanz, ruestungstyp, item_id)); conn.commit(); conn.close()
        log_action("Item Bearbeitet", f"Item '{item_name}' wurde aktualisiert.")
        return redirect(url_for('item_liste'))
    conn.close(); return render_template('item_bearbeiten.html', item=item, raid_instanzen=raid_instanzen, boss_namen=boss_namen)

@app.route('/admin/item/<int:item_id>/loeschen', methods=['POST'])
@login_required
@admin_required
def item_loeschen(item_id):
    conn = get_db_connection(); item = conn.execute('SELECT item_name FROM items WHERE id = ?', (item_id,)).fetchone(); conn.execute('DELETE FROM items WHERE id = ?', (item_id,)); conn.commit(); conn.close()
    log_action("Item Gelöscht", f"Item '{item['item_name']}' wurde entfernt.")
    return redirect(url_for('item_liste'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)