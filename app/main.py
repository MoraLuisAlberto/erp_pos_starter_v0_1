from app.routers import ui_pos_wallet
from app.routers import session
from app.routers import coupon
from fastapi import FastAPI
from app.routers import crm_wallet
from app.routers import wallet
from app.middleware.idempotency import install_idempotency
from app.routers import pos_orders_min
from app.routers import ui
from app.middleware.pay_audit import install_pay_audit
from app.routers import reports_coupons_audit
from app.routers import reports_coupons
from app.routers import pos_payx
from app.routers import pos_coupons
from app.routers import health
from .db import Base, engine

# IMPORTA MODELOS antes de create_all
from .models import product as _product_models
from .models import pos as _pos_models
from .models import coupon as _coupon_models
from .models import segment as _segment_models
from .models import pos_session as _pos_session_models
from .models import customer as _customer_models

# Crea tablas faltantes (desarrollo)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ERP POS")



app.include_router(crm_wallet.router)
app.include_router(wallet.router)
install_idempotency(app)
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
















