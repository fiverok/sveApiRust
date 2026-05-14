from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
import json
import os
import sys
import logging

app = Flask(__name__, static_folder='static', static_url_path='')
DATA_FILE = '/data/computers.json'
API_VERSION = "1.2.3"

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ (ТОЛЬКО ОШИБКИ) ==========

# Отключаем все логи Flask/Werkzeug
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Отключаем логи приложения
app.logger.disabled = True

# Настройка логов только для ошибок
error_handler = logging.StreamHandler()
error_handler.setLevel(logging.ERROR)
error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_logger.addHandler(error_handler)

# Проверка наличия файла для записи ошибок
try:
    error_file_handler = logging.FileHandler('/data/errors.log')
    error_file_handler.setLevel(logging.ERROR)
    error_logger.addHandler(error_file_handler)
except:
    pass

# Подавляем вывод предупреждений
import warnings
warnings.filterwarnings("ignore")

# ========== КОНЕЦ НАСТРОЙКИ ЛОГИРОВАНИЯ ==========

def load_data():
    """Загружает данные из JSON файла"""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        error_logger.error(f"Ошибка загрузки данных: {e}")
        return []

def save_data(data):
    """Сохраняет данные в JSON файл"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        error_logger.error(f"Ошибка сохранения данных: {e}")

@app.route('/')
def index():
    """Отдает HTML файл"""
    try:
        return send_from_directory('static', 'index.html')
    except Exception as e:
        error_logger.error(f"Ошибка отдачи index.html: {e}")
        return "Ошибка загрузки страницы", 500

@app.route('/api/computers', methods=['GET'])
def get_computers():
    """Возвращает список всех компьютеров"""
    try:
        computers = load_data()
        return jsonify(computers)
    except Exception as e:
        error_logger.error(f"Ошибка GET /api/computers: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sysinfo', methods=['POST'])
def register_sysinfo():
    """
    Принимает системную информацию от клиента RustDesk
    - Если ID не найден → создаётся новая запись
    - Если ID найден → обновляется существующая запись
    Ответ: SYSINFO_UPDATED (всегда)
    """
    try:
        # Получаем данные
        data = request.get_json()
        
        if not data:
            raw_data = request.get_data(as_text=True)
            if raw_data:
                try:
                    data = json.loads(raw_data)
                except:
                    pass
        
        if not data or 'id' not in data:
            return jsonify({'error': 'Missing id field'}), 400
        
        computers = load_data()
        computer_id = str(data['id'])
        
        # Ищем существующий компьютер
        found = False
        for comp in computers:
            if str(comp.get('id')) == computer_id:
                comp.update({
                    'hostname': data.get('hostname', comp.get('hostname', 'Unknown')),
                    'username': data.get('username', comp.get('username', 'Unknown')),
                    'os': data.get('os', comp.get('os', 'Unknown')),
                    'cpu': data.get('cpu', comp.get('cpu', 'Unknown')),
                    'memory_total': str(data.get('memory', comp.get('memory_total', '0'))),
                    'memory_used': str(data.get('memory_used', comp.get('memory_used', '0'))),
                    'uuid': data.get('uuid', comp.get('uuid', '')),
                    'version': data.get('version', comp.get('version', '')),
                    'ip': request.remote_addr,
                    'last_update': datetime.now().isoformat()
                })
                found = True
                break
        
        if not found:
            # Создаем новую запись (регистрация)
            computers.append({
                'id': computer_id,
                'hostname': data.get('hostname', 'Unknown'),
                'username': data.get('username', 'Unknown'),
                'os': data.get('os', 'Unknown'),
                'cpu': data.get('cpu', 'Unknown'),
                'memory_total': str(data.get('memory', '0')),
                'memory_used': str(data.get('memory_used', '0')),
                'uuid': data.get('uuid', ''),
                'version': data.get('version', ''),
                'ip': request.remote_addr,
                'first_seen': datetime.now().isoformat(),
                'last_update': datetime.now().isoformat(),
                'last_online': None
            })
        
        # Сохраняем данные
        save_data(computers)
        return "SYSINFO_UPDATED", 200
        
    except json.JSONDecodeError as e:
        error_logger.error(f"JSON ошибка в sysinfo: {e}")
        return jsonify({'error': 'Invalid JSON'}), 400
    except Exception as e:
        error_logger.error(f"Ошибка sysinfo: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """
    Обновляет статус онлайн ТОЛЬКО для существующих устройств
    Если ID не найден - возвращает {} без обновления LastOnlineTime
    Клиент сам интерпретирует ответ и отправит sysinfo при необходимости
    
    Ответ: {} (пустой JSON) - всегда
    Но LastOnlineTime обновляется ТОЛЬКО если ID найден
    """
    try:
        # Получаем данные
        data = request.get_json()
        
        if not data:
            raw_data = request.get_data(as_text=True)
            if raw_data:
                try:
                    data = json.loads(raw_data)
                except:
                    pass
        
        if not data or 'id' not in data:
            return jsonify({}), 400
        
        computer_id = str(data['id'])
        computers = load_data()
        now = datetime.now()
        
        # Ищем существующий компьютер
        found = False
        for comp in computers:
            if str(comp.get('id')) == computer_id:
                found = True
                # Обновляем LastOnlineTime ТОЛЬКО если устройство найдено
                comp['last_online'] = now.isoformat()
                comp['last_online_ip'] = request.remote_addr
                comp['ver'] = data.get('ver', 0)
                comp['ip'] = request.remote_addr
                save_data(computers)
                break
        
        # Если устройство не найдено - НЕ обновляем LastOnlineTime
        # Клиент получит {} и поймет, что нужно отправить sysinfo
        if not found:
            # Логируем для отладки (опционально)
            with open('/data/unknown_heartbeat.log', 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().isoformat()}] Unknown heartbeat: ID={computer_id}, IP={request.remote_addr} - sysinfo will be sent by client\n")
        
        # Всегда возвращаем пустой JSON
        return jsonify({}), 200
        
    except json.JSONDecodeError as e:
        error_logger.error(f"JSON ошибка в heartbeat: {e}")
        return jsonify({}), 400
    except Exception as e:
        error_logger.error(f"Ошибка heartbeat: {e}")
        return jsonify({}), 500

@app.route('/api/version', methods=['GET'])
def get_version():
    """
    Возвращает версию API
    Ответ: 1.2.3
    """
    return API_VERSION, 200

@app.route('/api/logs/errors', methods=['GET'])
def get_error_logs():
    """Просмотр логов ошибок через API"""
    try:
        lines = request.args.get('lines', 50, type=int)
        
        if os.path.exists('/data/errors.log'):
            with open('/data/errors.log', 'r', encoding='utf-8') as f:
                logs = f.readlines()
                return jsonify({'logs': logs[-lines:]})
        else:
            return jsonify({'logs': [], 'message': 'No error logs found'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Простая статистика"""
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
        error_logger.error(f"Ошибка stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервера"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'api_version': API_VERSION
    })

