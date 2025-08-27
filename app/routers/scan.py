from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models.product import Product, ProductBarcode, PriceList, PriceListItem

router = APIRouter()

@router.get("/{barcode}")
def scan_barcode(barcode: str, price_list_id: int | None = None):
    db: Session = SessionLocal()
    try:
        p = db.query(Product).filter(Product.barcode == barcode).first()
        if not p:
            alt = db.query(ProductBarcode).filter(ProductBarcode.code == barcode).first()
            if alt:
                p = db.get(Product, alt.product_id)
        if not p:
            raise HTTPException(status_code=404, detail="Producto no encontrado")

        # Precio (por lista si se indica; si no, toma la primera)
        if price_list_id is None:
            pl = db.query(PriceList).first()
            price_list_id = pl.id if pl else None

        price = None
        if price_list_id is not None:
            pli = db.query(PriceListItem).filter_by(price_list_id=price_list_id, product_id=p.id).first()
            if pli:
                price = float(pli.price)

        return {
            "product_id": p.id,
            "name": p.name,
            "barcode": p.barcode,
            "uom": p.uom,
            "price_list_id": price_list_id,
            "price": price
        }
    finally:
        db.close()
