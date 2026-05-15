#!/bin/bash

echo "🚀 Подготовка к выгрузке на GitHub..."
echo "======================================"

# Проверяем наличие изменений
if [[ -z $(git status -s) ]]; then
    echo "❌ Нет изменений для коммита."
    exit 1
fi

echo "📝 Изменения для коммита:"
git status -s
echo ""

# Добавляем все изменения
echo "📦 Добавляем файлы..."
git add .

# Создаем коммит
echo "📝 Создаем коммит..."
git commit -m "Release v5.0: Stable version with SQLite and authentication

- SQLite database for reliable storage
- User authentication system with roles (admin/user)
- Admin panel for user management
- Device management (delete devices)
- Corporate design
- Fixed database locking issues
- Optimized query execution"

# Проверяем наличие remote
if ! git remote | grep -q origin; then
    echo "➕ Добавляем remote origin..."
    git remote add origin https://github.com/fiverok/sveApiRust.git
fi

# Отправляем изменения
echo "⬆️ Отправляем на GitHub..."
git push -u origin main 2>/dev/null || git push -u origin master

# Создаем тег
echo "🏷️ Создаем тег v5.0..."
git tag -a v5.0 -m "Version 5.0: Stable release with SQLite and authentication"
git push origin v5.0

echo ""
echo "✅ Готово! Изменения выгружены на GitHub"
echo "🔗 Репозиторий: https://github.com/fiverok/sveApiRust"
echo "🏷️ Тег: v5.0"
echo ""
echo "📊 Статистика:"
echo "   - Всего коммитов: $(git rev-list --count HEAD)"
echo "   - Размер репозитория: $(du -sh .git | cut -f1)"
