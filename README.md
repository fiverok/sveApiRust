## Версия 5.0 (SQLite + Authentication)

### Новые возможности:
- **SQLite база данных** - надежное и производительное хранение
- **Система авторизации** - защита веб-интерфейса
- **Роли пользователей** - admin и user
- **Управление пользователями** - добавление/удаление через API
- **Удаление клиентов** - администратор может удалять записи
- **Лог аудита** - отслеживание всех действий
- **Smart heartbeat** - автоматическое связывание ID и UUID

### API Endpoints:

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/login` | POST | - | Вход в систему |
| `/api/users` | GET | Admin | Список пользователей |
| `/api/users` | POST | Admin | Создание пользователя |
| `/api/users/<id>` | DELETE | Admin | Удаление пользователя |
| `/api/computers/<uuid>` | DELETE | Admin | Удаление компьютера |
| `/api/computers` | GET | Auth | Список компьютеров |
| `/api/audit` | GET | Admin | Лог аудита |
| `/api/sysinfo` | POST | - | Регистрация устройства |
| `/api/heartbeat` | POST | - | Heartbeat |

### Первый вход:
- URL: `http://your-server:21114`
- Логин: `admin`
- Пароль: `admin`