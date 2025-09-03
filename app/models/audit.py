from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from ..db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String)
    session_id = Column(Integer, ForeignKey("pos_session.id"))
    entity = Column(String)
    entity_id = Column(String)
    action = Column(String)
    payload_json = Column(String)
    ip = Column(String)
