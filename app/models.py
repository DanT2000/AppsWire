from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    version = Column(String, nullable=False, default="1.0.0")

    # image either URL or upload path (served via /media/...)
    image_url = Column(Text, nullable=True)
    image_path = Column(Text, nullable=True)

    # markdown instruction
    instruction_md = Column(Text, nullable=True)

    actions = relationship(
        "Action",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # download | link
    kind = Column(String, nullable=False)
    label = Column(String, nullable=False)

    # for link
    url = Column(Text, nullable=True)

    # for download: path inside storage, like projects/<id>/files/<name>
    file_path = Column(Text, nullable=True)

    is_primary = Column(Boolean, default=False)

    project = relationship("Project", back_populates="actions")