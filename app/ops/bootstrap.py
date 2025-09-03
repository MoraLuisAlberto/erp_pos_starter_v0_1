# app/ops/bootstrap.py
from __future__ import annotations

import os
import sys
import datetime as dt
from typing import Dict, Any, Iterable, Optional, Set


def _load_engine_and_base():
    """Carga Base/engine desde ubicaciones comunes. Fallback a DATABASE_URL."""
    try:
        from app.core.db import Base as _B, engine as _E, SessionLocal as _S  # type: ignore

        return _B, _E, _S
    except Exception:
        pass
    try:
        from app.db import Base as _B, engine as _E, SessionLocal as _S  # type: ignore

        return _B, _E, _S
    except Exception:
        pass

    from sqlalchemy import create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker

    url = os.getenv("DATABASE_URL", "sqlite:///./erp.db")
    engine = create_engine(url, future=True)
    Base = declarative_base()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    print(f"[bootstrap] Fallback engine via DATABASE_URL={url}.")
    return Base, engine, SessionLocal


def _metadata_create_all(Base, engine):
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        Base.metadata.create_all(bind=engine)
        print("[bootstrap] metadata.create_all completed.")
    except Exception as e:
        print(f"[bootstrap] metadata.create_all skipped: {e!r}")


def _ensure_row(conn, table: str, prefer_id: int, label: str):
    """Inserta una fila mínima si es posible (id/name/code/flags/timestamps). Idempotente."""
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    try:
        if table not in insp.get_table_names():
            print(f"[bootstrap] Table '{table}' not found; skip.")
            return
    except Exception:
        print(f"[bootstrap] Could not inspect table list; skip '{table}'.")
        return

    cols = insp.get_columns(table)
    names = [c["name"] for c in cols]

    now = dt.datetime.utcnow().isoformat(timespec="seconds")
    values: Dict[str, Any] = {}
    if "id" in names:
        values["id"] = prefer_id
    if "name" in names:
        values["name"] = f"Default {label}"
    if "code" in names:
        values["code"] = f"{label.upper()}1"
    for flag in ("is_active", "active", "enabled"):
        if flag in names:
            values[flag] = 1
            break
    for ts in ("created_at", "updated_at", "created_on", "updated_on"):
        if ts in names:
            values[ts] = now

    if not values:
        print(f"[bootstrap] No insertable columns for '{table}'; skip.")
        return

    cols_sql = ", ".join(values.keys())
    params_sql = ", ".join(f":{k}" for k in values.keys())
    sql = f"INSERT OR IGNORE INTO {table} ({cols_sql}) VALUES ({params_sql});"
    try:
        conn.exec_driver_sql(sql, values)
        print(f"[bootstrap] Ensured minimal row in '{table}' => {values}")
    except Exception as e:
        print(f"[bootstrap] Insert into '{table}' failed but ignored: {e!r}")


def _pragmas(conn, table: str) -> Dict[str, Any]:
    """PRAGMA table_info / foreign_key_list para SQLite."""
    cols = [dict(row) for row in conn.exec_driver_sql(f"PRAGMA table_info('{table}')")]
    fks = [dict(row) for row in conn.exec_driver_sql(f"PRAGMA foreign_key_list('{table}')")]
    return {"cols": cols, "fks": fks}


def _detect_parents(conn, tables: Iterable[str]) -> Dict[str, Set[str]]:
    """
    Devuelve mapping {'pos': {parent_table}, 'cashier': {parent_table}} detectando FKs
    con variedad de nombres de columna (sinónimos comunes en POS).
    """
    POS_FK_COLS = {
        "pos_id",
        "pos",
        "pos_fk",
        "terminal_id",
        "device_id",
        "register_id",
        "pos_device_id",
        "pos_register_id",
    }
    CASHIER_FK_COLS = {
        "cashier_id",
        "user_id",
        "employee_id",
        "operator_id",
        "opened_by",
        "opened_by_id",
        "staff_id",
        "account_id",
    }

    parents = {"pos": set(), "cashier": set()}
    for t in tables:
        meta = _pragmas(conn, t)
        fk_list = meta["fks"]
        for fk in fk_list:
            from_col = str(fk.get("from"))
            parent_tbl = str(fk.get("table"))
            if from_col in POS_FK_COLS:
                parents["pos"].add(parent_tbl)
            if from_col in CASHIER_FK_COLS:
                parents["cashier"].add(parent_tbl)
    return parents


def main():
    Base, engine, SessionLocal = _load_engine_and_base()
    _metadata_create_all(Base, engine)

    from sqlalchemy import inspect

    with engine.begin() as conn:
        insp = inspect(conn)
        try:
            tables = insp.get_table_names()
        except Exception:
            tables = []

        # 1) Detecta tablas padre reales por FKs (amplio set de sinónimos)
        detected = _detect_parents(conn, tables)

        # 2) Fallbacks por nombre de tabla
        POS_TABLE_FALLBACKS = [
            "pos",
            "pos_device",
            "pos_register",
            "point_of_sale",
            "points_of_sale",
            "terminal",
            "device",
            "register",
        ]
        CASHIER_TABLE_FALLBACKS = [
            "cashier",
            "cashiers",
            "user",
            "users",
            "employee",
            "employees",
            "operator",
            "operators",
            "staff",
            "account",
            "accounts",
            "user_account",
            "user_accounts",
        ]

        pos_parents = list(detected["pos"]) or [t for t in POS_TABLE_FALLBACKS if t in tables]
        cashier_parents = list(detected["cashier"]) or [
            t for t in CASHIER_TABLE_FALLBACKS if t in tables
        ]

        if not pos_parents:
            print("[bootstrap] No parent table detected for POS; tried FKs and fallbacks.")
        else:
            _ensure_row(conn, pos_parents[0], prefer_id=1, label="POS")

        if not cashier_parents:
            print("[bootstrap] No parent table detected for Cashier; tried FKs and fallbacks.")
        else:
            _ensure_row(conn, cashier_parents[0], prefer_id=1, label="Cashier")

        # 3) Extras seguros por si otros seeds los requieren
        for candidate in ("customer", "customers"):
            if candidate in tables:
                _ensure_row(conn, candidate, prefer_id=1, label="Customer")
                break

        for candidate in ("segment", "segments"):
            if candidate in tables:
                _ensure_row(conn, candidate, prefer_id=1, label="GEN")
                break

        for candidate in ("coupon", "coupons"):
            if candidate in tables:
                _ensure_row(conn, candidate, prefer_id=1, label="TEST10")
                break

    print("[bootstrap] Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[bootstrap] Non-fatal error: {e!r}")
        sys.exit(0)
