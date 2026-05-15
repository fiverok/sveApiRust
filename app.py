from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
import json
import os
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__, static_folder='static', static_url_path='')

# ========== НАСТРОЙКИ ==========
DATA_FILE = '/data/computers.json'
API_VERSION = "1.0.0"
SERVER_VERSION = "2025.1.0"

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
log_format = '%(asctime)s - %(levelname)s - %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

# Логгер для sysinfo
sysinfo_logger = logging.getLogger('sysinfo')
sysinfo_logger.setLevel(logging.INFO)
sysinfo_handler = RotatingFileHandler('/data/sysinfo.log', maxBytes=10485760, backupCount=10)
sysinfo_handler.setFormatter(logging.Formatter(log_format, date_format))
sysinfo_logger.addHandler(sysinfo_handler)

# Логгер для heartbeat
heartbeat_logger = logging.getLogger('heartbeat')
heartbeat_logger.setLevel(logging.INFO)
heartbeat_handler = RotatingFileHandler('/data/heartbeat.log', maxBytes=10485760, backupCount=5)
heartbeat_handler.setFormatter(logging.Formatter(log_format, date_format))
heartbeat_logger.addHandler(heartbeat_handler)

# Логгер для ошибок
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

# Отключаем логи Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app.logger.disabled = True

# ========== РАБОТА С JSON ==========
def load_data():
    """Загружает данные из JSON файла"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        error_logger.error(f"Error loading data: {e}")
        return []

def save_data(data):
    """Сохраняет данные в JSON файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        error_logger.error(f"Error saving data: {e}")
        return False
    return True

def get_computer_by_uuid(uuid):
    """Получает компьютер по UUID"""
    if not uuid:
        return None
    computers = load_data()
    for comp in computers:
        if comp.get('uuid') == uuid:
            return comp
    return None

def get_computer_by_id(computer_id):
    """Получает компьютер по ID (для обратной совместимости)"""
    if not computer_id:
        return None
    computers = load_data()
    for comp in computers:
        if comp.get('id') == computer_id:
            return comp
    return None

def update_computer_with_id(uuid, computer_id):
    """Дополняет информацию о компьютере: добавляет ID по UUID"""
    computers = load_data()
    for comp in computers:
        if comp.get('uuid') == uuid:
            # Если ID еще не установлен или отличается, обновляем
            old_id = comp.get('id')
            if not comp.get('id') or comp.get('id') != computer_id:
                comp['id'] = computer_id
                save_data(computers)
                return True, old_id
            return False, old_id
    return False, None

def update_sysinfo(data, client_ip):
    """
    Обновляет или создает запись с системной информацией
    Критерий уникальности - UUID
    """
    computers = load_data()
    
    uuid = data.get('uuid')
    computer_id = data.get('id')
    
    if not uuid:
        sysinfo_logger.warning(f"SYSINFO | IP={client_ip} | Error=Missing uuid field")
        return None, 'NO_UUID'
    
    # Ищем существующий компьютер по UUID
    existing_index = None
    for i, comp in enumerate(computers):
        if comp.get('uuid') == uuid:
            existing_index = i
            break
    
    now = datetime.now().isoformat()
    current_timestamp = int(datetime.now().timestamp())
    
    new_computer = {
        'uuid': uuid,
        'id': computer_id if computer_id else '',
        'hostname': data.get('hostname', 'Unknown'),
        'username': data.get('username', 'Unknown'),
        'os': data.get('os', 'Unknown'),
        'cpu': data.get('cpu', 'Unknown'),
        'memory': data.get('memory', '0'),
        'version': data.get('version', ''),
        'ip': client_ip,
        'last_update': now,
        'last_update_timestamp': current_timestamp,
        'last_online': None,
        'last_online_timestamp': None,
        'modified_at': data.get('modified_at', current_timestamp)
    }
    
    if existing_index is not None:
        # Сохраняем last_online из существующей записи
        new_computer['last_online'] = computers[existing_index].get('last_online')
        new_computer['last_online_timestamp'] = computers[existing_index].get('last_online_timestamp')
        # Если в новом запросе нет ID, но есть в старом - сохраняем старый
        if not new_computer['id'] and computers[existing_index].get('id'):
            new_computer['id'] = computers[existing_index].get('id')
        computers[existing_index] = new_computer
        save_data(computers)
        return new_computer, 'UPDATED'
    else:
        computers.append(new_computer)
        save_data(computers)
        return new_computer, 'CREATED'

