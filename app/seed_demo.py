from decimal import Decimal

from sqlalchemy.orm import Session

from .db import Base, SessionLocal, engine
from .models.pos import CashDenomination
from .models.product import PriceList, PriceListItem, Product, ProductBarcode
from .models.stock import StockLocation, StockQuant


def get_or_create(session: Session, model, defaults=None, **kwargs):
    inst = session.query(model).filter_by(**kwargs).first()
    if inst:
        return inst, False
    params = dict(kwargs)
    if defaults:
        params.update(defaults)
    inst = model(**params)
    session.add(inst)
    session.commit()
    session.refresh(inst)
    return inst, True


def main():
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    try:
        # Producto demo
        prod, _ = get_or_create(
            db,
            Product,
            sku="LAB-001",
            name="Labial Mate",
            barcode_main="7501234567890",
            uom="unit",
            is_active=True,
        )
        get_or_create(db, ProductBarcode, product_id=prod.id, barcode="LAB001ALT")

        # Lista de precios BASE
        pl, _ = get_or_create(db, PriceList, name="PL Base", currency="MXN", is_active=True)
        get_or_create(
            db, PriceListItem, price_list_id=pl.id, product_id=prod.id, price=Decimal("129.00")
        )

        # Stock inicial
        loc, _ = get_or_create(
            db, StockLocation, code="MAIN", name="Almacén Principal", is_active=True
        )
        get_or_create(
            db,
            StockQuant,
            product_id=prod.id,
            location_id=loc.id,
            qty_on_hand=Decimal("100"),
            qty_reserved=Decimal("0"),
        )

        # Denominaciones MXN
        for v in [1000, 500, 200, 100, 50, 20, 10, 5, 2, 1]:
            get_or_create(db, CashDenomination, currency="MXN", value=Decimal(str(v)))

        print(
            f"Seed OK | product_id={prod.id} barcode=7501234567890 price_list_id={pl.id} location=MAIN"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
