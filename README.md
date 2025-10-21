# 🧾 OrderAPI — Limit Order Book (FastAPI + Python)

## 🧠 Overview

A simple **Order Matching Engine** that simulates a **limit order book** using:

- **Max-heap** for buy orders (highest bid first)
- **Min-heap** for sell orders (lowest ask first)
- **Automatic trade creation** when bid ≥ ask

Built with **FastAPI**, supports both **REST** and **WebSocket** APIs.  
Now includes persistence (WAL + snapshot), **background snapshot loop**, and a **split matcher microservice** (via Docker Compose).

---

## ⚙️ Setup (Local)

```powershell
cd "C:\Users\Jivika Arora\Documents\projects\OrderAPI"
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Server runs at: http://127.0.0.1:8000

Check Health:
 
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method GET
```

---

## 📦 Example API Calls

1. Place a Buy Order

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" `
-Method POST -Body '{"product_id":"PROD1","side":1,"price":120.0,"qty":5}' `
-ContentType "application/json"
```

2. Place a Sell Order

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" `
-Method POST -Body '{"product_id":"PROD1","side":-1,"price":115.0,"qty":3}' `
-ContentType "application/json"
```

3. View All Trades

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/trades" -Method GET
```

4. Fetch an Order

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders/<order_id>" -Method GET
```

---

## 🔌 WebSocket Endpoints

### 📡 Live Trades

```arduino
ws://127.0.0.1:8000/ws/trades
```

### 📘 Order Book Snapshots

```ruby
ws://127.0.0.1:8000/ws/book/PROD1
```

### 🧪 Run Local Test Clients

```powershell
python .\app\test_ws.py
python .\app\test_trades_ws.py
```

---

## 🧩 Persistence Details


|File                  |Purpose                                                                    |
|----------------------|--------------------------------------------------------------------------|
|data/wal.log	       | Write-Ahead Log of all events (place/modify/cancel/trade)                    |
|data/snapshot.json    | Snapshot for faster recovery                                                 |
|Background Task       | Saves a snapshot every 30 seconds                                            |
|On Startup	           | Restores snapshot → replays WAL → rebuilds heaps → rematches crossable orders|

---


## 🐳 Docker Setup


### Build & Run with Compose

```powershell
docker compose up -d --build
```

### Check Containers

```powershell
docker compose ps
```


### You should see:

orderapi-api-1       Up  (port 8000)
orderapi-matcher-1   Up  (port 9000)

### View Logs

```powershell
docker compose logs api --tail 50
docker compose logs matcher --tail 50
```

### Stop

```powershell
docker compose down
```

---

## ⚙️ Architecture Summary
|Component	         | Description                                               |
|------------------------|-----------------------------------------------------------|
|app/main.py	         | FastAPI app: REST, WebSocket, background snapshot loop    | 
|app/orderbook.py	 | Core matching engine (heaps + order management)           |
|app/persistence.py	 | WAL + snapshot read/write/replay                          |
|services/matcher	 | Separate matching microservice                            |
|scripts/run_scenario.ps1| End-to-end test: buy/sell → match → trades visible        |
|docker-compose.yml	 | Runs API + matcher as services, connected internally      |
|data/	                 | Persistent logs & snapshot folder                         |

---

## 🧱 Architecture  &  Data Flow

1. Client/UI places an order via /orders.
2. API service records the event in WAL.
3. Matcher service reads from snapshot + WAL and executes the matching logic.
4. Matched trades are persisted and broadcasted in real time via: WebSocket (live updates) , /trades (REST endpoint)
5. The background snapshot loop saves the engine state periodically for recovery.

---

## ✅ Features

1. Place, modify, cancel, and fetch orders
2. View all trades
3. Real-time orderbook + trades via WebSockets
4. Snapshot & WAL persistence (durable recovery)
5. Background snapshot task (every 30 seconds)
6. Multi-service architecture (API + Matcher via Docker)
7. Automatic matching of crossable orders
8. REST + WebSocket API fully documented
9. Static UI Dashboard at /web/index.html

---

## 🧪 Example Test Scenario (PowerShell)

### Place a buy

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" `
-Method POST -Body '{"product_id":"PROD1","side":1,"price":220.0,"qty":1}' `
-ContentType "application/json"
```

### Place a matching sell

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" `
-Method POST -Body '{"product_id":"PROD1","side":-1,"price":220.0,"qty":1}' `
-ContentType "application/json"
```

### View trades

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/trades" -Method GET
```

---

## 🧠 Design Decisions

1. Matching engine separated as a microservice for scalability
2. Heap-based structures ensure O(log N) insert and match efficiency
3. API is stateless → horizontally scalable
4. Snapshot & WAL ensure persistence even after crashes
5. Static web UI integrated for seamless testing without Postman

---

## 🧩 Tech Stack

1. **Language** :  Python 3.11
2. **Framework** :  FastAPI + Uvicorn
3. **Concurrency** :  asyncio
4. **Storage** :  Snapshot + WAL
5. **Frontend** :  HTML + JavaScript + WebSocket
6. **Containerization** :  Docker + Docker Compose

---

## 💭 Design Philosophy

The goal of this system is to achieve **maximum throughput** for order processing while maintaining correctness and determinism.

Every core **order book operation** (insert, cancel, match, modify) runs in **amortized O(1)** time, leveraging efficient heap-based structures.  
By **removing disk and network access from the critical path**, the system ensures that matching happens purely in-memory for speed.

Order matching is intentionally designed to be **sequential**, as deterministic matching is critical to maintaining a consistent market state.  
All other tasks — such as persistence (snapshot/WAL writing), logging, and WebSocket broadcasting — are **decoupled** into separate processes or async background loops.

This allows:
- **Fast, single-threaded matching loop** → highest matching speed  
- **Parallel auxiliary services** (API, persistence, UI) → horizontal scalability  
- **No blocking I/O** during trade execution  

This design mimics the core philosophy of real-world trading systems:  
keep the **matching path lightweight and sequential**, and push everything else to asynchronous pipelines.

---

## 🧾 One-Paragraph Summary

This project implements a complete limit order book system using FastAPI (Python) with real-time WebSocket streaming and REST APIs. It supports order placement, modification, cancellation, and automatic trade matching between buyers and sellers using heap-based logic. The system is split into two microservices — an API service and a Matcher service — orchestrated via Docker Compose, with persistent storage handled by a snapshot + WAL model. A simple frontend webpage is included for interacting with and visualizing live trades and orderbooks in real time.

---

## 👩‍💻 Author

Jeevika Arora

---

