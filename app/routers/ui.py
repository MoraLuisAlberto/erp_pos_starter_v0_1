from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>POS UI (con Monedero)</title>
<style>
 body{font-family: system-ui, Segoe UI, Arial; margin:18px}
 h2{margin:18px 0 8px}
 fieldset{border:1px solid #ddd; padding:12px; border-radius:10px; margin-bottom:14px}
 label{display:inline-block; min-width:140px}
 input[type=number]{width:120px}
 .row{margin:6px 0}
 .ok{color:#0a7a0a}
 .err{color:#b30000}
 .pill{display:inline-block; padding:2px 8px; border-radius:999px; background:#eee; margin-left:8px}
 button{padding:6px 10px; border-radius:8px; border:1px solid #ccc; background:#f7f7f7; cursor:pointer}
 button:hover{background:#efefef}
 .muted{color:#666; font-size:12px}
 pre{background:#111; color:#ddd; padding:10px; border-radius:8px; overflow:auto; max-height:260px}
</style>
</head>
<body>
  <h1>POS Demo UI — Wallet</h1>

  <fieldset>
    <legend>1) Apertura de caja</legend>
    <div class="row"><label>Store ID</label><input id="store_id" type="number" value="1"/></div>
    <div class="row"><label>Terminal ID</label><input id="terminal_id" type="number" value="1"/></div>
    <div class="row"><label>Efectivo inicial</label><input id="opening_cash" type="number" value="0"/></div>
    <div class="row">
      <button onclick="openSession()">Abrir sesión</button>
      <span id="session_badge" class="pill">sin sesión</span>
    </div>
    <div class="muted">/session/open</div>
  </fieldset>

  <fieldset>
    <legend>2) Borrador de orden</legend>
    <div class="row"><label>Session ID</label><input id="session_id" type="number" value=""/></div>
    <div class="row"><label>Price List ID</label><input id="pricelist_id" type="number" value="1"/></div>
    <div class="row"><label>Product ID</label><input id="product_id" type="number" value="1"/></div>
    <div class="row"><label>Cantidad</label><input id="qty" type="number" value="1"/></div>
    <div class="row">
      <button onclick="createDraft()">Crear borrador</button>
      <span id="order_badge" class="pill">sin orden</span>
    </div>
    <div class="muted">/pos/order/draft</div>
  </fieldset>

  <fieldset>
    <legend>3) Monedero del cliente</legend>
    <div class="row"><label>Customer ID</label><input id="customer_id" type="number" value="1"/></div>
    <div class="row">
      <button onclick="linkWallet()">Vincular wallet / Mostrar saldo</button>
      <span id="wallet_badge" class="pill">saldo: -</span>
    </div>
    <div class="row">
      <label><input type="checkbox" id="apply_wallet" checked/> Aplicar monedero</label>
    </div>
    <div class="row">
      <button onclick="calcApply()">Calcular aplicar monedero</button>
      <span id="apply_badge" class="pill">aplica: -</span>
    </div>
    <div class="muted">/crm/wallet/link • /crm/wallet/{id}/balance • /crm/wallet/apply-calc</div>
  </fieldset>

  <fieldset>
    <legend>4) Cobro</legend>
    <div class="row"><label>Key idempotencia</label><input id="pay_key" value="ui-pay-001"/></div>
    <div class="row"><button onclick="pay()">Pagar</button></div>
    <div class="muted">/pos/order/pay (splits: wallet + cash)</div>
  </fieldset>

  <h2>Consola</h2>
  <pre id="log"></pre>

<script>
let SESSION_ID = null;
let ORDER = null;
let WALLET = { balance: 0 };
let CAN_APPLY = 0;

const port = 8010;              // backend
const base = `http://127.0.0.1:${port}`;
const U = (id) => document.getElementById(id);
const log = (m, cls="") => {
  const el = U("log");
  el.innerHTML = (cls ? "["+cls.toUpperCase()+"] " : "") + (typeof m==="string"? m: JSON.stringify(m,null,2)) + "\\n" + el.innerHTML;
};
const setText = (id, text) => U(id).innerText = text;

async function openSession(){
  try{
    const body = {
      store_id: parseInt(U("store_id").value||"1"),
      terminal_id: parseInt(U("terminal_id").value||"1"),
      opening_cash: parseFloat(U("opening_cash").value||"0")
    };
    // En tu app actual, la ruta viva es /session/open
    const r = await fetch(`${base}/session/open`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)
    });
    if(!r.ok){ throw new Error("open failed: "+r.status); }
    const data = await r.json();
    SESSION_ID = data.id || data.session_id || null;
    U("session_id").value = SESSION_ID || "";
    setText("session_badge", `session: ${SESSION_ID ?? "-"}`);
    log(data, "ok");
  }catch(e){ log(e.message||e, "err"); }
}

async function createDraft(){
  try{
    const sid = parseInt(U("session_id").value||"0");
    const pl = parseInt(U("pricelist_id").value||"1");
    const pid = parseInt(U("product_id").value||"1");
    const qty = parseFloat(U("qty").value||"1");
    if(!sid) throw new Error("Session ID requerido");

    const body = {
      session_id: sid,
      price_list_id: pl,
      items: [{ product_id: pid, qty: qty }]
    };
    const r = await fetch(`${base}/pos/order/draft`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)
    });
    if(!r.ok){ 
      const t = await r.text(); 
      throw new Error("draft failed: "+r.status+" -> "+t); 
    }
    const data = await r.json();
    ORDER = data;
    setText("order_badge", `orden: ${ORDER.order_id ?? "-" } total: ${ORDER.total ?? "-"}`);
    log(data, "ok");
  }catch(e){ log(e.message||e, "err"); }
}

