from sqlalchemy import text


def mark_coupons_used(db, order_id: int, by_user: str = "pos"):
    """
    Idempotente: por cada cupón ligado a la orden crea rastro en coupon_audit
    (event='used', notes='order:<id>'). Si el INSERT OR IGNORE inserta,
    entonces suma +1 en coupon.used_count. Si ya existía, no duplica.
    """
    rows = db.execute(
        text("SELECT coupon_id FROM pos_order_coupon WHERE order_id = :oid"), {"oid": order_id}
    ).fetchall()

    for (coupon_id,) in rows:
        notes = f"order:{order_id}"
        ins = db.execute(
            text(
                """
                INSERT OR IGNORE INTO coupon_audit (coupon_id, event, at, by_user, notes)
                VALUES (:cid, 'used', datetime('now'), :usr, :nts)
            """
            ),
            {"cid": coupon_id, "usr": by_user, "nts": notes},
        )
        if ins.rowcount and ins.rowcount > 0:
            db.execute(
                text("UPDATE coupon SET used_count = COALESCE(used_count,0) + 1 WHERE id = :cid"),
                {"cid": coupon_id},
            )
    # commit lo hace el caller (router de pago)
