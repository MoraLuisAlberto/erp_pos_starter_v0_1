from fastapi import APIRouter
from sqlalchemy import text

from ..db import SessionLocal

router = APIRouter()


def _has_col(rows, name: str) -> bool:
    return any(r[1] == name for r in rows)


@router.get("/stats/today")
def stats_today():
    s = SessionLocal()
    try:
        # detectar columnas de tiempo
        pp_cols = s.execute(text("PRAGMA table_info(pos_payment)")).fetchall()
        po_cols = s.execute(text("PRAGMA table_info(pos_order)")).fetchall()
        has_pp_created = _has_col(pp_cols, "created_at") or _has_col(pp_cols, "at")
        has_po_paid = _has_col(po_cols, "paid_at")

        date_col = (
            "created_at"
            if _has_col(pp_cols, "created_at")
            else ("at" if _has_col(pp_cols, "at") else None)
        )
        where_date = ""
        date_filter_applied = False
        if has_pp_created and date_col:
            where_date = f" WHERE DATE(p.{date_col}) = DATE('now','localtime')"
            date_filter_applied = True
        elif has_po_paid:
            where_date = " WHERE DATE(o.paid_at) = DATE('now','localtime')"
            date_filter_applied = True

        # base por pagos (1 pago por orden en nuestro flujo)
        sql_base = f"""
            SELECT COALESCE(SUM(p.amount),0) as total, COUNT(p.id) as cnt
            FROM pos_payment p
            {"JOIN pos_order o ON o.id=p.order_id" if where_date and "o." in where_date else ""}
            {where_date}
        """
        row = s.execute(text(sql_base)).fetchone()
        total = float(row[0] or 0.0)
        cnt = int(row[1] or 0)

        # por método
        sql_by = f"""
            SELECT p.method, COALESCE(SUM(p.amount),0) as total
            FROM pos_payment p
            {"JOIN pos_order o ON o.id=p.order_id" if where_date and "o." in where_date else ""}
            {where_date}
            GROUP BY p.method
        """
        rows = s.execute(text(sql_by)).fetchall()
        by_method = [{"method": r[0] or "unknown", "amount": float(r[1] or 0.0)} for r in rows]

        avg_ticket = round(total / cnt, 2) if cnt > 0 else 0.0
        return {
            "date": s.execute(text("SELECT DATE('now','localtime')")).scalar(),
            "date_filter_applied": date_filter_applied,
            "sales_count": cnt,
            "gross_total": round(total, 2),
            "avg_ticket": avg_ticket,
            "by_method": by_method,
        }
    finally:
        s.close()
