# app/schemas.py

from pydantic import BaseModel
from typing import Optional

class ProjectCreate(BaseModel):
    title: str
    description: str
    version: Optional[str] = "1.0.0"
    image: Optional[str] = None
    instruction: Optional[str] = None