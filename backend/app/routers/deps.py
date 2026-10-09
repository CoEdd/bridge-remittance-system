"""Dependencies shared by the routers."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.seed import DEMO_USER_ID

SessionDep = Annotated[Session, Depends(get_session)]


def current_user(session: SessionDep) -> User:
    """The sandbox has one user, Ahmad. There is no login."""
    return session.get_one(User, DEMO_USER_ID)


UserDep = Annotated[User, Depends(current_user)]
