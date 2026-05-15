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
heartbeat_handler = RotatingFileHandler('/data/heartbeat.log', maxBytes=10485760, backupCount=10)
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

def update_computer(computer_id, data):
    """Обновляет или создает запись о компьютере"""
    computers = load_data()
    
    # Ищем существующий компьютер по ID
    existing_index = None
    for i, comp in enumerate(computers):
        if comp.get('id') == computer_id:
            existing_index = i
            break
    
    now = datetime.now().isoformat()
    
    new_computer = {
        'id': computer_id,
        'hostname': data.get('hostname', 'Unknown'),
        'username': data.get('username', 'Unknown'),
        'os': data.get('os', 'Unknown'),
        'cpu': data.get('cpu', 'Unknown'),
        'memory_total': data.get('memory_total', '0'),
        'memory_used': data.get('memory_used', '0'),
        'uuid': data.get('uuid', ''),
        'version': data.get('version', ''),
        'ip': data.get('ip', ''),
        'last_update': now,
        'last_online': None
    }
    
    if existing_index is not None:
        # Сохраняем last_online из существующей записи
        new_computer['last_online'] = computers[existing_index].get('last_online')
        computers[existing_index] = new_computer
        save_data(computers)
        return 'UPDATED'
    else:
        computers.append(new_computer)
        save_data(computers)
        return 'CREATED'

def update_heartbeat(computer_id, ip, ver):
    """Обновляет heartbeat (только если компьютер существует)"""
    computers = load_data()
    
    for comp in computers:
        if comp.get('id') == computer_id:
            comp['last_online'] = datetime.now().isoformat()
            comp['last_online_ip'] = ip
            comp['ver'] = ver
            comp['ip'] = ip
            save_data(computers)
            return True
    return False

def get_computer_by_id(computer_id):
    """Получает компьютер по ID"""
    computers = load_data()
    for comp in computers:
        if comp.get('id') == computer_id:
            return comp
    return None

# ========== API ЭНДПОИНТЫ ==========
@app.route('/')
def index():
    """Отдает HTML файл"""
    return send_from_directory('static', 'index.html')

@app.route('/api/computers', methods=['GET'])
def get_computers():
    """Возвращает список всех компьютеров"""
    computers = load_data()
    return jsonify(computers)

