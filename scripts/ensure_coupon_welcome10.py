from sqlalchemy import text
from app.db import SessionLocal

s = SessionLocal()
code = "WELCOME10"

row = s.execute(
    text("SELECT id FROM coupon WHERE UPPER(code)=UPPER(:c)"),
    {"c": code}
).fetchone()

if row:
    s.execute(
        text("""
            UPDATE coupon
               SET is_active=1,
                   type='percent',
                   value=10,
                   valid_from=date('now'),
                   valid_to=date('now','+30 day'),
                   valid_days_mask=127,
                   valid_hours_json='[]'
             WHERE id=:id
        """),
        {"id": row[0]}
    )
else:
    s.execute(
        text("""
            INSERT INTO coupon
                (code,type,value,min_amount,max_uses,used_count,
                 valid_from,valid_to,valid_days_mask,valid_hours_json,
                 segment_id,is_active,created_at)
            VALUES
                (:c,'percent',10,0,NULL,0,
                 date('now'),date('now','+30 day'),127,'[]',
                 NULL,1,datetime('now'))
        """),
        {"c": code}
    )

s.commit()
print("COUPON_WELCOME10_OK")
s.close()