def update_heartbeat(uuid, client_ip, conns=None, modified_at=None, computer_id=None):
    """Обновляет heartbeat по UUID"""
    computers = load_data()
    now = datetime.now()
    now_iso = now.isoformat()
    now_timestamp = int(now.timestamp())
    
    for comp in computers:
        if comp.get('uuid') == uuid:
            comp['last_online'] = now_iso
            comp['last_online_timestamp'] = now_timestamp
            comp['last_online_ip'] = client_ip
            comp['ip'] = client_ip
            if conns:
                comp['conns'] = conns
            if modified_at:
                comp['modified_at'] = modified_at
            # Если в запросе есть ID, но в записи его нет - обновляем
            if computer_id and not comp.get('id'):
                comp['id'] = computer_id
            save_data(computers)
            return True, now_timestamp
    return False, None

# ========== API ЭНДПОИНТЫ ==========

@app.route('/')
def index():
    """Отдает HTML файл веб-интерфейса"""
    try:
        return send_from_directory('static', 'index.html')
    except Exception as e:
        error_logger.error(f"Error serving index.html: {e}")
        return jsonify({
            'name': 'RustDesk Monitor',
            'version': SERVER_VERSION,
            'api_version': API_VERSION,
            'description': 'Система мониторинга оборудования RustDesk',
            'endpoints': {
                'sysinfo': '/api/sysinfo',
                'sysinfo_ver': '/api/sysinfo_ver',
                'heartbeat': '/api/heartbeat',
                'computers': '/api/computers',
                'version': '/api/version'
            }
        })

@app.route('/api/info', methods=['GET'])
def api_info():
    """Возвращает базовую информацию API"""
    return jsonify({
        'name': 'RustDesk Monitor',
        'version': SERVER_VERSION,
        'api_version': API_VERSION,
        'description': 'Система мониторинга оборудования RustDesk',
        'endpoints': {
            'sysinfo': '/api/sysinfo',
            'sysinfo_ver': '/api/sysinfo_ver',
            'heartbeat': '/api/heartbeat',
            'computers': '/api/computers',
            'version': '/api/version'
        }
    })

@app.route('/api/computers', methods=['GET'])
def get_computers():
    """Возвращает список всех компьютеров"""
    computers = load_data()
    return jsonify(computers)

@app.route('/api/sysinfo', methods=['POST'])
def register_sysinfo():
    """
    Принимает системную информацию от клиента RustDesk
    Критерий уникальности - UUID
    """
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
            sysinfo_logger.warning(f"SYSINFO | IP={client_ip} | Error=Empty request")
            return "MISSING_UUID", 400
        
        if 'uuid' not in data or not data['uuid']:
            sysinfo_logger.warning(f"SYSINFO | IP={client_ip} | Error=Missing uuid field")
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
        
    except json.JSONDecodeError as e:
        sysinfo_logger.error(f"SYSINFO | IP={client_ip} | Error=Invalid JSON: {str(e)}")
        return "MISSING_UUID", 400
    except Exception as e:
        sysinfo_logger.error(f"SYSINFO | IP={client_ip} | Error={str(e)}")
        error_logger.error(f"Error sysinfo: {e}")
        return "MISSING_UUID", 500

@app.route('/api/sysinfo_ver', methods=['POST'])
def sysinfo_ver():
    """Возвращает версию сервера при инициализации клиента"""
    client_ip = request.remote_addr
    sysinfo_logger.info(f"SYSINFO_VER | IP={client_ip} | Version={SERVER_VERSION}")
    return SERVER_VERSION, 200

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """
    Поддержание онлайн-статуса
    Если устройство не найдено по UUID, но есть ID - ищем по ID
    Если найдено по ID, но нет UUID - дополняем информацию
    Если не найдено - возвращаем 401
    """
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
            heartbeat_logger.warning(f"HEARTBEAT | IP={client_ip} | Error=Empty request")
            return jsonify({}), 400
        
        uuid = data.get('uuid')
        computer_id = str(data.get('id')) if data.get('id') else None
        conns = data.get('conns')
        modified_at = data.get('modified_at')
        
        # Проверяем, есть ли хоть какой-то идентификатор
        if not uuid and not computer_id:
            heartbeat_logger.warning(f"HEARTBEAT | IP={client_ip} | Error=Missing uuid and id")
            return jsonify({}), 400
        
        # Ищем устройство (сначала по UUID, потом по ID)
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
        
        # Если устройство не найдено - возвращаем 401
        if not existing:
            heartbeat_logger.warning(
                f"HEARTBEAT | UUID={uuid or 'N/A'} | ID={computer_id or 'N/A'} | "
                f"IP={client_ip} | Status=not_registered | HTTP=401"
            )
            return "", 401
        
        # Устройство найдено - обновляем heartbeat
        updated, new_timestamp = update_heartbeat(
            existing['uuid'], client_ip, conns, modified_at, computer_id
        )
        
        # Дополняем информацию: если нашли по ID, но в записи нет UUID - обновляем
        if search_method == 'ID' and not existing.get('uuid') and uuid:
            update_computer_with_id(uuid, computer_id)
            heartbeat_logger.info(
                f"HEARTBEAT | Найден по ID={computer_id}, дополнен UUID={uuid} | "
                f"Hostname={existing.get('hostname', 'Unknown')} | IP={client_ip}"
            )
        # Если нашли по UUID, но в записи нет ID - обновляем
        elif search_method == 'UUID' and not existing.get('id') and computer_id:
            update_computer_with_id(uuid, computer_id)
            heartbeat_logger.info(
                f"HEARTBEAT | Найден по UUID={uuid}, дополнен ID={computer_id} | "
                f"Hostname={existing.get('hostname', 'Unknown')} | IP={client_ip}"
            )
        
        if updated:
            heartbeat_logger.info(
                f"HEARTBEAT | UUID={existing['uuid']} | ID={existing.get('id', 'N/A')} | "
                f"Hostname={existing.get('hostname', 'Unknown')} | IP={client_ip} | Status=online"
            )
            return jsonify({'modified_at': new_timestamp}), 200
        else:
            heartbeat_logger.error(f"HEARTBEAT | UUID={existing['uuid']} | IP={client_ip} | Status=update_failed")
            return jsonify({}), 500
        
    except json.JSONDecodeError as e:
        heartbeat_logger.error(f"HEARTBEAT | IP={client_ip} | Error=Invalid JSON: {str(e)}")
        return jsonify({}), 400
    except Exception as e:
        heartbeat_logger.error(f"HEARTBEAT | IP={client_ip} | Error={str(e)}")
        error_logger.error(f"Error heartbeat: {e}")
        return jsonify({}), 500

