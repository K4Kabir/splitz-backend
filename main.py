from fastapi import FastAPI
from routes.User import router as user_router
from routes.Expense import router as expense_router
from fastapi.middleware.cors import CORSMiddleware
from db.database import Base, engine
import models

origins = ["*"]

Base.metadata.create_all(bind=engine)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers (Authorization, Content-Type, etc.)
)


app.include_router(user_router, prefix="/user", tags=["User Interface"])
app.include_router(expense_router, prefix="/expense", tags=["Messages Interface"])
