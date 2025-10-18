const API = "http://127.0.0.1:8000";

// DOM
const form = document.getElementById("orderForm");
const productEl = document.getElementById("product");
const sideEl = document.getElementById("side");
const priceEl = document.getElementById("price");
const qtyEl = document.getElementById("qty");
const placeResult = document.getElementById("placeResult");
const tradesEl = document.getElementById("trades");
const bidsEl = document.getElementById("bids");
const asksEl = document.getElementById("asks");
const rawOut = document.getElementById("rawOut");
const refreshTradesBtn = document.getElementById("refreshTrades");
const listOrdersBtn = document.getElementById("listOrders");

// helpers
function pretty(obj){
  return JSON.stringify(obj, null, 2);
}

async function httpJson(method, path, body){
  const res = await fetch(API + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`HTTP ${res.status}: ${t}`);
  }
  return res.json();
}

// place order
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  placeResult.textContent = "Placing...";
  try {
    const payload = {
      product_id: productEl.value,
      side: Number(sideEl.value),
      price: Number(priceEl.value),
      qty: Number(qtyEl.value)
    };
    const j = await httpJson("POST", "/orders", payload);
    placeResult.textContent = "Order placed: " + j.order_id;
  } catch (err) {
    placeResult.textContent = "Error: " + err.message;
  }
});

// manual refresh trades
refreshTradesBtn.addEventListener("click", refreshTrades);
listOrdersBtn.addEventListener("click", listOrders);

async function refreshTrades(){
  tradesEl.innerHTML = "Loading...";
  try {
    const arr = await httpJson("GET", "/trades");
    tradesEl.innerHTML = "";
    arr.forEach(t => {
      const d = document.createElement("div");
      d.className = "trade";
      d.textContent = `${new Date(t.execution_timestamp*1000).toLocaleTimeString()} — ${t.qty}@${t.price} (buy:${t.bid_order_id.slice(0,6)} ask:${t.ask_order_id.slice(0,6)})`;
      tradesEl.appendChild(d);
    });
  } catch (err) {
    tradesEl.textContent = "Error: " + err.message;
  }
}

async function listOrders(){
  rawOut.textContent = "Loading orders...";
  try {
    const arr = await httpJson("GET", "/orders");
    rawOut.textContent = pretty(arr);
  } catch (err) {
    rawOut.textContent = "Error: " + err.message;
  }
}

// WebSocket — trades
let wsTrades;
function startTradesWS(){
  try {
    wsTrades = new WebSocket("ws://127.0.0.1:8000/ws/trades");
    wsTrades.onopen = () => console.log("ws trades open");
    wsTrades.onmessage = (ev) => {
      try {
        const t = JSON.parse(ev.data);
        const d = document.createElement("div");
        d.className = "trade live";
        d.textContent = `${new Date(t.execution_timestamp*1000).toLocaleTimeString()} — ${t.qty}@${t.price}`;
        tradesEl.prepend(d);
      } catch(e){}
    };
    wsTrades.onclose = () => setTimeout(startTradesWS, 1000);
  } catch(e){
    console.warn("ws trades error", e);
  }
}

// WebSocket — orderbook snapshot for product
let wsBook;
function startBookWS(product="PROD1"){
  try {
    wsBook = new WebSocket(`ws://127.0.0.1:8000/ws/book/${product}`);
    wsBook.onopen = () => console.log("ws book open");
    wsBook.onmessage = (ev) => {
      try {
        const snap = JSON.parse(ev.data);
        renderBookSnapshot(snap);
      } catch(e){}
    };
    wsBook.onclose = () => setTimeout(()=>startBookWS(product), 1000);
  } catch(e){
    console.warn("ws book error", e);
  }
}

function renderBookSnapshot(snap){
  bidsEl.innerHTML = "";
  asksEl.innerHTML = "";
  if (!snap) return;
  (snap.bids || []).forEach(level => {
    const li = document.createElement("li");
    li.textContent = `${level.price} (${level.qty})`;
    bidsEl.appendChild(li);
  });
  (snap.asks || []).forEach(level => {
    const li = document.createElement("li");
    li.textContent = `${level.price} (${level.qty})`;
    asksEl.appendChild(li);
  });
}

// start live
startTradesWS();
startBookWS();
refreshTrades(); // initial http load
