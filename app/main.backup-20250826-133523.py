from fastapi import FastAPI

from app.middleware.pay_audit import install_pay_audit
from app.routers import (
    coupon,
    health,
    pos_coupons,
    pos_orders_min,
    pos_payx,
    reports_coupons,
    reports_coupons_audit,
    session,
    ui,
    ui_pos_wallet,
)

from .db import Base, engine

# IMPORTA MODELOS antes de create_all

# Crea tablas faltantes (desarrollo)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ERP POS")


app.include_router(crm_wallet.router)
app.include_router(reports_wallet.router)
app.include_router(pos_orders_min.router)
app.include_router(health.router)
app.include_router(coupon.router)
app.include_router(ui.router)
app.include_router(ui_pos_wallet.router)
app.include_router(session.router)
install_pay_audit(app)
app.include_router(reports_coupons_audit.router)
app.include_router(reports_coupons.router)
app.include_router(pos_payx.router)
app.include_router(pos_coupons.router)
# Salud
