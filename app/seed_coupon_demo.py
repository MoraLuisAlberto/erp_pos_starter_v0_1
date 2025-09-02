from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models.coupon import Coupon
from app.models.segment import Segment

s = SessionLocal()
# Asegura un segmento demo opcional
seg = s.query(Segment).filter_by(code="GEN").first()
if not seg:
    seg = Segment(code="GEN", name="General")
    s.add(seg)
    s.commit()

code = "SAVE10"
c = s.query(Coupon).filter_by(code=code).first()
if not c:
    c = Coupon(
        code=code,
        type="percent",
        value=10,
        min_amount=100,
        max_uses=100,
        used_count=0,
        valid_from=datetime.utcnow() - timedelta(days=1),
        valid_to=datetime.utcnow() + timedelta(days=30),
        valid_days_mask=127,  # todos los días (bits 0..6)
        valid_hours_json=None,
        segment_id=None,
        is_active=True,
    )
    s.add(c)
    s.commit()
print("Seed coupon:", code)
s.close()
