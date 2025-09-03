from sqlalchemy import Column, ForeignKey, Integer, String

from ..db import Base


class Customer(Base):
    __tablename__ = "customer"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=True)
    email = Column(String(120), nullable=True)
    phone = Column(String(40), nullable=True)
    segment_id = Column(Integer, ForeignKey("segment.id"), nullable=True)
