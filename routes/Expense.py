from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from db.database import get_db
from utils.helper import verify_user_token
from models import Group, Expense, ExpenseUser, User
from typing import List


router = APIRouter(dependencies=[Depends(verify_user_token)])


class CreateGroup(BaseModel):
    name: str
    user_ids: List[int]


class ParticipantInput(BaseModel):
    user_id: int
    paid_amount: float = 0.0


class ExpenseCreate(BaseModel):
    description: str
    total_amount: float
    group_id: int
    participants: List[ParticipantInput]

    @field_validator("participants")
    @classmethod
    def validate_paid_sum(cls, v, info):
        total_amt = info.data.get("total_amount")
        if sum(p.paid_amount for p in v) != total_amt:
            raise ValueError("Sum of paid_amounts must equal total_amount")
        return v


@router.post("/create_group")
def create_group(
    data: CreateGroup,
    db: Session = Depends(get_db),
):
    try:
        new_group = Group(name=data.name, user_ids=data.user_ids)

        db.add(new_group)
        db.commit()

        db.refresh(new_group)

        return {"message": "Group created successfully", "group_id": new_group.id}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/get_groups")
def get_groups(
    current_user_email = Depends(verify_user_token),
    db: Session = Depends(get_db),
):
    try:

        current_user = db.query(User).filter(User.email == current_user_email).first()

        all_groups = db.query(Group).all()

        my_groups = []

        for group in list(all_groups):
            if (current_user.id in group.user_ids):
                my_groups.append(group)

        return my_groups
 
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )



@router.post("/create_expense")
def create_expense(data: ExpenseCreate, current_user_email = Depends(verify_user_token), db: Session = Depends(get_db)):
    try:
        current_user = db.query(User).filter(User.email == current_user_email).first()

        # 1. Initialize the main Expense
        new_expense = Expense(
            description=data.description,
            total_amount=data.total_amount,
            group_id=data.group_id,
            created_by = current_user.id
        )
        db.add(new_expense)
        db.flush()  # Gets the new_expense.id

        # 2. Calculate the equal share for everyone
        num_participants = len(data.participants)
        equal_share = round(data.total_amount / num_participants, 2)

        # 3. Create the Association records
        response_participants = []
        for p in data.participants:
            association = ExpenseUser(
                user_id=p.user_id,
                expense_id=new_expense.id,
                paid_amount=p.paid_amount,
                owed_amount=equal_share,  # Auto-calculated
            )
            db.add(association)

            # Prepare data for the response
            response_participants.append(
                {
                    "user_id": p.user_id,
                    "paid": p.paid_amount,
                    "owes": equal_share,
                    "net": round(p.paid_amount - equal_share, 2),
                }
            )

        db.commit()

        return {
            "message": "Expense created",
            "expense_id": new_expense.id,
            "details": response_participants,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/expenses/{expense_id}")
def update_expense(expense_id: int, data: ExpenseCreate, db: Session = Depends(get_db)):
    # 1. Find the existing expense
    db_expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not db_expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    try:
        # 2. Update the main Expense fields
        db_expense.description = data.description
        db_expense.total_amount = data.total_amount
        db_expense.group_id = data.group_id

        # 3. Delete ALL old participant records for this expense
        db.query(ExpenseUser).filter(ExpenseUser.expense_id == expense_id).delete()

        # 4. Recalculate the new equal share
        num_participants = len(data.participants)
        equal_share = round(data.total_amount / num_participants, 2)

        # Handle the 1-cent rounding difference (assign to the first payer)
        rounding_diff = round(data.total_amount - (equal_share * num_participants), 2)

        # 5. Re-insert the new participant data
        response_participants = []
        for i, p in enumerate(data.participants):
            # If there's a rounding diff (e.g., 0.01), add it to the first person's share
            current_owed = equal_share + (rounding_diff if i == 0 else 0)

            new_association = ExpenseUser(
                user_id=p.user_id,
                expense_id=expense_id,
                paid_amount=p.paid_amount,
                owed_amount=current_owed,
            )
            db.add(new_association)

            response_participants.append(
                {
                    "user_id": p.user_id,
                    "paid": p.paid_amount,
                    "owes": current_owed,
                    "net": round(p.paid_amount - current_owed, 2),
                }
            )

        db.commit()
        db.refresh(db_expense)

        return {
            "message": "Expense updated successfully",
            "details": response_participants,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


def get_payments(details):
    # 1. Separate and sort
    # Creditors: People who are owed money (Net > 0)
    creditors = sorted(
        [d for d in details if d["net"] > 0], key=lambda x: x["net"], reverse=True
    )
    # Debtors: People who owe money (Net < 0)
    debtors = sorted(
        [d for d in details if d["net"] < 0],
        key=lambda x: x["net"],  # Most negative first
    )

    payments = []

    # 2. Match Debtors to Creditors
    for d in debtors:
        d_amount_to_pay = abs(d["net"])

        for c in creditors:
            if d_amount_to_pay <= 0:
                break
            if c["net"] <= 0:
                continue

            # How much can this creditor take?
            settle_amount = min(d_amount_to_pay, c["net"])

            if settle_amount > 0:
                payments.append(
                    {
                        "from": d["user_id"],
                        "to": c["user_id"],
                        "amount": round(settle_amount, 2),
                    }
                )

                # Update the running balances
                d_amount_to_pay -= settle_amount
                c["net"] -= settle_amount

    return payments


@router.get("/expenses/{expense_id}")
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    # 1. Fetch Expense with User details
    expense = db.query(Expense).filter(Expense.id == expense_id).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    # 2. Prepare the participants list with Net Balances
    participants_list = []
    for assoc in expense.user_associations:
        net = round(assoc.paid_amount - assoc.owed_amount, 2)
        participants_list.append(
            {
                "user_id": assoc.user_id,
                "paid": assoc.paid_amount,
                "owes": assoc.owed_amount,
                "net": net,
            }
        )

    print(f"DEBUG: Participants: {participants_list}")
    settlements = get_payments([p.copy() for p in participants_list])
    print(f"DEBUG: Settlements: {settlements}")

    return {
        "expense_id": expense.id,
        "description": expense.description,
        "total_amount": expense.total_amount,
        "participants": participants_list,
        "settlements": settlements,
    }


@router.delete("/delete_expense/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    # 1. Fetch Expense
    expense = db.query(Expense).filter(Expense.id == expense_id).first()

    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    try:
        # 2. Delete all associated ExpenseUser records
        db.query(ExpenseUser).filter(ExpenseUser.expense_id == expense_id).delete()

        # 3. Delete the expense itself
        db.delete(expense)
        db.commit()

        return {"message": "Expense deleted successfully", "expense_id": expense_id}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
