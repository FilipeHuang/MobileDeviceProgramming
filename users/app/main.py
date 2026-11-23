import os, datetime as dt
import bcrypt, jwt
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, Column, Integer, String, DateTime, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session

SECRET = os.environ["JWT_SECRET"]
engine = create_engine(os.getenv("DATABASE_URL", "sqlite:////data/users.db"), connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def use_wal(conn, _): conn.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    description = Column(String, default="")
    avatar_url = Column(String, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)

Base.metadata.create_all(engine)
app = FastAPI(title="Users service")

@app.exception_handler(HTTPException)
async def http_error(_, exc): return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_error(_, exc): return JSONResponse({"error": "Invalid input"}, status_code=400)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

bearer = HTTPBearer(auto_error=False)   
def current_user_id(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> int:
    if creds is None: raise HTTPException(401, "Login required")
    try: data = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Invalid or expired token")
    return int(data["sub"])

def public(u: User) -> dict:
    return {"id": u.id, "username": u.username, "description": u.description, "avatarUrl": u.avatar_url}

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[a-z0-9_]+$")
    password: str = Field(min_length=6, max_length=72)
    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, v): return v.strip().lower() if isinstance(v, str) else v

class ProfileUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=300)
    avatarUrl: str | None = None

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/auth/register", status_code=201)
def register(c: Credentials, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == c.username).first(): raise HTTPException(409, "Username already taken")
    hashed = bcrypt.hashpw(c.password.encode(), bcrypt.gensalt()).decode()
    u = User(username=c.username, password_hash=hashed)
    db.add(u); db.commit(); db.refresh(u)
    return public(u)

@app.post("/auth/login")
def login(c: Credentials, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.username == c.username).first()
    if not u or not bcrypt.checkpw(c.password.encode(), u.password_hash.encode()): raise HTTPException(401, "Wrong username or password")
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)
    token = jwt.encode({"sub": str(u.id), "username": u.username, "exp": exp}, SECRET, algorithm="HS256")
    return {"token": token, "user": public(u)}

@app.get("/users")
def search_users(search: str = "", db: Session = Depends(get_db)):
    q = db.query(User).filter(User.username.ilike(f"%{search}%")).limit(30)
    return [public(u) for u in q]

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u: raise HTTPException(404, "User not found")
    return public(u)

@app.put("/users/me")
def update_me(body: ProfileUpdate, uid: int = Depends(current_user_id), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u: raise HTTPException(404, "User not found")
    if body.description is not None: u.description = body.description
    if body.avatarUrl is not None: u.avatar_url = body.avatarUrl
    db.commit()
    return public(u)