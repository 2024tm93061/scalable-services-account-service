import os
import csv
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, condecimal
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    create_engine,
    func,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./accounts.db")
DAILY_LIMIT = float(os.environ.get("DAILY_TRANSFER_LIMIT", "200000"))

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, unique=True, index=True)
    customer_id = Column(Integer, index=True)
    account_number = Column(String, unique=True)
    account_type = Column(String)
    balance = Column(Float, default=0.0)
    currency = Column(String, default="INR")
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    # read-optimized projection: we store a simple customer_name
    customer_name = Column(String, default=None)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    from_account = Column(Integer, ForeignKey("accounts.account_id"), nullable=False)
    to_account = Column(Integer, ForeignKey("accounts.account_id"), nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Account Service", version="0.1")


class CreateAccountRequest(BaseModel):
    customer_id: int
    account_number: str
    account_type: Optional[str] = "SAVINGS"
    initial_balance: Optional[condecimal(max_digits=20, decimal_places=2)] = 0.0
    currency: Optional[str] = "INR"
    customer_name: Optional[str] = None


class StatusChangeRequest(BaseModel):
    status: str


class TransferRequest(BaseModel):
    from_account: int
    to_account: int
    amount: condecimal(gt=0, max_digits=20, decimal_places=2)


def seed_from_csv(csv_path: str = "accounts.csv"):
    if not os.path.exists(csv_path):
        return
    db = SessionLocal()
    try:
        # only seed if accounts table empty
        existing = db.query(Account).first()
        if existing:
            return

        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    acct = Account(
                        account_id=int(row.get("account_id")),
                        customer_id=int(row.get("customer_id") or 0),
                        account_number=row.get("account_number"),
                        account_type=row.get("account_type"),
                        balance=float(row.get("balance") or 0.0),
                        currency=row.get("currency") or "INR",
                        status=row.get("status") or "ACTIVE",
                        created_at=datetime.strptime(row.get("created_at"), "%Y-%m-%d %H:%M:%S"),
                        customer_name=row.get("customer_name") or f"Customer {row.get('customer_id')}",
                    )
                except Exception:
                    # fallback: create with minimal fields
                    acct = Account(
                        account_id=int(row.get("account_id")),
                        customer_id=int(row.get("customer_id") or 0),
                        account_number=row.get("account_number"),
                        balance=float(row.get("balance") or 0.0),
                        currency=row.get("currency") or "INR",
                        status=row.get("status") or "ACTIVE",
                        customer_name=f"Customer {row.get('customer_id')}",
                    )
                db.add(acct)
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    # Seed DB from provided CSV if empty
    seed_from_csv(os.path.join(os.getcwd(), "accounts.csv"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/accounts")
def create_account(req: CreateAccountRequest):
    db = SessionLocal()
    try:
        # simple account_id generator (max +1) if not provided
        max_id = db.query(func.max(Account.account_id)).scalar() or 0
        account_id = int(max_id) + 1
        acc = Account(
            account_id=account_id,
            customer_id=req.customer_id,
            account_number=req.account_number,
            account_type=req.account_type,
            balance=float(req.initial_balance),
            currency=req.currency,
            status="ACTIVE",
            customer_name=req.customer_name or f"Customer {req.customer_id}",
            created_at=datetime.utcnow(),
        )
        db.add(acc)
        db.commit()
        db.refresh(acc)
        return {"account_id": acc.account_id, "balance": acc.balance}
    finally:
        db.close()


@app.get("/accounts/{account_id}")
def get_account(account_id: int):
    db = SessionLocal()
    try:
        acc = db.query(Account).filter(Account.account_id == account_id).first()
        if not acc:
            raise HTTPException(status_code=404, detail="account not found")
        return {
            "account_id": acc.account_id,
            "customer_id": acc.customer_id,
            "account_number": acc.account_number,
            "balance": acc.balance,
            "currency": acc.currency,
            "status": acc.status,
            "customer_name": acc.customer_name,
        }
    finally:
        db.close()


@app.post("/accounts/{account_id}/status")
def change_status(account_id: int, req: StatusChangeRequest):
    db = SessionLocal()
    try:
        acc = db.query(Account).filter(Account.account_id == account_id).first()
        if not acc:
            raise HTTPException(status_code=404, detail="account not found")
        acc.status = req.status.upper()
        db.add(acc)
        db.commit()
        return {"account_id": acc.account_id, "status": acc.status}
    finally:
        db.close()


def todays_transferred_sum(db, from_account_id: int) -> float:
    # sum of amounts sent by account today (UTC)
    start = datetime.combine(date.today(), datetime.min.time())
    end = datetime.combine(date.today(), datetime.max.time())
    s = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0.0))
        .filter(Transaction.from_account == from_account_id)
        .filter(Transaction.created_at >= start)
        .filter(Transaction.created_at <= end)
        .scalar()
    )
    return float(s or 0.0)


@app.post("/transfer")
def transfer(req: TransferRequest):
    db = SessionLocal()
    try:
        if req.from_account == req.to_account:
            raise HTTPException(status_code=400, detail="from_account and to_account must differ")

        src = db.query(Account).filter(Account.account_id == req.from_account).with_for_update().first()
        dst = db.query(Account).filter(Account.account_id == req.to_account).with_for_update().first()

        if not src or not dst:
            raise HTTPException(status_code=404, detail="source or destination account not found")

        if src.status != "ACTIVE":
            raise HTTPException(status_code=400, detail=f"source account status '{src.status}' cannot transact")
        if dst.status != "ACTIVE":
            raise HTTPException(status_code=400, detail=f"destination account status '{dst.status}' cannot receive funds")

        amt = float(req.amount)
        if src.balance < amt:
            raise HTTPException(status_code=400, detail="insufficient funds")

        transferred_today = todays_transferred_sum(db, req.from_account)
        if transferred_today + amt > DAILY_LIMIT:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"daily transfer limit exceeded: limit={DAILY_LIMIT}, already_transferred_today={transferred_today}, "
                    f"attempting={amt}"
                ),
            )

        # perform transfer atomically
        try:
            src.balance = src.balance - amt
            dst.balance = dst.balance + amt
            tx = Transaction(from_account=req.from_account, to_account=req.to_account, amount=amt)
            db.add(src)
            db.add(dst)
            db.add(tx)
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"transfer failed: {e}")

        return {"from_account": src.account_id, "to_account": dst.account_id, "amount": amt}
    finally:
        db.close()
