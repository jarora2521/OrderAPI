# Simple scenario: place orders and fetch trades + orderbook
Write-Host "Placing buy 1 @ 230"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" -Method POST -Body '{"product_id":"PROD1","side":1,"price":230.0,"qty":1}' -ContentType "application/json" | Write-Host

Write-Host "Placing sell 1 @ 230 (should match)"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" -Method POST -Body '{"product_id":"PROD1","side":-1,"price":230.0,"qty":1}' -ContentType "application/json" | Write-Host

Write-Host "`nTrades:"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/trades" -Method GET | Format-List

Write-Host "`nOrders:"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" -Method GET | Format-List

Write-Host "`nSnapshot (PROD1):"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/orders" -Method GET | Out-Null
