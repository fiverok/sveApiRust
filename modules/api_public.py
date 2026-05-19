from flask import request, jsonify
from datetime import datetime
import json
import logging

from modules.database import (
    get_computer_by_uuid, get_computer_by_id,
    update_sysinfo, update_heartbeat, get_stats
)

# Настройка логгеров
sysinfo_logger = logging.getLogger('sysinfo')
heartbeat_logger = logging.getLogger('heartbeat')
error_logger = logging.getLogger('error_logger')

SERVER_VERSION = "2025.1.0"
API_VERSION = "2.0.0"

def init_public_routes(app):
    """Инициализация публичных маршрутов для клиентов RustDesk"""
    
    @app.route('/api/sysinfo', methods=['POST'])
    def register_sysinfo():
        client_ip = request.remote_addr
        raw_data = request.get_data(as_text=True)
        content_length = request.content_length
        
        if not raw_data or content_length == 0:
            error_logger.info(f"Sysinfo: Empty request from {client_ip}, returning version info")
            return f"RustDesk Monitor v{SERVER_VERSION}", 200
        
        try:
            if request.is_json:
                data = request.get_json()
            else:
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError as e:
                    error_logger.error(f"Sysinfo JSON error from {client_ip}: {e}")
                    return "MISSING_UUID", 400
            
            if not data:
                return "MISSING_UUID", 400
            
            if 'uuid' not in data:
                error_logger.error(f"Sysinfo: Missing UUID from {client_ip}")
                return "MISSING_UUID", 400
            
            computer, result = update_sysinfo(data, client_ip)
            if not computer:
                return "MISSING_UUID", 400
            
            sysinfo_logger.info(f"SYSINFO | UUID={computer['uuid']} | Hostname={computer['hostname']} | Action={result}")
            return "SYSINFO_UPDATED", 200
            
        except json.JSONDecodeError as e:
            error_logger.error(f"Sysinfo JSON error from {client_ip}: {e}")
            return "MISSING_UUID", 400
        except Exception as e:
            error_logger.error(f"Error sysinfo from {client_ip}: {e}")
            return "ERROR", 500
    
    @app.route('/api/heartbeat', methods=['POST'])
    def heartbeat():
        client_ip = request.remote_addr
        raw_data = request.get_data(as_text=True)
        content_length = request.content_length
        
        if not raw_data or content_length == 0:
            heartbeat_logger.info(f"Heartbeat: Empty request from {client_ip}")
            return jsonify({}), 200
        
        try:
            if request.is_json:
                data = request.get_json()
            else:
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError as e:
                    heartbeat_logger.error(f"Heartbeat JSON error from {client_ip}: {e}")
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