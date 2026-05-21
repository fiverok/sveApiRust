import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session, redirect, url_for

from modules.database import execute_query

# Константы
SESSION_TIMEOUT_HOURS = 2  # Время бездействия в часах

def hash_password(password, salt=None):
    """Хеширует пароль с солью"""
    if not salt:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + ':' + hash_obj.hex()

def verify_password(stored_password, provided_password):
    """Проверяет пароль"""
    try:
        salt, stored_hash = stored_password.split(':')
        hash_obj = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt.encode(), 100000)
        return hash_obj.hex() == stored_hash
    except:
        return False

def update_last_activity():
    """Обновляет время последней активности пользователя в сессии"""
    if 'user_id' in session:
        session['last_activity'] = datetime.now().isoformat()

def is_session_expired():
    """Проверяет, не истекла ли сессия по бездействию"""
    if 'last_activity' not in session:
        return True
    
    try:
        last_activity = datetime.fromisoformat(session['last_activity'])
        timeout_delta = timedelta(hours=SESSION_TIMEOUT_HOURS)
        
        if datetime.now() - last_activity > timeout_delta:
            return True
    except:
        return True
    
    return False

def add_audit_log(user_id, action, target, details, ip):
    """Добавляет запись в лог аудита"""
    try:
        execute_query('''
            INSERT INTO audit_log (user_id, action, target, details, ip)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, target, details, ip))
    except Exception as e:
        pass

def require_auth(f):
    """Декоратор для проверки авторизации с проверкой бездействия"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Проверяем наличие сессии
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login_page'))
        
        # Проверяем бездействие
        if is_session_expired():
            # Логируем выход по бездействию
            user_id = session.get('user_id')
            username = session.get('username', 'Unknown')
            add_audit_log(user_id, 'SESSION_TIMEOUT', username, f'Auto logout after {SESSION_TIMEOUT_HOURS} hours of inactivity', request.remote_addr)
            
            # Очищаем сессию
            session.clear()
            
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Session expired due to inactivity'}), 401
            return redirect(url_for('login_page'))
        
        # Обновляем время последней активности
        update_last_activity()
        
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') == 'admin':
            return f(*args, **kwargs)
        
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Admin rights required'}), 403
        return redirect(url_for('login_page'))
    return decorated_function

def get_session_timeout_seconds():
    """Возвращает время таймаута в секундах"""
    return SESSION_TIMEOUT_HOURS * 3600

# ========== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ==========

def get_all_users():
    """Возвращает список всех пользователей"""
    return execute_query('SELECT id, username, role, email, created_at, last_login FROM users', fetch_all=True)

def get_user_by_username(username):
    """Получает пользователя по имени"""
    return execute_query('SELECT * FROM users WHERE username = ?', (username,), fetch_one=True)

def create_user(username, password, role='user', email=None):
    """Создает нового пользователя"""
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
    """Удаляет пользователя"""
    admin_count = execute_query('SELECT COUNT(*) as count FROM users WHERE role = "admin"', fetch_one=True)
    user = execute_query('SELECT role FROM users WHERE id = ?', (user_id,), fetch_one=True)
    
    if user and user['role'] == 'admin' and admin_count and admin_count['count'] <= 1:
        return False, 'Cannot delete the last admin user'
    
    execute_query('DELETE FROM users WHERE id = ?', (user_id,))
    return True, 'User deleted'

def update_user_last_login(user_id):
    """Обновляет время последнего входа пользователя"""
    execute_query('UPDATE users SET last_login = ? WHERE id = ?', 
                 (datetime.now().isoformat(), user_id))