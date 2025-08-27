from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text
from datetime import datetime
from ..db import Base

class PosSession(Base):
    __tablename__ = "pos_session"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(20), default="open")  # open|closed
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    opened_by = Column(String(60), nullable=True)
    closed_by = Column(String(60), nullable=True)
    note = Column(String(255), nullable=True)

    expected_cash = Column(Numeric(12,2), default=0)
    counted_pre = Column(Numeric(12,2), default=0)
    counted_final = Column(Numeric(12,2), default=0)
    diff_cash = Column(Numeric(12,2), default=0)
    tolerance = Column(Numeric(12,2), default=0)

    idem_open = Column(String(80), unique=True, nullable=True)
    idem_close = Column(String(80), unique=True, nullable=True)

    # NUEVO: tienda obligatoria (default 1)
    store_id = Column(Integer, nullable=False, default=1, index=True)

class CashCount(Base):
    __tablename__ = "cash_count"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=False)
    kind = Column(String(10), nullable=False)     # 'pre' | 'final'
    total = Column(Numeric(12,2), default=0)
    details_json = Column(Text, nullable=True)
    at = Column(DateTime, default=datetime.utcnow)
    by_user = Column(String(60), nullable=True)
