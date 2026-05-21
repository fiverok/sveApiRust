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
git commit -m "Добавлен автовыход из системы при бездействии 2 часа

- Добавлена проверка сессии каждую минуту
- Отслеживание активности пользователя (клики, клавиши, движение мыши)
- При бездействии 2 часа - автоматический выход
- Уведомление об истечении сессии
- API эндпоинты для проверки и продления сессии
- Исправлен конфликт маршрутов выхода
- Добавлено логирование событий таймаута в audit_log
"

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
git tag -a v5.1 -m "Добавлен автовыход из системы при бездействии 2 часа"
git push origin v5.1

echo ""
echo "✅ Готово! Изменения выгружены на GitHub"
echo "🔗 Репозиторий: https://github.com/fiverok/sveApiRust"
echo "🏷️ Тег: v5.0"
echo ""
echo "📊 Статистика:"
echo "   - Всего коммитов: $(git rev-list --count HEAD)"
echo "   - Размер репозитория: $(du -sh .git | cut -f1)"
