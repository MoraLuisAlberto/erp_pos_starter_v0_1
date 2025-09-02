from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String

from ..db import Base


class Coupon(Base):
    __tablename__ = "coupon"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True, nullable=False)
    type = Column(String, nullable=False)  # 'percent' | 'fixed'
    value = Column(Numeric(12, 2), nullable=False)
    min_amount = Column(Numeric(12, 2))
    max_uses = Column(Integer)
    used_count = Column(Integer, default=0)
    valid_from = Column(DateTime)
    valid_to = Column(DateTime)
    valid_days_mask = Column(Integer)  # bits 0..6 (lun..dom)
    valid_hours_json = Column(String)  # JSON con franjas
    segment_id = Column(Integer, ForeignKey("segment.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CouponAudit(Base):
    __tablename__ = "coupon_audit"
    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("coupon.id"), nullable=False)
    event = Column(String, nullable=False)
    at = Column(DateTime, default=datetime.utcnow)
    by_user = Column(String)
    notes = Column(String)
