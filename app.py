from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
import sqlite3
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager

app = Flask(__name__, static_folder='static', static_url_path='')

# ========== НАСТРОЙКИ ==========
DB_PATH = '/data/computers.db'
API_VERSION = "1.0.0"
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
heartbeat_logger.setLevel(logging.INFO)
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

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========

@contextmanager
def get_db():
    """Контекстный менеджер для работы с БД"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        error_logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """Инициализация базы данных"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Создаем таблицу computers
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
        
        # Создаем индексы для ускорения поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hostname ON computers(hostname)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON computers(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_last_online ON computers(last_online_timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ip ON computers(ip)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_id ON computers(id)')
        
        error_logger.info("Database initialized successfully")

def get_computer_by_uuid(uuid):
    """Получает компьютер по UUID"""
    if not uuid:
        return None
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM computers WHERE uuid = ?', (uuid,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        error_logger.error(f"Error getting computer by UUID: {e}")
        return None

def get_computer_by_id(computer_id):
    """Получает компьютер по ID"""
    if not computer_id:
        return None
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM computers WHERE id = ?', (computer_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        error_logger.error(f"Error getting computer by ID: {e}")
        return None

def update_computer_with_id(uuid, computer_id):
    """Дополняет информацию о компьютере: добавляет ID по UUID"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE computers SET id = ? WHERE uuid = ? AND (id IS NULL OR id = "")', 
                          (computer_id, uuid))
            return cursor.rowcount > 0
    except Exception as e:
        error_logger.error(f"Error updating computer with ID: {e}")
        return False

def update_sysinfo(data, client_ip):
    """
    Обновляет или создает запись с системной информацией
    Критерий уникальности - UUID
    """
    uuid = data.get('uuid')
    computer_id = data.get('id')
    
    if not uuid:
        sysinfo_logger.warning(f"SYSINFO | IP={client_ip} | Error=Missing uuid field")
        return None, 'NO_UUID'
    
    now = datetime.now()
    now_iso = now.isoformat()
    now_timestamp = int(now.timestamp())
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем существует ли запись
            existing = get_computer_by_uuid(uuid)
            
            if existing:
                # Обновляем существующую запись
                cursor.execute('''
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
                        modified_at = COALESCE(?, modified_at)
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
                    uuid
                ))
                result = 'UPDATED'
            else:
                # Создаем новую запись
                cursor.execute('''
                    INSERT INTO computers (
                        id, uuid, hostname, username, os, cpu, memory, version,
                        ip, last_update, last_update_timestamp, modified_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    now_iso
                ))
                result = 'CREATED'
            
            # Получаем созданную/обновленную запись
            cursor.execute('SELECT * FROM computers WHERE uuid = ?', (uuid,))
            row = cursor.fetchone()
            return dict(row) if row else None, result
            
    except Exception as e:
        error_logger.error(f"Error updating sysinfo: {e}")
        return None, 'ERROR'

def update_heartbeat(uuid, client_ip, conns=None, modified_at=None, computer_id=None):
    """Обновляет heartbeat по UUID"""
    now = datetime.now()
    now_iso = now.isoformat()
    now_timestamp = int(now.timestamp())
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Обновляем heartbeat
            cursor.execute('''
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
                json.dumps(conns) if conns else None,
                computer_id if computer_id else None,
                uuid
            ))
            
            return cursor.rowcount > 0, now_timestamp
            
    except Exception as e:
        error_logger.error(f"Error updating heartbeat: {e}")
        return False, None

def get_all_computers():
    """Возвращает список всех компьютеров"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM computers ORDER BY last_update_timestamp DESC')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        error_logger.error(f"Error getting all computers: {e}")
        return []

