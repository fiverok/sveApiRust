#!/bin/bash

echo "🚀 Подготовка к выгрузке на GitHub..."
echo "======================================"

# Добавляем файлы в .gitignore
echo "🔧 Настройка .gitignore..."
cat > .gitignore << 'EOF'
# Лог-файлы
*.log
logs/
*.log.*

# Базы данных
*.db
*.sqlite
*.sqlite3
*.db-journal

# Системные файлы
.DS_Store
Thumbs.db
*.tmp
*.temp

# Файлы окружения
.env
.env.local
.env.*.local

# Файлы IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Файлы сборки
/target/
debug/
release/
Cargo.lock
EOF

echo "✅ .gitignore обновлен"

# Проверяем наличие изменений (игнорируя исключенные файлы)
if [[ -z $(git status -s --ignore-submodules) ]]; then
    echo "⚠️ Нет изменений для коммита."
    echo "Но продолжаем для обновления тега..."
fi

# Удаляем из индекса уже отслеживаемые файлы логов и БД (если были добавлены ранее)
echo "🧹 Очищаем отслеживание лог-файлов и БД..."
git rm --cached -q *.log 2>/dev/null
git rm --cached -q *.db 2>/dev/null
git rm --cached -q logs/*.log 2>/dev/null

# Добавляем все изменения
echo "📦 Добавляем файлы..."
git add .

# Проверяем, есть ли изменения для коммита
if [[ -n $(git status -s) ]]; then
    # Создаем коммит
    echo "📝 Создаем коммит..."
    git commit -m "Release v5.0: Stable version with SQLite and authentication

- SQLite database for reliable storage
- User authentication system with roles (admin/user)
- Admin panel for user management
- Device management (delete devices)
- Corporate design
- Fixed database locking issues
- Optimized query execution
- Added .gitignore for logs and database files"
else
    echo "ℹ️ Нет новых изменений для коммита"
fi

# Проверяем и создаем ветку main/master если нужно
CURRENT_BRANCH=$(git branch --show-current)
if [[ -z "$CURRENT_BRANCH" ]]; then
    echo "🔄 Создаем ветку main..."
    git checkout -b main
    CURRENT_BRANCH="main"
fi

# Проверяем наличие remote
if ! git remote | grep -q origin; then
    echo "➕ Добавляем remote origin..."
    git remote add origin https://github.com/fiverok/sveApiRust.git
fi

# Определяем основную ветку
if git show-ref --verify --quiet refs/heads/main; then
    BRANCH="main"
elif git show-ref --verify --quiet refs/heads/master; then
    BRANCH="master"
else
    BRANCH=$CURRENT_BRANCH
    echo "🔄 Создаем ветку main..."
    git checkout -b main
    BRANCH="main"
fi

# Отправляем изменения
echo "⬆️ Отправляем на GitHub (ветка: $BRANCH)..."
git push -u origin $BRANCH

# Обновляем тег v5.0 (удаляем старый и создаем новый)
echo "🏷️ Обновляем тег v5.0..."
git tag -d v5.0 2>/dev/null
git push origin :refs/tags/v5.0 2>/dev/null
git tag -a v5.0 -m "Version 5.0: Stable release with SQLite and authentication"
git push origin v5.0

echo ""
echo "✅ Готово! Изменения выгружены на GitHub"
echo "🔗 Репозиторий: https://github.com/fiverok/sveApiRust"
echo "🏷️ Тег: v5.0 (обновлен)"
echo ""
echo "📊 Статистика:"
echo "   - Текущая ветка: $BRANCH"
echo "   - Всего коммитов: $(git rev-list --count HEAD)"
echo "   - Размер репозитория: $(du -sh .git | cut -f1)"
echo ""
echo "🚫 Исключенные файлы:"
echo "   - Все *.log файлы"
echo "   - Все *.db, *.sqlite файлы"
echo "   - Папка logs/"