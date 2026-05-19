from flask import request, jsonify, session
from datetime import datetime
from modules.auth import (
    verify_password, add_audit_log, get_user_by_username, update_user_last_login
)

def init_auth_routes(app):
    """Инициализация маршрутов аутентификации"""
    
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
                
                update_user_last_login(user['id'])
                add_audit_log(user['id'], 'LOGIN', data.get('username'), 'Successful', request.remote_addr)
                return jsonify({'status': 'success', 'role': user['role']}), 200
            return jsonify({'error': 'Invalid credentials'}), 401
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/users/me', methods=['GET'])
    def get_current_user():
        return jsonify({
            'id': session.get('user_id'),
            'username': session.get('username'),
            'role': session.get('role')
        })
    
    @app.route('/api/users', methods=['GET'])
    def get_users():
        from modules.auth import get_all_users, require_admin
        auth_check = require_admin(lambda: None)()
        if isinstance(auth_check, tuple):
            return auth_check
        return jsonify(get_all_users())
    
    @app.route('/api/users', methods=['POST'])
    def add_user():
        from modules.auth import create_user, require_admin, add_audit_log
        auth_check = require_admin(lambda: None)()
        if isinstance(auth_check, tuple):
            return auth_check
        
        data = request.get_json()
        success, message = create_user(data.get('username'), data.get('password'), 
                                       data.get('role', 'user'), data.get('email'))
        if success:
            add_audit_log(session.get('user_id'), 'CREATE_USER', data.get('username'), message, request.remote_addr)
            return jsonify({'message': message}), 201
        return jsonify({'error': message}), 400
    
    @app.route('/api/users/<int:user_id>', methods=['DELETE'])
    def remove_user(user_id):
        from modules.auth import delete_user, require_admin, add_audit_log
        auth_check = require_admin(lambda: None)()
        if isinstance(auth_check, tuple):
            return auth_check
        
        success, message = delete_user(user_id)
        if success:
            add_audit_log(session.get('user_id'), 'DELETE_USER', str(user_id), message, request.remote_addr)
            return jsonify({'message': message}), 200
        return jsonify({'error': message}), 400