def get_stats():
    """Возвращает статистику"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as total FROM computers')
            total = cursor.fetchone()['total']
            
            now_timestamp = int(datetime.now().timestamp())
            cursor.execute('SELECT COUNT(*) as online FROM computers WHERE last_online_timestamp > ?', 
                         (now_timestamp - 35,))
            online = cursor.fetchone()['online']
            
            return {
                'total_computers': total,
                'online_computers': online,
                'offline_computers': total - online
            }
    except Exception as e:
        error_logger.error(f"Error getting stats: {e}")
        return {'total_computers': 0, 'online_computers': 0, 'offline_computers': 0}

# ========== API ЭНДПОИНТЫ ==========

@app.route('/')
def index():
    """Отдает HTML файл веб-интерфейса"""
    try:
        return send_from_directory('static', 'index.html')
    except Exception as e:
        return jsonify({
            'name': 'RustDesk Monitor',
            'version': SERVER_VERSION,
            'api_version': API_VERSION,
            'description': 'Система мониторинга оборудования RustDesk',
            'database': 'sqlite'
        })

@app.route('/api/info', methods=['GET'])
def api_info():
    """Возвращает базовую информацию API"""
    return jsonify({
        'name': 'RustDesk Monitor',
        'version': SERVER_VERSION,
        'api_version': API_VERSION,
        'description': 'Система мониторинга оборудования RustDesk',
        'database': 'sqlite'
    })

@app.route('/api/computers', methods=['GET'])
def get_computers():
    """Возвращает список всех компьютеров"""
    computers = get_all_computers()
    return jsonify(computers)

@app.route('/api/sysinfo', methods=['POST'])
def register_sysinfo():
    """Принимает системную информацию от клиента RustDesk"""
    client_ip = request.remote_addr
    
    try:
        data = request.get_json()
        if not data:
            raw_data = request.get_data(as_text=True)
            if raw_data:
                try:
                    data = json.loads(raw_data)
                except:
                    pass
        
        if not data:
            return "MISSING_UUID", 400
        
        if 'uuid' not in data or not data['uuid']:
            sysinfo_logger.warning(f"SYSINFO | IP={client_ip} | Error=Missing uuid")
            return "MISSING_UUID", 400
        
        computer, result = update_sysinfo(data, client_ip)
        
        if not computer:
            return "MISSING_UUID", 400
        
        sysinfo_logger.info(
            f"SYSINFO | UUID={computer['uuid']} | ID={computer.get('id', 'N/A')} | "
            f"Hostname={computer['hostname']} | User={computer['username']} | "
            f"OS={computer['os']} | CPU={computer['cpu']} | "
            f"Memory={computer['memory']} | Version={computer['version']} | "
            f"IP={client_ip} | Action={result}"
        )
        
        return "SYSINFO_UPDATED", 200
        
    except Exception as e:
        error_logger.error(f"Error sysinfo: {e}")
        return "MISSING_UUID", 500

@app.route('/api/sysinfo_ver', methods=['POST'])
def sysinfo_ver():
    """Возвращает версию сервера"""
    client_ip = request.remote_addr
    sysinfo_logger.info(f"SYSINFO_VER | IP={client_ip} | Version={SERVER_VERSION}")
    return SERVER_VERSION, 200

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """Поддержание онлайн-статуса"""
    client_ip = request.remote_addr
    
    try:
        data = request.get_json()
        if not data:
            raw_data = request.get_data(as_text=True)
            if raw_data:
                try:
                    data = json.loads(raw_data)
                except:
                    pass
        
        if not data:
            return jsonify({}), 400
        
        uuid = data.get('uuid')
        computer_id = str(data.get('id')) if data.get('id') else None
        conns = data.get('conns')
        modified_at = data.get('modified_at')
        
        if not uuid and not computer_id:
            heartbeat_logger.warning(f"HEARTBEAT | IP={client_ip} | Error=No identifiers")
            return jsonify({}), 400
        
        # Ищем устройство
        existing = None
        search_method = None
        
        if uuid:
            existing = get_computer_by_uuid(uuid)
            if existing:
                search_method = 'UUID'
        
        if not existing and computer_id:
            existing = get_computer_by_id(computer_id)
            if existing:
                search_method = 'ID'
        
        if not existing:
            heartbeat_logger.warning(
                f"HEARTBEAT | UUID={uuid or 'N/A'} | ID={computer_id or 'N/A'} | "
                f"IP={client_ip} | Status=not_registered"
            )
            return "", 401
        
        # Обновляем heartbeat
        updated, new_timestamp = update_heartbeat(
            existing['uuid'], client_ip, conns, modified_at, computer_id
        )
        
        # Дополняем информацию при необходимости
        if search_method == 'ID' and not existing.get('uuid') and uuid:
            update_computer_with_id(uuid, computer_id)
            heartbeat_logger.info(
                f"HEARTBEAT | Дополнен UUID={uuid} для ID={computer_id}"
            )
        elif search_method == 'UUID' and not existing.get('id') and computer_id:
            update_computer_with_id(uuid, computer_id)
            heartbeat_logger.info(
                f"HEARTBEAT | Дополнен ID={computer_id} для UUID={uuid}"
            )
        
        if updated:
            heartbeat_logger.info(
                f"HEARTBEAT | UUID={existing['uuid']} | ID={existing.get('id', 'N/A')} | "
                f"Hostname={existing.get('hostname', 'Unknown')} | IP={client_ip}"
            )
            return jsonify({'modified_at': new_timestamp}), 200
        else:
            return jsonify({}), 500
        
    except Exception as e:
        error_logger.error(f"Error heartbeat: {e}")
        return jsonify({}), 500

@app.route('/api/version', methods=['GET'])
def get_version():
    return API_VERSION, 200

@app.route('/api/stats', methods=['GET'])
def get_stats_api():
    stats = get_stats()
    stats['api_version'] = API_VERSION
    stats['server_version'] = SERVER_VERSION
    stats['database'] = 'sqlite'
    return jsonify(stats)

@app.route('/health', methods=['GET'])
def health_check():
    try:
        stats = get_stats()
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'sqlite',
            'computers_count': stats['total_computers'],
            'api_version': API_VERSION,
            'server_version': SERVER_VERSION
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/api/logs/sysinfo', methods=['GET'])
def get_sysinfo_logs():
    try:
        lines = request.args.get('lines', 100, type=int)
        if os.path.exists('/data/sysinfo.log'):
            with open('/data/sysinfo.log', 'r', encoding='utf-8') as f:
                logs = f.readlines()
                return jsonify({'logs': logs[-lines:]})
        return jsonify({'logs': [], 'message': 'Log file not found'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs('/data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    init_db()
    
    print("=" * 60)
    print("🚀 RustDesk Monitor Server v5.0 (SQLite)")
    print("=" * 60)
    print(f"📁 Database: {DB_PATH}")
    print(f"🌐 Web UI: http://0.0.0.0:21114")
    print(f"📡 API endpoints:")
    print(f"   POST /api/sysinfo      - регистрация (UUID обязателен)")
    print(f"   POST /api/heartbeat    - heartbeat (автодополнение)")
    print(f"   GET  /api/computers    - список устройств")
    print(f"   GET  /api/stats        - статистика")
    print("=" * 60)
    print("💾 Хранение: SQLite (более надежно и производительно)")
    print("📊 Логи: /data/sysinfo.log, /data/heartbeat.log")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=21114, debug=False)