async function linkWallet(){
  try{
    const cid = parseInt(U("customer_id").value||"0");
    if(!cid) throw new Error("Customer ID requerido");
    const r = await fetch(`${base}/crm/wallet/link`, {
      method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({customer_id: cid})
    });
    if(!r.ok){ throw new Error("link failed: "+r.status); }
    WALLET = await r.json();
    setText("wallet_badge", `saldo: ${(+WALLET.balance).toFixed(2)}`);
    log(WALLET, "ok");
  }catch(e){ log(e.message||e, "err"); }
}

async function calcApply(){
  try{
    const cid = parseInt(U("customer_id").value||"0");
    const oid = ORDER?.order_id;
    if(!oid) throw new Error("No hay orden");
    const r = await fetch(`${base}/crm/wallet/apply-calc`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ order_id: oid, customer_id: cid })
    });
    if(!r.ok){ throw new Error("calc failed: "+r.status); }
    const data = await r.json();
    CAN_APPLY = +data.can_apply || 0;
    setText("apply_badge", `aplica: ${CAN_APPLY.toFixed(2)}`);
    log(data, "ok");
  }catch(e){ log(e.message||e, "err"); }
}

async function pay(){
  try{
    if(!ORDER?.order_id) throw new Error("Sin orden");
    const total = +ORDER.total || 0;
    let splits = [];
    const useWallet = U("apply_wallet").checked;
    let walletPart = 0;

    if(useWallet){
      // si no se calculó aún, calcula a demanda
      if(!CAN_APPLY){ await calcApply(); }
      walletPart = Math.min(CAN_APPLY || 0, total);
      if(walletPart > 0){
        splits.push({ method: "wallet", amount: +walletPart.toFixed(2) });
      }
    }
    const cash = +(total - walletPart).toFixed(2);
    if(cash > 0){ splits.push({ method: "cash", amount: cash }); }

    if(splits.length === 0){ throw new Error("No hay splits para pagar"); }

    const key = U("pay_key").value || ("ui-pay-"+Date.now());
    const r = await fetch(`${base}/pos/order/pay`, {
      method:"POST",
      headers: { "Content-Type": "application/json", "x-idempotency-key": key },
      body: JSON.stringify({ order_id: ORDER.order_id, splits })
    });
    if(!r.ok){ 
      const t = await r.text();
      throw new Error("pay failed: "+r.status+" -> "+t); 
    }
    const data = await r.json();
    log(data, "ok");

    // refresca saldo si procede
    if(U("apply_wallet").checked){
      const cid = parseInt(U("customer_id").value||"0");
      const rb = await fetch(`${base}/crm/wallet/${cid}/balance`);
      if(rb.ok){
        const wb = await rb.json();
        setText("wallet_badge", `saldo: ${(+wb.balance).toFixed(2)}`);
        log({wallet_balance: wb.balance}, "ok");
      }
    }
  }catch(e){ log(e.message||e, "err"); }
}
</script>
</body>
</html>
"""
