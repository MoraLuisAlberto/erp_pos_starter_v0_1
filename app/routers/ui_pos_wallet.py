from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>POS · Monedero V1 (demo)</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:20px;line-height:1.35}
  h1{margin:0 0 8px 0}
  .row{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0}
  .card{border:1px solid #ddd;border-radius:10px;padding:14px;margin:10px 0;box-shadow:0 2px 6px rgba(0,0,0,.04)}
  label{font-weight:600}
  input,button,select{padding:8px 10px;border:1px solid #bbb;border-radius:8px}
  button{cursor:pointer}
  .ok{color:#0a7}
  .err{color:#b00}
  .muted{color:#666}
  code{background:#f6f6f6;border:1px solid #eee;border-radius:6px;padding:0 4px}
  .pill{display:inline-block;background:#eef;border:1px solid #ccd;border-radius:999px;padding:2px 8px;margin:0 4px}
  .mono{font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace}
</style>
</head>
<body>

<h1>POS · Monedero V1 (demo)</h1>
<div class="muted">Ruta: <code>/ui/pos-wallet</code>. Usa los endpoints actuales del backend.</div>

<div class="card">
  <h3>1) Sesión de caja</h3>
  <div class="row">
    <label>Store ID <input id="storeId" type="number" value="1" style="width:90px"></label>
    <label>Terminal ID <input id="termId" type="number" value="1" style="width:90px"></label>
    <button id="btnOpen">Abrir sesión</button>
    <div>SESSION_ID: <span id="sessionId" class="pill">—</span></div>
    <button id="btnResume">Resume</button>
    <div id="resumeInfo" class="muted mono"></div>
  </div>
</div>

<div class="card">
  <h3>2) Orden demo</h3>
  <div class="row">
    <label>Lista de precios <input id="priceList" type="number" value="1" style="width:90px"></label>
    <label>Producto <input id="prodId" type="number" value="1" style="width:90px"></label>
    <label>Cantidad <input id="qty" type="number" value="1" style="width:90px"></label>
    <button id="btnDraft">Crear borrador</button>
    <div>ORDER_ID: <span id="orderId" class="pill">—</span> Total: $<span id="orderTotal">0.00</span></div>
  </div>
  <div id="orderLines" class="muted mono"></div>
</div>

<div class="card">
  <h3>3) Monedero</h3>
  <div class="row">
    <label>Customer ID <input id="custId" type="number" value="1" style="width:90px"></label>
    <button id="btnLink">Vincular/crear monedero</button>
    <button id="btnBal">Consultar saldo</button>
    <button id="btnDep">Depositar $100 (demo)</button>
    <div>Saldo: $<span id="walletBal" class="pill">0.00</span></div>
  </div>
  <div class="row">
    <label><input type="checkbox" id="applyWallet" checked> Aplicar monedero al pagar</label>
    <span class="muted">Calcula monto con <code>POST /crm/wallet/apply-calc</code></span>
  </div>
</div>

<div class="card">
  <h3>4) Pago</h3>
  <div class="row">
    <button id="btnPay">Pagar</button>
    <span class="muted">Idempotencia: header <code>x-idempotency-key</code></span>
  </div>
  <div id="payOut" class="mono"></div>
</div>

<div class="card">
  <h3>5) Ticket / Splits</h3>
  <pre id="ticket" class="mono" style="white-space:pre-wrap"></pre>
</div>

<div class="card">
  <h3>6) Reporte diario (depósitos vs redenciones)</h3>
  <div class="row">
    <button id="btnDaily">Refrescar hoy</button>
    <div id="daily" class="mono"></div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s)
const fmt = n => Number(n||0).toFixed(2)
const key = () => 'ui-'+(crypto.randomUUID ? crypto.randomUUID() : (Date.now()+'-'+Math.random()))

let currentOrder = null

async function j(url, opts={}) {
  const res = await fetch(url, opts)
  const txt = await res.text()
  let data; try { data = txt ? JSON.parse(txt) : {} } catch { data = {raw:txt} }
  if (!res.ok) { throw {status:res.status, data} }
  return data
}
function headers(extra={}) {
  return Object.assign({'Content-Type':'application/json'}, extra)
}

// 1) Sesión
$('#btnOpen').onclick = async () => {
  try {
    const body = {
      store_id: Number($('#storeId').value||1),
      terminal_id: Number($('#termId').value||1),
      opening_cash: 0
    }
    const r = await j('/session/open', {method:'POST', headers:headers(), body:JSON.stringify(body)})
    $('#sessionId').textContent = r.id || r.session_id || r.id_session || '—'
    $('#resumeInfo').textContent = JSON.stringify(r)
  } catch (e) { alert('OPEN error: '+JSON.stringify(e.data||e)) }
}
$('#btnResume').onclick = async () => {
  try {
    const sid = $('#sessionId').textContent.trim()
    if (!sid || sid==='—') { alert('No hay SESSION_ID'); return }
    const r = await j(`/session/${sid}/resume`)
    $('#resumeInfo').textContent = JSON.stringify(r)
  } catch (e) { alert('RESUME error: '+JSON.stringify(e.data||e)) }
}

