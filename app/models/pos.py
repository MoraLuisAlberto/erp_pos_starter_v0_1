from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint

from ..db import Base


class PosDay(Base):
    __tablename__ = "pos_day"
    id = Column(Integer, primary_key=True)
    business_date = Column(DateTime, nullable=False)
    store_id = Column(String, nullable=False)
    status = Column(String, default="open")  # open | closed
    __table_args__ = (UniqueConstraint("store_id", "business_date", name="uq_store_day"),)


class PosSession(Base):
    __tablename__ = "pos_session"
    id = Column(Integer, primary_key=True)
    store_id = Column(String, nullable=False)
    terminal_id = Column(String, nullable=False)
    user_open_id = Column(String, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="open")  # open | pre_close | closed
    user_close_id = Column(String)
    closed_at = Column(DateTime)
    idempotency_open = Column(String, unique=True)
    idempotency_close = Column(String, unique=True)
    audit_ref = Column(String)


class CashDenomination(Base):
    __tablename__ = "cash_denominations"
    id = Column(Integer, primary_key=True)
    currency = Column(String, default="MXN")
    value = Column(Numeric(12, 2), nullable=False)


class CashCount(Base):
    __tablename__ = "cash_count"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("pos_session.id"), nullable=False)
    stage = Column(String, nullable=False)  # open | pre_close | close
    created_at = Column(DateTime, default=datetime.utcnow)
    by_user = Column(String)


class CashCountLine(Base):
    __tablename__ = "cash_count_line"
    id = Column(Integer, primary_key=True)
    cash_count_id = Column(Integer, ForeignKey("cash_count.id"), nullable=False)
    denomination_id = Column(Integer, ForeignKey("cash_denominations.id"), nullable=False)
    units = Column(Integer, default=0)
    subtotal = Column(Numeric(12, 2), default=0)
    __table_args__ = (UniqueConstraint("cash_count_id", "denomination_id", name="uq_count_line"),)


class PosOrder(Base):
    __tablename__ = "pos_order"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("pos_session.id"), nullable=False)
    order_no = Column(String, unique=True, index=True)
    business_date = Column(DateTime, default=datetime.utcnow)
    customer_id = Column(Integer, ForeignKey("customer.id"))
    price_list_id = Column(Integer, ForeignKey("price_list.id"), nullable=False)
    subtotal = Column(Numeric(12, 2), default=0)
    discount_total = Column(Numeric(12, 2), default=0)
    tax_total = Column(Numeric(12, 2), default=0)
    total = Column(Numeric(12, 2), default=0)
    status = Column(String, default="draft")  # draft | paid | voided
    undo_until_at = Column(DateTime)
    idempotency_key = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PosOrderLine(Base):
    __tablename__ = "pos_order_line"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("pos_order.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    qty = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    discount = Column(Numeric(12, 2), default=0)
    line_total = Column(Numeric(12, 2), default=0)


class PosOrderCoupon(Base):
    __tablename__ = "pos_order_coupon"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("pos_order.id"), nullable=False)
    coupon_id = Column(Integer, ForeignKey("coupon.id"))
    code_snapshot = Column(String)
    value_applied = Column(Numeric(12, 2), default=0)


class PosPayment(Base):
    __tablename__ = "pos_payment"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("pos_order.id"), nullable=False)
    method = Column(String, nullable=False)  # cash | card | mixed
    amount = Column(Numeric(12, 2), nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow)
    idempotency_key = Column(String, unique=True, index=True)
    ref_ext = Column(String)
    by_user = Column(String)


class PosPaymentSplit(Base):
    __tablename__ = "pos_payment_split"
    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("pos_payment.id"), nullable=False)
    method = Column(String, nullable=False)  # cash | card
    amount = Column(Numeric(12, 2), nullable=False)
