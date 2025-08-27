from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, UniqueConstraint
from datetime import datetime
from ..db import Base

class StockLocation(Base):
    __tablename__ = "stock_location"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)

class StockQuant(Base):
    __tablename__ = "stock_quant"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("stock_location.id"), nullable=False)
    qty_on_hand = Column(Numeric(12,3), default=0)
    qty_reserved = Column(Numeric(12,3), default=0)
    __table_args__ = (UniqueConstraint("product_id","location_id", name="uq_quant"),)

class StockMove(Base):
    __tablename__ = "stock_move"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    location_id_from = Column(Integer, ForeignKey("stock_location.id"))
    location_id_to = Column(Integer, ForeignKey("stock_location.id"))
    qty = Column(Numeric(12,3), nullable=False)
    reason = Column(String)            # e.g. 'sale'
    ref_type = Column(String)          # 'pos_order'
    ref_id = Column(String)            # order_id
    at = Column(DateTime, default=datetime.utcnow)
    by_user = Column(String)
