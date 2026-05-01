import os
import shutil
from pathlib import Path
from typing import List, Optional

import markdown
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, Base
from .models import Project, Action
from .auth import check_admin

load_dotenv()

# Paths
APP_DIR = Path(__file__).resolve().parent          # .../app
ROOT_DIR = APP_DIR.parent                         # .../appswire
STORAGE_DIR = ROOT_DIR / "storage"
PROJECTS_DIR = STORAGE_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# DB
Base.metadata.create_all(bind=engine)

# App
app = FastAPI()
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Static assets (css/js/favicon)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
# Uploaded assets (images/files) live in storage/
app.mount("/media", StaticFiles(directory=str(STORAGE_DIR)), name="media")


# ---------------- DB Session ----------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- Helpers ----------------

@app.get("/favicon.ico")
def favicon():
    ico = APP_DIR / "static" / "favicon.ico"
    if ico.exists():
        return FileResponse(str(ico))
    return RedirectResponse("/static/favicon.ico", status_code=302)


def ensure_project_dirs(pid: int) -> Path:
    """Ensure /storage/projects/<pid>/files exists and return project dir."""
    d = PROJECTS_DIR / str(pid)
    (d / "files").mkdir(parents=True, exist_ok=True)
    return d


def md_clean(s: Optional[str]) -> str:
    return (s or "").strip()


def safe_filename(name: str) -> str:
    # simple sanitize for paths
    name = name.replace("\\", "_").replace("/", "_")
    return name[:180] if len(name) > 180 else name


# ---------------- FRONT ----------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.id.desc()).all()
    return templates.TemplateResponse(request, "index.html", {"projects": projects})


@app.get("/instruction/{project_id}", response_class=HTMLResponse)
def instruction(project_id: int, request: Request, db: Session = Depends(get_db)):
    p = db.query(Project).get(project_id)
    if not p or not (p.instruction_md or "").strip():
        return RedirectResponse("/", status_code=302)

    html = markdown.markdown(
        p.instruction_md,
        extensions=["fenced_code", "tables"]
    )
    return templates.TemplateResponse(
        "instruction.html",
        {"request": request, "project": p, "content": html}
    )


@app.get("/download/{action_id}")
def download(action_id: int, db: Session = Depends(get_db)):
    a = db.query(Action).get(action_id)
    if not a or a.kind != "download" or not a.file_path:
        return RedirectResponse("/", status_code=302)

    abs_path = STORAGE_DIR / a.file_path
    if not abs_path.exists():
        return RedirectResponse("/", status_code=302)

    return FileResponse(str(abs_path), filename=abs_path.name)


# ---------------- ADMIN ----------------

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, db: Session = Depends(get_db)):
    authed = request.cookies.get("admin") == (os.getenv("ADMIN_PASSWORD") or "")
    if not authed:
        return templates.TemplateResponse(
    request,
    "admin.html",
    {"dashboard": False}
)

    projects = db.query(Project).order_by(Project.id.desc()).all()
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "dashboard": True, "projects": projects, "edit_project": None}
    )


@app.post("/admin/login")
def admin_login(password: str = Form(...)):
    if password == (os.getenv("ADMIN_PASSWORD") or ""):
        r = RedirectResponse("/admin", status_code=302)
        r.set_cookie("admin", password, httponly=True, samesite="lax")
        return r
    return RedirectResponse("/admin", status_code=302)


@app.get("/admin/logout")
def admin_logout():
    r = RedirectResponse("/admin", status_code=302)
    r.delete_cookie("admin")
    return r


@app.get("/admin/edit/{project_id}", response_class=HTMLResponse)
def admin_edit(project_id: int, request: Request, db: Session = Depends(get_db)):
    check_admin(request)
    projects = db.query(Project).order_by(Project.id.desc()).all()
    edit_project = db.query(Project).get(project_id)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "dashboard": True, "projects": projects, "edit_project": edit_project}
    )


