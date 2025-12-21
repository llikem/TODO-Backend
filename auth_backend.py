from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import json
import os

app = FastAPI(title="Todo приложение")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserRegister(BaseModel):
    email: str
    password: str
    username: str

class UserLogin(BaseModel):
    email: str
    password: str

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "users.json")

def load_users():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            print(f"Ошибка загрузки файла: {e}")
            return {}
    return {}

def save_users(users):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

def hash_password(pwd):
    return hashlib.sha256(pwd.encode('utf-8')).hexdigest()

@app.get("/")
def home():
    return {"status": "running", "api": "todo-auth"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/api/register")
def register(user: UserRegister):
    try:
        users = load_users()
        
        for u in users.values():
            if u.get("email") == user.email:
                raise HTTPException(status_code=400, detail="Email уже используется")
        
        user_id = str(len(users) + 1)
        
        password_hash = hash_password(user.password)
        
        users[user_id] = {
            "id": user_id,
            "email": user.email,
            "username": user.username,
            "password_hash": password_hash
        }
        
        save_users(users)
        
        print(f"Зарегистрирован пользователь: {user.email}, хеш: {password_hash[:20]}...")
        
        return {
            "success": True,
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "message": "Регистрация успешна"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.post("/api/login")
def login(user: UserLogin):
    try:
        users = load_users()
        
        print(f"Попытка входа: {user.email}")
        print(f"Всего пользователей в базе: {len(users)}")
        
        found_user = None
        found_id = None
        
        for user_id, u in users.items():
            print(f"Проверяем: {u.get('email')}")
            if u.get("email") == user.email:
                found_user = u
                found_id = user_id
                break
        
        if not found_user:
            print(f"Пользователь {user.email} не найден")
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        
        input_hash = hash_password(user.password)
        stored_hash = found_user.get("password_hash", "")
        
        print(f"Введенный пароль хеш: {input_hash[:30]}...")
        print(f"Сохраненный хеш: {stored_hash[:30]}...")
        
        if input_hash == stored_hash:
            print(f"Успешный вход для: {user.email}")
            return {
                "success": True,
                "user_id": found_id,
                "username": found_user.get("username", ""),
                "email": found_user.get("email", ""),
                "message": "Вход выполнен успешно"
            }
        else:
            print(f"Неверный пароль для: {user.email}")
            print(f"Хеши не совпадают!")
            raise HTTPException(status_code=401, detail="Неверный пароль")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка входа: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.get("/api/users")
def get_users():
    users = load_users()
    print(f"Запрос списка пользователей. Найдено: {len(users)}")
    for uid, u in users.items():
        print(f"   {uid}: {u.get('email')} - {u.get('password_hash', '')[:20]}...")
    return users

@app.get("/api/debug")
def debug():
    users = load_users()
    return {
        "total_users": len(users),
        "users": users,
        "file_exists": os.path.exists(DATA_FILE)
    }

if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False)
        print(f"📁 Создан файл {DATA_FILE}")
    else:
        print(f"📁 Используем существующий файл {DATA_FILE}")
    
    import uvicorn
    
    print("=" * 60)
    print("Сервер авторизации запущен!")
    print("Адрес: http://localhost:8000")
    print("Документация: http://localhost:8000/docs")
    print("Health: http://localhost:8000/health")
    print("Debug: http://localhost:8000/api/debug")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)