import os, re, uuid, datetime as dt
import jwt
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session

SECRET = os.environ["JWT_SECRET"]
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/data/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
CATEGORIES = ["Crops", "Livestock", "Tools", "Trading", "Tips", "General"]

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:////data/content.db"),
                       connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def use_wal(conn, _):
    conn.execute("PRAGMA journal_mode=WAL")

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, nullable=False, index=True)
    author_username = Column(String, nullable=False)
    text = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    photo_url = Column(String, default="")
    views = Column(Integer, default=0)
    score = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)

class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    name = Column(String, index=True)

Base.metadata.create_all(engine)
app = FastAPI(title="Content service")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.exception_handler(HTTPException)
async def http_error(_, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    return JSONResponse({"error": "Invalid input"}, status_code=400)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

bearer = HTTPBearer(auto_error=False)

def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(401, "Login required")
    try:
        d = jwt.decode(creds.credentials, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return {"id": int(d["sub"]), "username": d["username"]}

def serialize(posts, db: Session) -> list[dict]:
    ids = [p.id for p in posts]
    tags = {}
    if ids:
        for t in db.query(Tag).filter(Tag.post_id.in_(ids)):
            tags.setdefault(t.post_id, []).append(t.name)
    return [{"id": p.id, "authorId": p.author_id, "authorUsername": p.author_username,
             "text": p.text, "category": p.category, "photoUrl": p.photo_url or "",
             "tags": tags.get(p.id, []), "views": p.views, "score": p.score,
             "createdAt": p.created_at.isoformat() + "Z"} for p in posts]

class PostCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    category: str
    tags: list[str] = Field(default_factory=list, max_length=5)
    photoUrl: str | None = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/categories")
def categories():
    return CATEGORIES

@app.post("/uploads", status_code=201)
async def upload(file: UploadFile = File(...), user: dict = Depends(current_user)):
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(file.content_type)
    if not ext:
        raise HTTPException(400, "Only JPEG, PNG or WebP images")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 5 MB)")
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return {"url": f"/uploads/{name}"}

@app.post("/posts", status_code=201)
def create_post(body: PostCreate, user: dict = Depends(current_user),
                db: Session = Depends(get_db)):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Unknown category")
    if body.photoUrl and not body.photoUrl.startswith("/uploads/"):
        raise HTTPException(400, "Invalid photo URL")
    names = []
    for t in body.tags:
        n = t.strip().lstrip("#").lower()
        if not re.fullmatch(r"[a-z0-9_]{1,30}", n):
            raise HTTPException(400, "Invalid tag")
        if n not in names:
            names.append(n)
    p = Post(author_id=user["id"], author_username=user["username"], text=body.text.strip(),
             category=body.category, photo_url=body.photoUrl or "")
    db.add(p); db.flush()
    for n in names:
        db.add(Tag(post_id=p.id, name=n))
    db.commit(); db.refresh(p)
    return serialize([p], db)[0]

@app.get("/posts")
def list_posts(category: str | None = None, sort: str = "recent", search: str = "",
               authorId: int | None = None, tag: str | None = None,
               limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    q = db.query(Post)
    if category:
        q = q.filter(Post.category == category)
    if authorId:
        q = q.filter(Post.author_id == authorId)
    if search:
        q = q.filter(Post.text.ilike(f"%{search}%"))
    if tag:
        q = q.filter(Post.id.in_(db.query(Tag.post_id).filter(Tag.name == tag.lstrip("#").lower())))
    if sort == "popular":
        q = q.order_by(Post.score.desc(), Post.views.desc(), Post.created_at.desc())
    else:
        q = q.order_by(Post.created_at.desc())
    posts = q.offset(max(offset, 0)).limit(min(max(limit, 1), 50)).all()
    return serialize(posts, db)

@app.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    p = db.get(Post, post_id)
    if not p:
        raise HTTPException(404, "Post not found")
    p.views += 1
    db.commit(); db.refresh(p)
    return serialize([p], db)[0]

@app.delete("/posts/{post_id}")
def delete_post(post_id: int, user: dict = Depends(current_user),
                db: Session = Depends(get_db)):
    p = db.get(Post, post_id)
    if not p:
        raise HTTPException(404, "Post not found")
    if p.author_id != user["id"]:
        raise HTTPException(403, "Not your post")
    db.query(Tag).filter(Tag.post_id == post_id).delete()
    db.delete(p); db.commit()
    return {"status": "deleted"}