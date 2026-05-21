from flask import Flask, send_from_directory, session, redirect, url_for, jsonify
from datetime import datetime
import os
import logging
from logging.handlers import RotatingFileHandler

from modules import (
    init_db, init_auth_routes, init_computers_routes, init_public_routes,
    get_user_by_username, hash_password, execute_query, add_audit_log
)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# ========== НАСТРОЙКИ ==========
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

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

# ========== ВЕБ-МАРШРУТЫ ==========
@app.route('/login')
def login_page():
    return send_from_directory('static', 'login.html')

@app.route('/')
def index():
    from modules.auth import require_auth
    auth_check = require_auth(lambda: None)()
    if isinstance(auth_check, tuple):
        return auth_check
    return send_from_directory('static', 'index.html')

@app.route('/admin')
def admin_page():
    from modules.auth import require_admin
    auth_check = require_admin(lambda: None)()
    if isinstance(auth_check, tuple):
        return auth_check
    return send_from_directory('static', 'admin.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/logout')
def web_logout():
    """Веб-выход из системы"""
    user_id = session.get('user_id')
    username = session.get('username', 'Unknown')
    
    if user_id:
        add_audit_log(user_id, 'LOGOUT', username, 'Web logout', request.remote_addr)
    
    session.clear()
    return redirect(url_for('login_page'))

# ========== ИНИЦИАЛИЗАЦИЯ API МАРШРУТОВ ==========
init_auth_routes(app)
init_computers_routes(app)
init_public_routes(app)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    os.makedirs('/data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Инициализация базы данных
    init_db()
    
    # Проверяем, есть ли admin пользователь
    admin = get_user_by_username('admin')
    if not admin:
        admin_password = hash_password('admin')
        execute_query('''
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, 'admin')
        ''', ('admin', admin_password))
        error_logger.info("Created default admin user: admin / admin")
    
    print("=" * 60)
    print("🚀 RustDesk Monitor Server v5.0 (Modular)")
    print("=" * 60)
    print(f"📁 Database: /data/computers.db")
    print(f"🌐 Web UI: http://0.0.0.0:21114")
    print(f"🔐 Login: http://0.0.0.0:21114/login (admin/admin)")
    print("=" * 60)
    print("📁 Modules structure:")
    print("   - modules/database.py     - работа с БД")
    print("   - modules/auth.py         - аутентификация")
    print("   - modules/api_auth.py     - API аутентификации")
    print("   - modules/api_computers.py - API компьютеров")
    print("   - modules/api_public.py   - публичные API")
    print("=" * 60)
    print("🕐 Session timeout: 2 hours of inactivity")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=21114, debug=False, threaded=True)