import hashlib
import secrets
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session, redirect, url_for

from modules.database import execute_query, get_db_connection

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

def add_audit_log(user_id, action, target, details, ip):
    """Добавляет запись в лог аудита"""
    try:
        execute_query('''
            INSERT INTO audit_log (user_id, action, target, details, ip)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, action, target, details, ip))
    except Exception as e:
        # Логирование ошибки происходит в вызывающем коде
        pass

def require_auth(f):
    """Декоратор для проверки авторизации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            login_time = session.get('login_time')
            if login_time:
                login_time = datetime.fromisoformat(login_time)
                if datetime.now() - login_time > timedelta(hours=8):
                    session.clear()
                    return redirect(url_for('login_page'))
            return f(*args, **kwargs)
        
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect(url_for('login_page'))
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


def update_user_last_login(user_id):
    """Обновляет время последнего входа пользователя"""
    from modules.database import execute_query
    execute_query('UPDATE users SET last_login = ? WHERE id = ?', 
                 (datetime.now().isoformat(), user_id))