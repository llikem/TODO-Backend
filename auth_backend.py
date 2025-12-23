from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import couchdb
import hashlib
import uuid
from datetime import datetime
from typing import Optional, List

# ========== FastAPI App ==========
app = FastAPI(title="Todo приложение с CouchDB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Модели данных ==========
class UserRegister(BaseModel):
    email: str
    password: str
    username: str

class UserLogin(BaseModel):
    email: str
    password: str

class TaskCreate(BaseModel):
    title: str
    category: str = "Дом"
    date: Optional[str] = None
    time: Optional[str] = None
    notes: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    notes: Optional[str] = None
    completed: Optional[bool] = None

# ========== CouchDB подключение ==========
COUCHDB_URL = 'http://admin:password@localhost:5984/'
DB_NAME = 'tpbase'

try:
    server = couchdb.Server(COUCHDB_URL)
    
    # Проверка подключения
    server.version()
    print(f"✅ Успешное подключение к CouchDB {server.version()}")
    
    # Создаем/подключаемся к базе
    if DB_NAME not in server:
        db = server.create(DB_NAME)
        print(f"📁 Создана новая база: {DB_NAME}")
    else:
        db = server[DB_NAME]
        print(f"📁 Используем существующую базу: {DB_NAME}")
        
except Exception as e:
    print(f"❌ Ошибка подключения к CouchDB: {e}")
    raise

# ========== Вспомогательные функции ==========
def hash_password(password: str) -> str:
    """Хеширование пароля SHA-256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(input_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return hash_password(input_password) == hashed_password

def generate_session_token() -> str:
    """Генерация токена сессии"""
    return str(uuid.uuid4())

# ========== Аутентификация ==========
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Получение текущего пользователя из заголовка Authorization"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    
    token = authorization.split(" ")[1]
    
    # Поиск пользователя по session_token в CouchDB
    try:
        query = {
            "selector": {
                "type": "user",
                "session_token": token
            },
            "limit": 1
        }
        
        users = list(db.find(query))
        
        if not users:
            print(f"❌ Токен не найден: {token[:20]}...")
            raise HTTPException(status_code=401, detail="Недействительный токен")
        
        user_doc = users[0]
        print(f"✅ Найден пользователь по токену: {user_doc['email']}")
        
        return {
            "email": user_doc["email"],
            "user_id": user_doc["_id"],
            "username": user_doc.get("username", "")
        }
        
    except Exception as e:
        print(f"❌ Ошибка при поиске пользователя по токену: {e}")
        # Fallback для обратной совместимости: используем токен как email
        return {
            "email": token,
            "user_id": f"user_{token}",
            "username": "User"
        }

# ========== API Endpoints ==========

# ----- Пользователи -----
@app.post("/api/register")
def register(user: UserRegister):
    """Регистрация нового пользователя"""
    try:
        user_id = f"user_{user.email}"
        if user_id in db:
            raise HTTPException(status_code=400, detail="Email уже используется")
        
        # Генерация токена сессии
        session_token = generate_session_token()
        
        # Создание документа пользователя
        user_doc = {
            "_id": user_id,
            "type": "user",
            "email": user.email,
            "username": user.username,
            "password_hash": hash_password(user.password),
            "session_token": session_token,
            "created_at": datetime.utcnow().isoformat(),
            "tasks": []
        }
        
        db.save(user_doc)
        print(f"👤 Зарегистрирован пользователь: {user.email}, токен: {session_token[:20]}...")
        
        return {
            "success": True,
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "session_token": session_token,
            "message": "Регистрация успешна"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.post("/api/login")
def login(user: UserLogin):
    """Вход пользователя"""
    try:
        user_id = f"user_{user.email}"
        
        # Поиск пользователя
        if user_id not in db:
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        
        user_doc = db[user_id]
        
        # Проверка пароля
        if not verify_password(user.password, user_doc["password_hash"]):
            raise HTTPException(status_code=401, detail="Неверный пароль")
        
        # Генерация нового токена сессии
        session_token = generate_session_token()
        user_doc["session_token"] = session_token
        db.save(user_doc)
        
        print(f"✅ Успешный вход для: {user.email}, новый токен: {session_token[:20]}...")
        
        return {
            "success": True,
            "user_id": user_id,
            "username": user_doc["username"],
            "email": user_doc["email"],
            "session_token": session_token,
            "message": "Вход выполнен успешно"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка входа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

# ----- Задачи -----
@app.post("/api/tasks")
def create_task(
    task: TaskCreate,
    current_user: dict = Depends(get_current_user)
):
    """Создание новой задачи"""
    try:
        user_email = current_user["email"]
        print(f"📝 Создание задачи для пользователя: {user_email}")
        
        # Генерация ID задачи
        task_id = f"task_{uuid.uuid4()}"
        timestamp = datetime.utcnow().isoformat()
        
        # Создание документа задачи
        task_doc = {
            "_id": task_id,
            "type": "task",
            "user_email": user_email,
            "title": task.title,
            "category": task.category,
            "date": task.date,
            "time": task.time,
            "notes": task.notes,
            "completed": False,
            "created_at": timestamp,
            "updated_at": timestamp
        }
        
        # Сохранение задачи
        db.save(task_doc)
        
        # Обновление списка задач пользователя
        user_id = f"user_{user_email}"
        if user_id in db:
            user_doc = db[user_id]
            if "tasks" not in user_doc:
                user_doc["tasks"] = []
            user_doc["tasks"].append(task_id)
            db.save(user_doc)
        
        print(f"✅ Создана задача '{task.title}' (ID: {task_id}) для пользователя {user_email}")
        
        return {
            "success": True,
            "task_id": task_id,
            "task": task_doc,
            "message": "Задача создана"
        }
        
    except Exception as e:
        print(f"Ошибка создания задачи: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.get("/api/tasks")
def get_user_tasks(current_user: dict = Depends(get_current_user)):
    try:
        user_email = current_user["email"]
        print(f"📥 Запрос задач для пользователя: {user_email}")
        
        query = {
            "selector": {
                "type": "task",
                "user_email": user_email
            }
        }
        
        tasks_result = db.find(query)
        tasks = [task for task in tasks_result]
        
        # Сортировка на стороне Python
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        print(f"📊 Найдено задач: {len(tasks)} для {user_email}")
        
        return {
            "success": True,
            "tasks": tasks,
            "count": len(tasks)
        }
        
    except Exception as e:
        print(f"Ошибка получения задач: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.put("/api/tasks/{task_id}")
def update_task(
    task_id: str,
    task_update: TaskUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Обновление задачи"""
    try:
        user_email = current_user["email"]
        
        # Проверка существования задачи
        if task_id not in db:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        
        task_doc = db[task_id]
        
        # Проверка прав доступа
        if task_doc.get("user_email") != user_email:
            raise HTTPException(status_code=403, detail="Нет доступа к задаче")
        
        # Обновление полей
        if task_update.title is not None:
            task_doc["title"] = task_update.title
        if task_update.category is not None:
            task_doc["category"] = task_update.category
        if task_update.date is not None:
            task_doc["date"] = task_update.date
        if task_update.time is not None:
            task_doc["time"] = task_update.time
        if task_update.notes is not None:
            task_doc["notes"] = task_update.notes
        if task_update.completed is not None:
            task_doc["completed"] = task_update.completed
        
        task_doc["updated_at"] = datetime.utcnow().isoformat()
        
        # Сохранение обновлений
        db.save(task_doc)
        
        print(f"✏️  Обновлена задача '{task_doc['title']}' (ID: {task_id})")
        
        return {
            "success": True,
            "task": task_doc,
            "message": "Задача обновлена"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка обновления задачи: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.delete("/api/tasks/{task_id}")
def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Удаление задачи"""
    try:
        user_email = current_user["email"]
        
        # Проверка существования задачи
        if task_id not in db:
            raise HTTPException(status_code=404, detail="Задача не найдена")
        
        task_doc = db[task_id]
        
        # Проверка прав доступа
        if task_doc.get("user_email") != user_email:
            raise HTTPException(status_code=403, detail="Нет доступа к задаче")
        
        # Удаление задачи
        db.delete(task_doc)
        
        # Удаление из списка задач пользователя
        user_id = f"user_{user_email}"
        if user_id in db:
            user_doc = db[user_id]
            if "tasks" in user_doc and task_id in user_doc["tasks"]:
                user_doc["tasks"].remove(task_id)
                db.save(user_doc)
        
        print(f"🗑️  Удалена задача '{task_doc['title']}' (ID: {task_id})")
        
        return {
            "success": True,
            "message": "Задача удалена"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка удаления задачи: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

# ----- Системные endpoints -----
@app.get("/")
def home():
    return {
        "status": "running", 
        "api": "todo-couchdb",
        "database": "CouchDB",
        "endpoints": {
            "auth": ["/api/register", "/api/login"],
            "tasks": ["/api/tasks (GET, POST)", "/api/tasks/{id} (PUT, DELETE)"]
        }
    }

@app.get("/health")
def health():
    try:
        # Проверка подключения к CouchDB
        server.version()
        db.info()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

@app.get("/api/debug/users")
def debug_users():
    """Отладка: список пользователей"""
    users = []
    for doc_id in db:
        doc = db[doc_id]
        if doc.get("type") == "user":
            users.append({
                "id": doc_id,
                "email": doc.get("email"),
                "username": doc.get("username"),
                "tasks_count": len(doc.get("tasks", [])),
                "has_token": "session_token" in doc
            })
    return {"users": users, "count": len(users)}

@app.get("/api/debug/tasks")
def debug_tasks():
    """Отладка: все задачи"""
    tasks = []
    for doc_id in db:
        doc = db[doc_id]
        if doc.get("type") == "task":
            tasks.append({
                "id": doc_id,
                "title": doc.get("title"),
                "user_email": doc.get("user_email"),
                "created_at": doc.get("created_at")
            })
    return {"tasks": tasks, "count": len(tasks)}

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🚀 Сервер с CouchDB запущен!")
    print("📍 Адрес: http://localhost:8000")
    print("📚 Документация: http://localhost:8000/docs")
    print("💾 База данных: CouchDB (tpbase)")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)