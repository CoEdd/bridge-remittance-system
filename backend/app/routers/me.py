from fastapi import APIRouter

from app.routers.deps import SessionDep, UserDep
from app.schemas import LanguageUpdate, UserOut

router = APIRouter(tags=["me"])


@router.get("/me")
def get_me(user: UserDep) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me")
def update_me(update: LanguageUpdate, session: SessionDep, user: UserDep) -> UserOut:
    user.preferred_language = update.preferred_language
    session.commit()
    return UserOut.model_validate(user)
