const API = (path)=>path.startsWith("http")?path:`${location.origin}${path}`;
let CART = [];         // {product_id, name, qty, unit_price}
let LAST_ORDER = null; // {order_id,total,status,undo_until_at?}

function money(n){ return (n??0).toFixed(2); }
function idem(prefix){ return `${prefix}-${Date.now()}`; }

function renderCart(){
  const tb = document.querySelector("#cartTbl tbody");
  tb.innerHTML = "";
  let subtotal = 0;
  CART.forEach((l,idx)=>{
    const lineTotal = (l.qty||0) * (l.unit_price||0);
    subtotal += lineTotal;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${l.name}</td>
      <td><input type="number" min="0.001" step="0.001" value="${l.qty}" data-idx="${idx}" class="qty"/></td>
      <td>${money(l.unit_price)}</td>
      <td>${money(lineTotal)}</td>
      <td><button data-del="${idx}">✕</button></td>
    `;
    tb.appendChild(tr);
  });
  document.querySelector("#subtot").textContent = money(subtotal);
}

function readSessionId(){ return document.querySelector("#sessionId").value.trim(); }
function readPL(){ return parseInt(document.querySelector("#priceListId").value||"1"); }
function readCustomer(){
  const v = document.querySelector("#customerId").value.trim();
  return v?parseInt(v):null;
}

async function openSession(){
  const r = await fetch(API("/pos/session/open"),{
    method:"POST",
    headers:{"Content-Type":"application/json","X-Idempotency-Key": idem("ui-open")},
    body:JSON.stringify({ opened_by:"ui" })
  });
  if(!r.ok){ throw new Error("No se pudo abrir sesión"); }
  const j = await r.json();
  document.querySelector("#sessionId").value = j.session_id;
  document.querySelector("#sessStatus").textContent = j.status;
}

async function scanBarcode(){
  const bc = document.querySelector("#barcode").value.trim();
  const msg = document.querySelector("#scanMsg");
  msg.textContent = "";
  if(!bc) return;
  const r = await fetch(API(`/pos/scan/${encodeURIComponent(bc)}`));
  if(!r.ok){
    msg.textContent = "No encontrado"; msg.className="err"; return;
  }
  const p = await r.json();
  // línea default qty=1
  CART.push({ product_id: p.product_id, name:p.name, qty:1, unit_price:p.price });
  renderCart();
  msg.textContent = `+ ${p.name}`; msg.className="ok";
  document.querySelector("#barcode").value = "";
  document.querySelector("#barcode").focus();
}

function collectItems(){
  return CART.map(l => ({ product_id:l.product_id, qty:parseFloat(l.qty) }));
}

async function draft(){
  const session_id = parseInt(readSessionId());
  if(!session_id){ alert("Abre sesión primero"); return; }
  const price_list_id = readPL();
  const coupon = document.querySelector("#couponCode").value.trim();
  const body = { session_id, price_list_id, items: collectItems() };
  if(coupon) body.coupon_code = coupon; // si el backend ya soporta este campo
  const r = await fetch(API("/pos/order/draft"),{
    method:"POST",
    headers:{"Content-Type":"application/json","X-Idempotency-Key":idem("order-ui")},
    body:JSON.stringify(body)
  });
  if(!r.ok){
    const t = await r.text();
    alert("DRAFT error: "+t); return;
  }
  const j = await r.json();
  LAST_ORDER = j;
  document.querySelector("#disc").textContent = money(j.discount_total);
  document.querySelector("#tax").textContent = money(j.tax_total);
  document.querySelector("#total").textContent = money(j.total);
  document.querySelector("#orderInfo").textContent = `Orden ${j.order_no} (${j.status})`;
}

async function payCash(){
  if(!LAST_ORDER){ await draft(); if(!LAST_ORDER) return; }
  const r = await fetch(API("/pos/order/pay"),{
    method:"POST",
    headers:{"Content-Type":"application/json","X-Idempotency-Key":idem("pay-ui")},
    body:JSON.stringify({
      order_id: LAST_ORDER.order_id,
      splits: [{ method:"cash", amount: LAST_ORDER.total }]
    })
  });
  const txt = await r.text();
  if(!r.ok){ alert("PAY error: "+txt); return; }
  const j = JSON.parse(txt);
  LAST_ORDER = j.order;
  document.querySelector("#orderInfo").textContent = `Pago OK: ${j.order.order_no} → ${j.order.status}`;
}

async function undo(){
  if(!LAST_ORDER){ alert("No hay orden"); return; }
  const r = await fetch(API("/pos/order/undo"),{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({ order_id: LAST_ORDER.order_id })
  });
  const txt = await r.text();
  if(!r.ok){ alert("UNDO error: "+txt); return; }
  const j = JSON.parse(txt);
  LAST_ORDER = j.order;
  document.querySelector("#orderInfo").textContent = `UNDO: ${j.order.order_no} → ${j.order.status}`;
}

document.addEventListener("click",(e)=>{
  if(e.target.id==="btnOpen"){ openSession().catch(err=>alert(err)); }
  if(e.target.id==="btnScan"){ scanBarcode(); }
  if(e.target.id==="btnDraft"){ draft(); }
  if(e.target.id==="btnPayCash"){ payCash(); }
  if(e.target.id==="btnUndo"){ undo(); }
  if(e.target.dataset?.del){
    CART.splice(parseInt(e.target.dataset.del),1); renderCart();
  }
});
document.addEventListener("input",(e)=>{
  if(e.target.classList?.contains("qty")){
    const idx = parseInt(e.target.dataset.idx);
    CART[idx].qty = parseFloat(e.target.value||"0");
    renderCart();
  }
});
document.addEventListener("keydown",(e)=>{
  if(e.key==="Enter" && document.activeElement.id==="barcode"){ scanBarcode(); }
});
