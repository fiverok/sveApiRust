# Модули базы данных
from modules.database import (
    get_db_connection, execute_query, init_db,
    get_computer_by_uuid, get_computer_by_id, delete_computer_by_uuid,
    update_sysinfo, update_heartbeat, get_all_computers, get_stats
)

# Модули аутентификации
from modules.auth import (
    hash_password, verify_password, add_audit_log,
    require_auth, require_admin,
    get_user_by_username, get_all_users, create_user, delete_user,
    update_user_last_login
)

# Модули API
from modules.api_auth import init_auth_routes
from modules.api_computers import init_computers_routes
from modules.api_public import init_public_routes