Fecha: 2025-09-01
Fase / módulo: POS / Cupones
Avance: Unificación de CouponValidateRequest; construcción única de at_dt en validate_coupon; validación WEEKEND15 (weekdays/days_mask) usando at_dt; NITE20 sin cambios.
Código / evidencias: diff en app/routers/pos_coupons.py; py_compile OK; tests time_windows_extra_edges y coupon_rules_matrix en verde.
Próximos pasos: test dedicado WEEKEND15 (sáb/dom); verificar auditoría en _AUDIT_FILE; limpiar snippets legacy si quedara alguno.
