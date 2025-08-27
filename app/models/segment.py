from sqlalchemy import Column, Integer, String
from ..db import Base

class Segment(Base):
    __tablename__ = "segment"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
