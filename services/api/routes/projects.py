import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Project, User
from db.session import get_db
from services.api.schemas import ProjectCreate, ProjectDetail, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


def current_user(db: Session = Depends(get_db)) -> User:
    """Single local creator until auth exists (multi-user is out of MVP scope)."""
    user = db.scalar(select(User).where(User.handle == "default"))
    if user is None:
        user = User(handle="default", display_name="Default creator")
        db.add(user)
        db.flush()
    return user


def get_project(project_id: uuid.UUID, db: Session) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, f"project {project_id} not found")
    return p


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = Project(owner_id=user.id, title=body.title, description=body.description)
    db.add(p)
    db.flush()
    return p


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.created_at.desc())).all()


@router.get("/{project_id}", response_model=ProjectDetail)
def read_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_project(project_id, db)
