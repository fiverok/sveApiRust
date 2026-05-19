import sqlite3
import json
import threading
import time
from datetime import datetime

DB_PATH = '/data/computers.db'
DB_LOCK = threading.RLock()

def get_db_connection():
    """Создает соединение с базой данных"""
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-20000")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    """Безопасное выполнение запроса с блокировкой"""
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
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

def init_db():
    """Инициализация базы данных"""
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
        
        conn.commit()
        conn.close()

# ========== РАБОТА С КОМПЬЮТЕРАМИ ==========

def get_computer_by_uuid(uuid):
    """Получает компьютер по UUID"""
    if not uuid:
        return None
    return execute_query('SELECT * FROM computers WHERE uuid = ?', (uuid,), fetch_one=True)

def get_computer_by_id(computer_id):
    """Получает компьютер по ID"""
    if not computer_id:
        return None
    return execute_query('SELECT * FROM computers WHERE id = ?', (computer_id,), fetch_one=True)

def delete_computer_by_uuid(uuid):
    """Удаляет компьютер по UUID"""
    return execute_query('DELETE FROM computers WHERE uuid = ?', (uuid,)) > 0

def update_sysinfo(data, client_ip):
    """Обновляет или создает запись с системной информацией"""
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
    """Обновляет heartbeat по UUID"""
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
        return False, None

def get_all_computers():
    """Возвращает список всех компьютеров"""
    return execute_query('SELECT * FROM computers ORDER BY last_update_timestamp DESC', fetch_all=True)

def get_stats():
    """Возвращает статистику"""
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