if __name__ == '__main__':
    # Создаем необходимые директории
    os.makedirs('/data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Инициализация файла данных
    if not os.path.exists(DATA_FILE):
        save_data([])
    
    # Создаем простой HTML файл если его нет
    if not os.path.exists('static/index.html'):
        try:
            with open('static/index.html', 'w', encoding='utf-8') as f:
                f.write('''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Светогорский ЦБК - Мониторинг</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #004D43; }
        .container { max-width: 1400px; margin: auto; background: white; padding: 20px; border-radius: 10px; }
        h1 { color: #004D43; border-bottom: 3px solid #FFC700; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #004D43; color: white; }
        tr:hover { background: #f5f5f5; }
        .search { width: 100%; padding: 10px; margin: 20px 0; font-size: 16px; border: 2px solid #ddd; border-radius: 5px; }
        .online { color: #4CAF50; font-weight: bold; }
        .offline { color: #f44336; font-weight: bold; }
        .computer-id { cursor: pointer; color: #004D43; text-decoration: underline; }
        .stats { background: #e3f2fd; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🏭 НПАО «Светогорский ЦБК»</h1>
        <p>Система мониторинга оборудования и удалённого доступа</p>
        <div class="stats" id="stats"></div>
        <input type="text" id="search" class="search" placeholder="🔍 Поиск по имени, пользователю или ID...">
        <table id="table">
            <thead><tr><th>#</th><th>Имя ПК</th><th>ID</th><th>Пользователь</th><th>IP</th><th>Статус</th><th>Обновлен</th></tr></thead>
            <tbody id="tbody"><tr><td colspan="7">Загрузка...</tr</tbody>
        </table>
    </div>
    <script>
        async function load() {
            try {
                const resp = await fetch('/api/computers');
                const data = await resp.json();
                const search = document.getElementById('search').value.toLowerCase();
                const filtered = data.filter(c => 
                    (c.hostname || '').toLowerCase().includes(search) ||
                    (c.username || '').toLowerCase().includes(search) ||
                    (c.id || '').toLowerCase().includes(search)
                );
                const now = new Date();
                document.getElementById('stats').innerHTML = `📊 Версия API: ${await fetch('/api/version').then(r=>r.text())} | Всего: ${data.length} | Онлайн: ${data.filter(c => c.last_online && (now - new Date(c.last_online)) < 30000).length} | Найдено: ${filtered.length}`;
                document.getElementById('tbody').innerHTML = filtered.map((c, i) => {
                    const isOnline = c.last_online && (now - new Date(c.last_online)) < 30000;
                    return `<tr>
                        <td>${i+1}</td>
                        <td><strong>${c.hostname || 'Unknown'}</strong></td>
                        <td><span class="computer-id" onclick="connect('${c.id}')">${c.id}</span></td>
                        <td>${c.username || 'Unknown'}</td>
                        <td>${c.ip || 'N/A'}</td>
                        <td class="${isOnline ? 'online' : 'offline'}">${isOnline ? '🟢 Онлайн' : '🔴 Оффлайн'}</td>
                        <td>${c.last_online ? new Date(c.last_online).toLocaleString() : 'Никогда'}</td>
                    </table>`;
                }).join('');
            } catch(e) { console.error(e); }
        }
        function connect(id) { window.location.href = `rustdesk://connection/new/${id}`; }
        document.getElementById('search').oninput = () => load();
        load();
        setInterval(load, 15000);
    </script>
</body>
</html>''')
        except:
            pass
    
    # Запуск сервера
    print("=" * 60)
    print("🚀 RustDesk Monitor Server v2.0")
    print("=" * 60)
    print(f"📁 Data file: {DATA_FILE}")
    print(f"🌐 Web UI: http://0.0.0.0:21114")
    print(f"📡 API endpoints:")
    print(f"   POST /api/sysinfo    - регистрация/обновление -> SYSINFO_UPDATED")
    print(f"   POST /api/heartbeat  - обновление статуса -> {{}}")
    print(f"   GET  /api/version    - версия API -> {API_VERSION}")
    print(f"   GET  /api/computers  - список компьютеров")
    print("=" * 60)
    print("ℹ️ Логика работы:")
    print("   - Клиент всегда отправляет sysinfo при первом запуске")
    print("   - Heartbeat обновляет LastOnlineTime ТОЛЬКО если ID найден")
    print("   - Если ID не найден, возвращается {} без обновления")
    print("   - Клиент понимает, что нужно отправить sysinfo повторно")
    print("=" * 60)
    
    # Запуск с отключенным debug
    app.run(host='0.0.0.0', port=21114, debug=False, threaded=True)