@app.route('/api/version', methods=['GET'])
def get_version():
    """Возвращает версию API при старте клиента"""
    return API_VERSION, 200

@app.route('/api/logs/sysinfo', methods=['GET'])
def get_sysinfo_logs():
    """Просмотр логов sysinfo"""
    try:
        lines = request.args.get('lines', 100, type=int)
        
        if os.path.exists('/data/sysinfo.log'):
            with open('/data/sysinfo.log', 'r', encoding='utf-8') as f:
                logs = f.readlines()
                return jsonify({'logs': logs[-lines:]})
        else:
            return jsonify({'logs': [], 'message': 'Sysinfo log file not found'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/heartbeat', methods=['GET'])
def get_heartbeat_logs():
    """Просмотр логов heartbeat"""
    try:
        lines = request.args.get('lines', 100, type=int)
        
        if os.path.exists('/data/heartbeat.log'):
            with open('/data/heartbeat.log', 'r', encoding='utf-8') as f:
                logs = f.readlines()
                return jsonify({'logs': logs[-lines:]})
        else:
            return jsonify({'logs': [], 'message': 'Heartbeat log file not found'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/errors', methods=['GET'])
def get_error_logs():
    """Просмотр логов ошибок"""
    try:
        lines = request.args.get('lines', 100, type=int)
        
        if os.path.exists('/data/errors.log'):
            with open('/data/errors.log', 'r', encoding='utf-8') as f:
                logs = f.readlines()
                return jsonify({'logs': logs[-lines:]})
        else:
            return jsonify({'logs': [], 'message': 'Error log file not found'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Статистика"""
    try:
        computers = load_data()
        online_count = 0
        now_timestamp = int(datetime.now().timestamp())
        
        for comp in computers:
            last_online_ts = comp.get('last_online_timestamp')
            if last_online_ts and (now_timestamp - last_online_ts) < 35:
                online_count += 1
        
        return jsonify({
            'total_computers': len(computers),
            'online_computers': online_count,
            'offline_computers': len(computers) - online_count,
            'api_version': API_VERSION,
            'server_version': SERVER_VERSION
        })
    except Exception as e:
        error_logger.error(f"Error stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервера"""
    try:
        computers = load_data()
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database': 'json',
            'computers_count': len(computers),
            'api_version': API_VERSION,
            'server_version': SERVER_VERSION
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs('/data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    if not os.path.exists(DATA_FILE):
        save_data([])
    
    print("=" * 60)
    print("🚀 RustDesk Monitor Server v4.0 (Smart Heartbeat)")
    print("=" * 60)
    print(f"📁 Data file: {DATA_FILE}")
    print(f"🌐 Web UI: http://0.0.0.0:21114")
    print(f"📡 API endpoints:")
    print(f"   POST /api/sysinfo      - системная информация (UUID обязателен)")
    print(f"   POST /api/heartbeat    - heartbeat (автодополнение ID/UUID)")
    print(f"   GET  /api/computers    - список компьютеров")
    print("=" * 60)
    print("📡 Smart Heartbeat логика:")
    print("   1. Ищем сначала по UUID")
    print("   2. Если не найден - ищем по ID")
    print("   3. Если найден по ID, но нет UUID - дополняем UUID")
    print("   4. Если найден по UUID, но нет ID - дополняем ID")
    print("   5. Если не найден - возвращаем 401")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=21114, debug=False)