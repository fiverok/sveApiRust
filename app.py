from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
import json
import os
import hashlib
import secrets
import logging
from logging.handlers import RotatingFileHandler
import time
import threading
import traceback

app = Flask(__name__, static_folder='static', static_url_path='/static')

# ========== НАСТРОЙКИ ==========
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
SESSION_EXPIRY_HOURS = int(os.environ.get('SESSION_EXPIRY_HOURS', 8))

DB_PATH = '/data/computers.db'
API_VERSION = "2.0.0"
SERVER_VERSION = "2025.1.0"

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
log_format = '%(asctime)s - %(levelname)s - %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

sysinfo_logger = logging.getLogger('sysinfo')
sysinfo_logger.setLevel(logging.INFO)
sysinfo_handler = RotatingFileHandler('/data/sysinfo.log', maxBytes=10485760, backupCount=10)
sysinfo_handler.setFormatter(logging.Formatter(log_format, date_format))
sysinfo_logger.addHandler(sysinfo_handler)

heartbeat_logger = logging.getLogger('heartbeat')
heartbeat_logger.setLevel(logging.WARNING)
heartbeat_handler = RotatingFileHandler('/data/heartbeat.log', maxBytes=10485760, backupCount=5)
heartbeat_handler.setFormatter(logging.Formatter(log_format, date_format))
heartbeat_logger.addHandler(heartbeat_handler)

error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_handler = logging.StreamHandler()
error_handler.setFormatter(logging.Formatter(log_format, date_format))
error_logger.addHandler(error_handler)

try:
    error_file_handler = RotatingFileHandler('/data/errors.log', maxBytes=10485760, backupCount=5)
    error_file_handler.setFormatter(logging.Formatter(log_format, date_format))
    error_logger.addHandler(error_file_handler)
except:
    pass

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app.logger.disabled = True

# ========== НАСТРОЙКИ БД ==========
DB_LOCK = threading.RLock()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-20000")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    with DB_LOCK:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            if params:
                processed_params = []
                for p in params:
                    if isinstance(p, (list, tuple, dict)):
                        processed_params.append(json.dumps(p, ensure_ascii=False))
                    else:
                        processed_params.append(p)
                cursor.execute(query, processed_params)
            else:
                cursor.execute(query)
            
            conn.commit()
            
            if fetch_one:
                result = cursor.fetchone()
                return dict(result) if result else None
            elif fetch_all:
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            else:
                return cursor.rowcount
        except sqlite3.OperationalError as e:
            if conn:
                conn.rollback()
            error_logger.error(f"Database error: {e}")
            raise
        except Exception as e:
            if conn:
                conn.rollback()
            error_logger.error(f"Query error: {e}")
            raise
        finally:
            if conn:
                conn.close()

