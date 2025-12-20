1. Установи Python 3.13.3
2. Создать виртуальное окружение: py -3.13 -m venv venv
3. Запустить виртуальное окружение: source venv/Scripts/activate
4. Установи зависимости: pip install -r requirements.txt
5. Запустить: python auth_backend.py
6. Документация: http://localhost:8000/docs

Эндпоинты:
- POST /api/register - регистрация
- POST /api/login - вход
- GET /api/users - список пользователей (тест)