@app.route('/api/sysinfo', methods=['POST'])
def register_sysinfo():
    """
    Принимает системную информацию от клиента RustDesk
    Создает или обновляет запись о компьютере
    """
    start_time = datetime.now()
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
        
        if not data or 'id' not in data:
            sysinfo_logger.warning(f"SYSINFO | IP={client_ip} | Error=Missing id field | Status=bad_request")
            return jsonify({'error': 'Missing id field'}), 400
        
        computer_id = str(data['id'])
        
        # Формируем данные для сохранения
        computer_data = {
            'hostname': data.get('hostname', 'Unknown'),
            'username': data.get('username', 'Unknown'),
            'os': data.get('os', 'Unknown'),
            'cpu': data.get('cpu', 'Unknown'),
            'memory_total': data.get('memory', data.get('memory_total', '0')),
            'memory_used': data.get('memory_used', '0'),
            'uuid': data.get('uuid', ''),
            'version': data.get('version', ''),
            'ip': client_ip
        }
        
        result = update_computer(computer_id, computer_data)
        
        # Детальное логирование sysinfo
        sysinfo_logger.info(
            f"SYSINFO | ID={computer_id} | Hostname={computer_data['hostname']} | "
            f"User={computer_data['username']} | OS={computer_data['os']} | "
            f"CPU={computer_data['cpu']} | Memory={computer_data['memory_total']} | "
            f"Version={computer_data['version']} | UUID={computer_data['uuid']} | "
            f"IP={client_ip} | Action={result} | Time={datetime.now().isoformat()}"
        )
        
        return "SYSINFO_UPDATED", 200
        
    except json.JSONDecodeError as e:
        sysinfo_logger.error(f"SYSINFO | IP={client_ip} | Error=Invalid JSON: {str(e)}")
        return jsonify({'error': 'Invalid JSON'}), 400
    except Exception as e:
        sysinfo_logger.error(f"SYSINFO | IP={client_ip} | Error={str(e)}")
        error_logger.error(f"Error sysinfo: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """
    Обновляет heartbeat только для существующих устройств.
    Если устройство НЕ найдено - возвращает 401 (Unauthorized).
    Клиент интерпретирует 401 как сигнал для повторной отправки sysinfo.
    """
    start_time = datetime.now()
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
        
        if not data or 'id' not in data:
            heartbeat_logger.warning(f"HEARTBEAT | IP={client_ip} | Error=Missing id field | Status=bad_request")
            return jsonify({}), 400
        
        computer_id = str(data['id'])
        ver = data.get('ver', 0)
        
        # Проверяем, существует ли устройство
        existing = get_computer_by_id(computer_id)
        
        if not existing:
            # Устройство не найдено - возвращаем 401
            heartbeat_logger.warning(
                f"HEARTBEAT | ID={computer_id} | IP={client_ip} | Ver={ver} | "
                f"Status=not_registered | HTTP=401 | Action=client_will_send_sysinfo"
            )
            return "", 401
        
        # Устройство найдено - обновляем heartbeat
        update_heartbeat(computer_id, client_ip, ver)
        
        hostname = existing.get('hostname', 'Unknown')
        username = existing.get('username', 'Unknown')
        
        heartbeat_logger.info(
            f"HEARTBEAT | ID={computer_id} | Hostname={hostname} | User={username} | "
            f"IP={client_ip} | Ver={ver} | Status=registered | HTTP=200"
        )
        
        return jsonify({}), 200
        
    except json.JSONDecodeError as e:
        heartbeat_logger.error(f"HEARTBEAT | IP={client_ip} | Error=Invalid JSON: {str(e)}")
        return jsonify({}), 400
    except Exception as e:
        heartbeat_logger.error(f"HEARTBEAT | IP={client_ip} | Error={str(e)}")
        error_logger.error(f"Error heartbeat: {e}")
        return jsonify({}), 500

@app.route('/api/version', methods=['GET'])
def get_version():
    """Возвращает версию API"""
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
        now = datetime.now()
        
        for comp in computers:
            last_online = comp.get('last_online')
            if last_online:
                try:
                    last_time = datetime.fromisoformat(last_online)
                    if (now - last_time).total_seconds() < 30:
                        online_count += 1
                except:
                    pass
        
        return jsonify({
            'total_computers': len(computers),
            'online_computers': online_count,
            'offline_computers': len(computers) - online_count,
            'api_version': API_VERSION
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
            'api_version': API_VERSION
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    # Создаем необходимые директории
    os.makedirs('/data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Инициализация файла данных
    if not os.path.exists(DATA_FILE):
        save_data([])
    
    print("=" * 60)
    print("🚀 RustDesk Monitor Server v1.0 (JSON storage)")
    print("=" * 60)
    print(f"📁 Data file: {DATA_FILE}")
    print(f"🌐 Web UI: http://0.0.0.0:21114")
    print(f"📡 API endpoints:")
    print(f"   POST /api/sysinfo    - регистрация/обновление")
    print(f"   POST /api/heartbeat  - обновление статуса")
    print(f"   GET  /api/computers  - список компьютеров")
    print(f"   GET  /api/stats      - статистика")
    print(f"   GET  /api/logs/sysinfo   - логи sysinfo")
    print(f"   GET  /api/logs/heartbeat - логи heartbeat")
    print(f"   GET  /api/logs/errors    - логи ошибок")
    print("=" * 60)
    print("📡 Heartbeat logic:")
    print("   - 200 OK + {} → устройство зарегистрировано")
    print("   - 401 Unauthorized → устройство НЕ зарегистрировано (клиент отправит sysinfo)")
    print("=" * 60)
    print("📊 Логи сохраняются в /data/")
    print("   - sysinfo.log   - все регистрации и обновления")
    print("   - heartbeat.log - все heartbeat запросы")
    print("   - errors.log    - ошибки")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=21114, debug=False)