def init_db():
    with DB_LOCK:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS computers (
                id TEXT,
                uuid TEXT PRIMARY KEY,
                hostname TEXT NOT NULL,
                username TEXT DEFAULT 'Unknown',
                os TEXT DEFAULT 'Unknown',
                cpu TEXT DEFAULT 'Unknown',
                memory TEXT DEFAULT '0',
                version TEXT DEFAULT '',
                ip TEXT DEFAULT '',
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_update_timestamp INTEGER DEFAULT 0,
                last_online TIMESTAMP,
                last_online_timestamp INTEGER DEFAULT 0,
                last_online_ip TEXT DEFAULT '',
                modified_at INTEGER DEFAULT 0,
                conns TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                target TEXT,
                details TEXT,
                ip TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hostname ON computers(hostname)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON computers(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_last_online ON computers(last_online_timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_computers_id ON computers(id)')
        
        cursor.execute('SELECT COUNT(*) as count FROM users')
        if cursor.fetchone()['count'] == 0:
            admin_password = hash_password('admin')
            cursor.execute('''
                INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, 'admin')
            ''', ('admin', admin_password))
            error_logger.info("Created default admin user: admin / admin")
        
        conn.commit()
        conn.close()
        error_logger.info("Database initialized successfully")

def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + ':' + hash_obj.hex()

def verify_password(stored_password, provided_password):
    try:
        salt, stored_hash = stored_password.split(':')
        hash_obj = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt.encode(), 100000)
        return hash_obj.hex() == stored_hash
    except:
        return False

def add_audit_log(user_id, action, target, details, ip):
    try:
        execute_query('''
            INSERT INTO audit_log (user_id, action, target, details, ip)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, target, details, ip))
    except Exception as e:
        error_logger.error(f"Failed to add audit log: {e}")

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            login_time = session.get('login_time')
            if login_time:
                login_time = datetime.fromisoformat(login_time)
                if datetime.now() - login_time > timedelta(hours=SESSION_EXPIRY_HOURS):
                    session.clear()
                    return redirect(url_for('login_page'))
            return f(*args, **kwargs)
        
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect(url_for('login_page'))
    return decorated_function

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') == 'admin':
            return f(*args, **kwargs)
        
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Admin rights required'}), 403
        return redirect(url_for('login_page'))
    return decorated_function

def get_computer_by_uuid(uuid):
    if not uuid:
        return None
    return execute_query('SELECT * FROM computers WHERE uuid = ?', (uuid,), fetch_one=True)

def get_computer_by_id(computer_id):
    if not computer_id:
        return None
    return execute_query('SELECT * FROM computers WHERE id = ?', (computer_id,), fetch_one=True)

def delete_computer_by_uuid(uuid):
    return execute_query('DELETE FROM computers WHERE uuid = ?', (uuid,)) > 0

def update_sysinfo(data, client_ip):
    uuid = data.get('uuid')
    computer_id = data.get('id')
    
    if not uuid:
        return None, 'NO_UUID'
    
    now = datetime.now()
    now_iso = now.isoformat()
    now_timestamp = int(now.timestamp())
    
    conns = data.get('conns')
    if isinstance(conns, (list, tuple)):
        conns = json.dumps(conns)
    
    existing = get_computer_by_uuid(uuid)
    
    if existing:
        execute_query('''
            UPDATE computers SET
                id = COALESCE(?, id),
                hostname = ?,
                username = ?,
                os = ?,
                cpu = ?,
                memory = ?,
                version = ?,
                ip = ?,
                last_update = ?,
                last_update_timestamp = ?,
                modified_at = COALESCE(?, modified_at),
                conns = COALESCE(?, conns)
            WHERE uuid = ?
        ''', (
            computer_id if computer_id else existing.get('id'),
            data.get('hostname', existing.get('hostname', 'Unknown')),
            data.get('username', existing.get('username', 'Unknown')),
            data.get('os', existing.get('os', 'Unknown')),
            data.get('cpu', existing.get('cpu', 'Unknown')),
            data.get('memory', existing.get('memory', '0')),
            data.get('version', existing.get('version', '')),
            client_ip,
            now_iso,
            now_timestamp,
            data.get('modified_at', now_timestamp),
            conns,
            uuid
        ))
        result = 'UPDATED'
    else:
        execute_query('''
            INSERT INTO computers (
                id, uuid, hostname, username, os, cpu, memory, version,
                ip, last_update, last_update_timestamp, modified_at, conns, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            computer_id if computer_id else '',
            uuid,
            data.get('hostname', 'Unknown'),
            data.get('username', 'Unknown'),
            data.get('os', 'Unknown'),
            data.get('cpu', 'Unknown'),
            data.get('memory', '0'),
            data.get('version', ''),
            client_ip,
            now_iso,
            now_timestamp,
            data.get('modified_at', now_timestamp),
            conns,
            now_iso
        ))
        result = 'CREATED'
    
    return get_computer_by_uuid(uuid), result

def update_heartbeat(uuid, client_ip, conns=None, modified_at=None, computer_id=None):
    now = datetime.now()
    now_iso = now.isoformat()
    now_timestamp = int(now.timestamp())
    
    if isinstance(conns, (list, tuple)):
        conns = json.dumps(conns)
    
    try:
        execute_query('''
            UPDATE computers SET
                last_online = ?,
                last_online_timestamp = ?,
                last_online_ip = ?,
                ip = ?,
                modified_at = COALESCE(?, modified_at),
                conns = COALESCE(?, conns),
                id = CASE WHEN id IS NULL OR id = '' THEN ? ELSE id END
            WHERE uuid = ?
        ''', (
            now_iso,
            now_timestamp,
            client_ip,
            client_ip,
            modified_at,
            conns,
            computer_id if computer_id else None,
            uuid
        ))
        return True, now_timestamp
    except Exception as e:
        error_logger.error(f"Error updating heartbeat: {e}")
        return False, None

def get_all_computers():
    return execute_query('SELECT * FROM computers ORDER BY last_update_timestamp DESC', fetch_all=True)

def get_stats():
    total = execute_query('SELECT COUNT(*) as count FROM computers', fetch_one=True)
    if not total:
        return {'total_computers': 0, 'online_computers': 0, 'offline_computers': 0}
    
    now_timestamp = int(datetime.now().timestamp())
    online = execute_query('SELECT COUNT(*) as count FROM computers WHERE last_online_timestamp > ?', 
                         (now_timestamp - 35,), fetch_one=True)
    
    return {
        'total_computers': total['count'],
        'online_computers': online['count'] if online else 0,
        'offline_computers': total['count'] - (online['count'] if online else 0)
    }

def get_all_users():
    return execute_query('SELECT id, username, role, email, created_at, last_login FROM users', fetch_all=True)

def get_user_by_username(username):
    return execute_query('SELECT * FROM users WHERE username = ?', (username,), fetch_one=True)

def create_user(username, password, role='user', email=None):
    existing = get_user_by_username(username)
    if existing:
        return False, 'Username already exists'
    
    password_hash = hash_password(password)
    execute_query('''
        INSERT INTO users (username, password_hash, role, email)
        VALUES (?, ?, ?, ?)
    ''', (username, password_hash, role, email))
    return True, 'User created'

def delete_user(user_id):
    admin_count = execute_query('SELECT COUNT(*) as count FROM users WHERE role = "admin"', fetch_one=True)
    user = execute_query('SELECT role FROM users WHERE id = ?', (user_id,), fetch_one=True)
    
    if user and user['role'] == 'admin' and admin_count and admin_count['count'] <= 1:
        return False, 'Cannot delete the last admin user'
    
    execute_query('DELETE FROM users WHERE id = ?', (user_id,))
    return True, 'User deleted'

# ========== ВЕБ-МАРШРУТЫ ==========
@app.route('/login')
def login_page():
    return send_from_directory('static', 'login.html')

@app.route('/')
@require_auth
def index():
    return send_from_directory('static', 'index.html')

@app.route('/admin')
@require_admin
def admin_page():
    return send_from_directory('static', 'admin.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ========== API АУТЕНТИФИКАЦИИ ==========
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        user = get_user_by_username(data.get('username'))
        
        if user and verify_password(user['password_hash'], data.get('password')):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['login_time'] = datetime.now().isoformat()
            
            execute_query('UPDATE users SET last_login = ? WHERE id = ?', 
                         (datetime.now().isoformat(), user['id']))
            
            add_audit_log(user['id'], 'LOGIN', data.get('username'), 'Successful', request.remote_addr)
            return jsonify({'status': 'success', 'role': user['role']}), 200
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        error_logger.error(f"Login error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/me', methods=['GET'])
@require_auth
def get_current_user():
    return jsonify({
        'id': session.get('user_id'),
        'username': session.get('username'),
        'role': session.get('role')
    })

@app.route('/api/users', methods=['GET'])
@require_admin
def get_users():
    return jsonify(get_all_users())

@app.route('/api/users', methods=['POST'])
@require_admin
def add_user():
    data = request.get_json()
    success, message = create_user(data.get('username'), data.get('password'), 
                                   data.get('role', 'user'), data.get('email'))
    if success:
        add_audit_log(session.get('user_id'), 'CREATE_USER', data.get('username'), message, request.remote_addr)
        return jsonify({'message': message}), 201
    return jsonify({'error': message}), 400

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@require_admin
def remove_user(user_id):
    success, message = delete_user(user_id)
    if success:
        add_audit_log(session.get('user_id'), 'DELETE_USER', str(user_id), message, request.remote_addr)
        return jsonify({'message': message}), 200
    return jsonify({'error': message}), 400

@app.route('/api/computers', methods=['GET'])
@require_auth
def get_computers_api():
    return jsonify(get_all_computers())

@app.route('/api/computers/<string:uuid>', methods=['DELETE'])
@require_admin
def delete_computer(uuid):
    success = delete_computer_by_uuid(uuid)
    if success:
        add_audit_log(session.get('user_id'), 'DELETE_COMPUTER', uuid, 'Computer deleted', request.remote_addr)
        return jsonify({'message': 'Computer deleted'}), 200
    return jsonify({'error': 'Computer not found'}), 404

@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats_api():
    stats = get_stats()
    stats['api_version'] = API_VERSION
    return jsonify(stats)

@app.route('/api/audit', methods=['GET'])
@require_admin
def get_audit_logs():
    limit = request.args.get('limit', 100, type=int)
    logs = execute_query('SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?', (limit,), fetch_all=True)
    return jsonify(logs if logs else [])

# ========== ПУБЛИЧНЫЕ API ==========
@app.route('/api/sysinfo', methods=['POST'])
def register_sysinfo():
    client_ip = request.remote_addr
    raw_data = request.get_data(as_text=True)
    content_length = request.content_length
    
    # Обработка пустого запроса (Content-Length = 0)
    if not raw_data or content_length == 0:
        error_logger.info(f"Sysinfo: Empty request from {client_ip}, returning version info")
        return f"RustDesk Monitor v{SERVER_VERSION}", 200
    
    headers = dict(request.headers)
    
    try:
        if request.is_json:
            data = request.get_json()
        else:
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as e:
                error_logger.error(f"Sysinfo JSON decode error from {client_ip}: {e}")
                error_logger.error(f"Raw data: {raw_data[:500]}")
                return "MISSING_UUID", 400
        
        if not data:
            error_logger.error(f"Sysinfo: No data received from {client_ip}")
            return "MISSING_UUID", 400
        
        if 'uuid' not in data:
            error_logger.error(f"Sysinfo: Missing UUID from {client_ip}")
            error_logger.error(f"Data received: {json.dumps(data, ensure_ascii=False)[:500]}")
            return "MISSING_UUID", 400
        
        computer, result = update_sysinfo(data, client_ip)
        if not computer:
            error_logger.error(f"Sysinfo: Failed to update computer with UUID={data.get('uuid')}")
            return "MISSING_UUID", 400
        
        sysinfo_logger.info(f"SYSINFO | UUID={computer['uuid']} | Hostname={computer['hostname']} | Action={result}")
        return "SYSINFO_UPDATED", 200
        
    except json.JSONDecodeError as e:
        error_logger.error(f"Sysinfo JSON error from {client_ip}: {e}")
        error_logger.error(f"Raw data: {raw_data[:500] if raw_data else 'empty'}")
        return "MISSING_UUID", 400
    except Exception as e:
        error_logger.error(f"Error sysinfo from {client_ip}: {e}")
        error_logger.error(f"Raw data: {raw_data[:500] if raw_data else 'empty'}")
        error_logger.error(traceback.format_exc())
        return "ERROR", 500

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    client_ip = request.remote_addr
    raw_data = request.get_data(as_text=True)
    content_length = request.content_length
    
    # Обработка пустого запроса
    if not raw_data or content_length == 0:
        error_logger.info(f"Heartbeat: Empty request from {client_ip}")
        return jsonify({}), 200
    
    try:
        if request.is_json:
            data = request.get_json()
        else:
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as e:
                error_logger.error(f"Heartbeat JSON error from {client_ip}: {e}")
                return jsonify({}), 400
        
        if not data:
            return jsonify({}), 400
        
        uuid = data.get('uuid')
        computer_id = str(data.get('id')) if data.get('id') else None
        
        existing = None
        if uuid:
            existing = get_computer_by_uuid(uuid)
        if not existing and computer_id:
            existing = get_computer_by_id(computer_id)
        
        if not existing:
            return "", 401
        
        updated, new_timestamp = update_heartbeat(
            existing['uuid'], client_ip, data.get('conns'), data.get('modified_at'), computer_id
        )
        
        if updated:
            return jsonify({'modified_at': new_timestamp}), 200
        return jsonify({}), 500
    except Exception as e:
        error_logger.error(f"Error heartbeat from {client_ip}: {e}")
        error_logger.error(traceback.format_exc())
        return jsonify({}), 500

@app.route('/api/version', methods=['GET'])
def get_version():
    return API_VERSION, 200

@app.route('/api/sysinfo_ver', methods=['POST'])
def sysinfo_ver():
    return SERVER_VERSION, 200

@app.route('/health', methods=['GET'])
def health_check():
    stats = get_stats()
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'computers_count': stats['total_computers']
    })

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    os.makedirs('/data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    init_db()
    
    print("=" * 60)
    print("🚀 RustDesk Monitor Server v5.0")
    print("=" * 60)
    print(f"📁 Database: {DB_PATH}")
    print(f"🌐 Web UI: http://0.0.0.0:21114")
    print(f"🔐 Login: http://0.0.0.0:21114/login (admin/admin)")
    print("=" * 60)
    print("📡 Обработка пустых запросов:")
    print("   - /api/sysinfo (empty) → возвращает версию сервера")
    print("   - /api/heartbeat (empty) → возвращает {}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=21114, debug=False, threaded=True)