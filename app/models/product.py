from sqlalchemy import Column, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import relationship

from ..db import Base


class Product(Base):
    __tablename__ = "product"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    barcode = Column(
        String(50), unique=True, index=True, nullable=True
    )  # barcode principal opcional
    uom = Column(String(20), default="unit")

    barcodes = relationship(
        "ProductBarcode", back_populates="product", cascade="all, delete-orphan"
    )


class ProductBarcode(Base):
    __tablename__ = "product_barcode"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=False)

    product = relationship("Product", back_populates="barcodes")


# Listas de precio
class PriceList(Base):
    __tablename__ = "price_list"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), nullable=False)


class PriceListItem(Base):
    __tablename__ = "price_list_item"
    id = Column(Integer, primary_key=True, index=True)
    price_list_id = Column(Integer, ForeignKey("price_list.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    __table_args__ = (Index("ix_plitem_plid_prod", "price_list_id", "product_id", unique=True),)

    product = relationship("Product")
    price_list = relationship("PriceList")
