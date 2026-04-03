from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    password = Column(String)

    # Relationships
    expenses_involved = relationship("ExpenseUser", back_populates="user")


class Group(Base):
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_ids = Column(ARRAY(Integer), nullable=True)
    expenses = relationship("Expense", back_populates="group")


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    group = relationship("Group", back_populates="expenses")
    # This links to the bridge table
    user_associations = relationship(
        "ExpenseUser", back_populates="expense", cascade="all, delete-orphan"
    )


class ExpenseUser(Base):
    """
    The Bridge Table: This is where the 'Taxi' logic lives.
    It tracks how much a specific user PAID vs how much they OWE for one expense.
    """

    __tablename__ = "expense_users"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), primary_key=True)

    paid_amount = Column(
        Float, default=0.0
    )  # What they contributed (e.g., your Rs 500)
    owed_amount = Column(
        Float, default=0.0
    )  # Their share of the bill (e.g., Rs 233.33)

    user = relationship("User", back_populates="expenses_involved")
    expense = relationship("Expense", back_populates="user_associations")