// 2) Borrador
$('#btnDraft').onclick = async () => {
  try {
    const sid = $('#sessionId').textContent.trim()
    if (!sid || sid==='—') { alert('Abre sesión primero'); return }
    const body = {
      session_id: Number(sid),
      price_list_id: Number($('#priceList').value||1),
      items: [{product_id:Number($('#prodId').value||1), qty:Number($('#qty').value||1)}]
    }
    const r = await j('/pos/order/draft', {method:'POST', headers:headers(), body:JSON.stringify(body)})
    currentOrder = r
    $('#orderId').textContent = r.order_id
    $('#orderTotal').textContent = fmt(r.total)
    $('#orderLines').textContent = JSON.stringify(r.lines||[])
  } catch (e) { alert('DRAFT error: '+JSON.stringify(e.data||e)) }
}

// 3) Monedero
$('#btnLink').onclick = async () => {
  try {
    const cid = Number($('#custId').value||1)
    const r = await j('/crm/wallet/link', {method:'POST', headers:headers(), body:JSON.stringify({customer_id:cid})})
    $('#walletBal').textContent = fmt(r.balance)
  } catch (e) { alert('LINK error: '+JSON.stringify(e.data||e)) }
}
$('#btnBal').onclick = async () => {
  try {
    const cid = Number($('#custId').value||1)
    const r = await j(`/crm/wallet/${cid}/balance`)
    $('#walletBal').textContent = fmt(r.balance)
  } catch (e) { alert('BALANCE error: '+JSON.stringify(e.data||e)) }
}
$('#btnDep').onclick = async () => {
  try {
    const cid = Number($('#custId').value||1)
    const r = await j('/crm/wallet/deposit', {
      method:'POST',
      headers:headers({'x-idempotency-key': key()}),
      body: JSON.stringify({customer_id:cid, amount:100, reason:'demo'})
    })
    $('#walletBal').textContent = fmt(r.balance)
  } catch (e) { alert('DEPOSIT error: '+JSON.stringify(e.data||e)) }
}

// 4) Pago (con cálculo de wallet opcional)
$('#btnPay').onclick = async () => {
  try {
    if (!currentOrder) { alert('Primero crea la orden'); return }
    const cid = Number($('#custId').value||1)
    let splits = []
    let total = Number(currentOrder.total||0)

    if ($('#applyWallet').checked) {
      const calc = await j('/crm/wallet/apply-calc', {
        method:'POST', headers:headers(),
        body: JSON.stringify({order_id: currentOrder.order_id, customer_id: cid})
      })
      const w = Number(calc.can_apply||0)
      const c = Number((total - w).toFixed(2))
      if (w > 0) splits.push({method:'wallet', amount:w})
      if (c > 0) splits.push({method:'cash', amount:c})
    } else {
      splits = [{method:'cash', amount: total}]
    }

    const pay = await j('/pos/order/pay', {
      method:'POST',
      headers: headers({'x-idempotency-key': key()}),
      body: JSON.stringify({order_id: currentOrder.order_id, splits})
    })

    $('#payOut').textContent = JSON.stringify(pay, null, 2)
    await refreshTicket(pay)
    // refresca saldo wallet
    const bal = await j(`/crm/wallet/${cid}/balance`)
    $('#walletBal').textContent = fmt(bal.balance)
  } catch (e) {
    $('#payOut').innerHTML = '<span class="err">ERROR</span> ' + JSON.stringify(e.data||e)
  }
}

async function refreshTicket(pay) {
  try {
    const order = pay.order || currentOrder
    let lines = (order.lines||[]).map(l => `• P${l.product_id}  x${l.qty}  $${fmt(l.line_total)}`).join('\\n')
    let splits = (pay.splits||[]).map(s => `  - ${s.method.toUpperCase()}: $${fmt(s.amount)}`).join('\\n')
    const txt =
`TICKET POS
Orden: ${order.order_no}  (ID ${order.order_id})
Estado: ${order.status}
--------------------------------
${lines}
--------------------------------
Subtotal: $${fmt(order.subtotal)}
Total:    $${fmt(order.total)}
Pago:
${splits || '  - CASH: $'+fmt(order.total)}
`
    $('#ticket').textContent = txt
  } catch (e) {
    $('#ticket').textContent = 'No disponible'
  }
}

// 6) Reporte diario
$('#btnDaily').onclick = async () => {
  try {
    const r = await j('/reports/wallet/daily')
    $('#daily').textContent = JSON.stringify(r)
  } catch (e) { alert('DAILY error: '+JSON.stringify(e.data||e)) }
}
</script>
</body>
</html>"""

@router.get("/ui/pos-wallet", response_class=HTMLResponse)
def ui_pos_wallet():
    return HTMLResponse(content=HTML)