@app.post("/admin/delete/{project_id}")
def admin_delete(project_id: int, request: Request, db: Session = Depends(get_db)):
    check_admin(request)

    p = db.query(Project).get(project_id)
    if p:
        db.delete(p)
        db.commit()

    # remove all project files
    shutil.rmtree(PROJECTS_DIR / str(project_id), ignore_errors=True)
    return RedirectResponse("/admin", status_code=302)


@app.post("/admin/save")
async def admin_save(
    request: Request,
    db: Session = Depends(get_db),

    project_id: int = Form(0),
    title: str = Form(...),
    description: str = Form(...),
    version: str = Form("1.0.0"),

    image_mode: str = Form("url"),  # none | url | upload
    image_url: str = Form(""),
    image_file: UploadFile = File(None),

    instruction_md: str = Form(""),

    # actions arrays
    action_kind: List[str] = Form([]),
    action_label: List[str] = Form([]),
    action_url: List[str] = Form([]),
    action_existing_file: List[str] = Form([]),
    action_clear_file: List[str] = Form([]),
    primary_index: int = Form(-1),

    action_file: List[UploadFile] = File([]),
):
    check_admin(request)

    instruction_md = md_clean(instruction_md)

    # Create or update project
    if project_id and project_id > 0:
        p = db.query(Project).get(project_id)
        if not p:
            return RedirectResponse("/admin", status_code=302)
        p.title = title
        p.description = description
        p.version = version
        p.instruction_md = instruction_md
    else:
        p = Project(
            title=title,
            description=description,
            version=version,
            instruction_md=instruction_md
        )
        db.add(p)
        db.commit()
        db.refresh(p)

    # image handling
    if image_mode == "none":
        p.image_url = None
        p.image_path = None

    elif image_mode == "url":
        p.image_url = image_url.strip() or None
        p.image_path = None

    elif image_mode == "upload":
        if image_file and image_file.filename:
            ensure_project_dirs(p.id)
            ext = Path(image_file.filename).suffix.lower()
            if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".ico"]:
                ext = ".png"
            img_abs = (PROJECTS_DIR / str(p.id)) / f"image{ext}"
            with open(img_abs, "wb") as f:
                shutil.copyfileobj(image_file.file, f)

            p.image_path = f"projects/{p.id}/{img_abs.name}"
            p.image_url = None

    # rebuild actions while preserving existing file_path if no new upload
    p.actions.clear()
    db.commit()

    for i in range(len(action_kind)):
        kind = (action_kind[i] or "").strip()
        label = (action_label[i] or "").strip()
        url = (action_url[i] or "").strip()

        if not kind or not label:
            continue

        a = Action(
            kind=kind,
            label=label,
            is_primary=(i == primary_index)
        )

        if kind == "link":
            a.url = url or None
            a.file_path = None
            p.actions.append(a)
            continue

        if kind == "download":
            existing = action_existing_file[i] if i < len(action_existing_file) else ""
            clear = action_clear_file[i] if i < len(action_clear_file) else "0"

            fp = None

            if clear == "1":
                # remove old file if exists
                if existing:
                    abs_old = STORAGE_DIR / existing
                    if abs_old.exists():
                        try:
                            abs_old.unlink()
                        except:
                            pass
                fp = None

            else:
                uploaded = action_file[i] if i < len(action_file) else None
                if uploaded and uploaded.filename:
                    d = ensure_project_dirs(p.id) / "files"
                    out_name = safe_filename(Path(uploaded.filename).name)
                    out_abs = d / out_name
                    with open(out_abs, "wb") as f:
                        shutil.copyfileobj(uploaded.file, f)
                    fp = f"projects/{p.id}/files/{out_abs.name}"
                else:
                    # keep existing if no new upload
                    fp = existing or None

            a.file_path = fp
            a.url = None
            p.actions.append(a)
            continue

    db.commit()
    return RedirectResponse(f"/admin/edit/{p.id}", status_code=302)