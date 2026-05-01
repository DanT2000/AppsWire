import os
from dotenv import load_dotenv
from fastapi import Request, HTTPException

load_dotenv()
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or "").strip()

def check_admin(request: Request):
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD is not set")
    if request.cookies.get("admin") != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Not authorized")