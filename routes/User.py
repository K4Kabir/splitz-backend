from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import get_db
from utils.helper import (
    hash_password,
    verify_password,
    create_access_token,
)
from models import User


router = APIRouter()


class UserModel(BaseModel):
    email: str
    password: str
    username: str
    is_active: bool = True


class LoginUser(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    token: str


@router.post("/register")
def register_user(user_data: UserModel, db: Session = Depends(get_db)):
    try:

        existing_user = db.query(User).filter(User.email == user_data.email).first()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already exists with this Email",
            )

        hashed_password = hash_password(user_data.password)

        new_user = User(
            email=user_data.email,
            username=user_data.username,
            password=hashed_password,
        )

        db.add(new_user)
        db.commit()

        db.refresh(new_user)

        return {"message": "User created successfully", "user_id": new_user.id}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/login")
def register_user(login_data: LoginUser, db: Session = Depends(get_db)):
    try:
        check_user = db.query(User).filter(User.email == login_data.email).first()
        if not check_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not exist. Please register first",
            )
        correct_password = verify_password(login_data.password, check_user.password)

        if not correct_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Incorrect Username or password",
            )
        jwt_token = create_access_token(data={"sub": check_user.email})
        return {
            "id": check_user.id,
            "email": check_user.email,
            "username": check_user.username,
            "token": jwt_token,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
