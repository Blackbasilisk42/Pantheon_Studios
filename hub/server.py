from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import Comment, MediaAsset, Submission, User, get_db, get_password_hash, init_db, verify_password

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT.parent / ".env")

SECRET_KEY = os.getenv("HUB_SECRET_KEY", "pantheon-team-hub-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

app = FastAPI(title="Pantheon Studios")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

templates = Jinja2Templates(directory=str(ROOT / "templates"))


def create_access_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _redirect_with_notice(message: str, level: str = "info") -> RedirectResponse:
    encoded_message = quote_plus(message)
    encoded_level = quote_plus(level)
    return RedirectResponse(url=f"/?notice={encoded_message}&notice_level={encoded_level}", status_code=303)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None
        return db.query(User).filter(User.username == username).first()
    except JWTError:
        return None


def require_admin(user: Optional[User]) -> User:
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_member(user: Optional[User]) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    assets = db.query(MediaAsset).order_by(MediaAsset.created_at.desc()).all()
    submissions = db.query(Submission).order_by(Submission.timestamp.desc()).all()
    notice = request.query_params.get("notice")
    notice_level = request.query_params.get("notice_level", "info")
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "assets": assets,
            "submissions": submissions,
            "notice": notice,
            "notice_level": notice_level,
        },
    )


@app.get("/team", response_class=HTMLResponse)
async def team_dashboard(request: Request):
    return templates.TemplateResponse(
        "team.html",
        {
            "request": request,
        },
    )


@app.get("/api/me")
def me(request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    return JSONResponse({"authenticated": True, "username": user.username, "role": user.role})


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)) -> RedirectResponse:
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return _redirect_with_notice("Invalid username or password.", "error")
    token = create_access_token(user.username)
    redirect = _redirect_with_notice(f"Welcome back, {user.username}.", "success")
    redirect.set_cookie(key="access_token", value=token, httponly=True, samesite="lax")
    return redirect


@app.post("/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    avatar_url: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    clean_username = username.strip()
    if len(clean_username) < 3:
        return _redirect_with_notice("Username must be at least 3 characters.", "error")
    if len(password) < 8:
        return _redirect_with_notice("Password must be at least 8 characters.", "error")
    if password != confirm_password:
        return _redirect_with_notice("Password confirmation does not match.", "error")

    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        return _redirect_with_notice("That username is already in use.", "error")

    user = User(
        username=clean_username,
        password_hash=get_password_hash(password),
        role="member",
        avatar_url=avatar_url.strip() or None,
    )
    db.add(user)
    db.commit()

    token = create_access_token(user.username)
    redirect = _redirect_with_notice(f"Account created for {user.username}.", "success")
    redirect.set_cookie(key="access_token", value=token, httponly=True, samesite="lax")
    return redirect


@app.post("/account/setup")
def account_setup(
    request: Request,
    username: str = Form(default=""),
    avatar_url: str = Form(default=""),
    new_password: str = Form(default=""),
    confirm_new_password: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    user = get_current_user(request, db)
    user = require_member(user)

    changed_fields: list[str] = []
    next_username = user.username

    requested_username = username.strip()
    if requested_username and requested_username != user.username:
        if len(requested_username) < 3:
            return _redirect_with_notice("New username must be at least 3 characters.", "error")
        username_taken = db.query(User).filter(User.username == requested_username).first()
        if username_taken:
            return _redirect_with_notice("That new username is already taken.", "error")
        user.username = requested_username
        next_username = requested_username
        changed_fields.append("username")

    requested_avatar = avatar_url.strip()
    normalized_avatar = requested_avatar or None
    if normalized_avatar != user.avatar_url:
        user.avatar_url = normalized_avatar
        changed_fields.append("avatar")

    if new_password:
        if len(new_password) < 8:
            return _redirect_with_notice("New password must be at least 8 characters.", "error")
        if new_password != confirm_new_password:
            return _redirect_with_notice("New password confirmation does not match.", "error")
        user.password_hash = get_password_hash(new_password)
        changed_fields.append("password")
    elif confirm_new_password:
        return _redirect_with_notice("Enter a new password before confirming it.", "error")

    if not changed_fields:
        return _redirect_with_notice("No account changes detected.", "info")

    db.commit()

    redirect = _redirect_with_notice("Account settings updated.", "success")
    if "username" in changed_fields or "password" in changed_fields:
        token = create_access_token(next_username)
        redirect.set_cookie(key="access_token", value=token, httponly=True, samesite="lax")
    return redirect


@app.post("/logout")
def logout() -> RedirectResponse:
    redirect = _redirect_with_notice("Logged out.", "info")
    redirect.delete_cookie("access_token")
    return redirect


@app.post("/upload")
def upload_asset(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    media_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    user = get_current_user(request, db)
    require_member(user)
    file_name = f"{secrets.token_hex(4)}_{file.filename or 'asset'}"
    destination = UPLOAD_DIR / file_name
    with destination.open("wb") as buffer:
        buffer.write(file.file.read())

    asset = MediaAsset(
        title=title,
        description=description,
        file_path=str(destination.relative_to(ROOT)),
        media_type=media_type,
        uploader_id=user.id,
    )
    db.add(asset)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/submissions")
def create_submission(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    user = get_current_user(request, db)
    require_member(user)
    submission = Submission(title=title, content=content, uploader_id=user.id, status="pending")
    db.add(submission)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/comments/{asset_id}")
def create_comment(
    asset_id: int,
    request: Request,
    comment_text: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    user = get_current_user(request, db)
    require_member(user)
    comment = Comment(asset_id=asset_id, user_id=user.id, comment_text=comment_text)
    db.add(comment)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/admin/submissions/{submission_id}/approve")
def approve_submission(submission_id: int, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    user = get_current_user(request, db)
    require_admin(user)
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    submission.status = "approved"
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/admin/submissions/{submission_id}/reject")
def reject_submission(submission_id: int, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    user = get_current_user(request, db)
    require_admin(user)
    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    submission.status = "rejected"
    db.commit()
    return RedirectResponse(url="/", status_code=303)
