param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366
)
function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function POST-R([string]$Url,$Body){
  try{
    $r=Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -UseBasicParsing -ErrorAction Stop
    return @{ ok=$true; status=[int]$r.StatusCode; json=($r.Content|ConvertFrom-Json) }
  } catch {
    $s=$null;$t=$null
    try{$s=[int]$_.Exception.Response.StatusCode}catch{}
    try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    return @{ ok=$false; status=$s; text=$t }
  }
}
# Comparación robusta para números/decimales provenientes como string
function EqNum($a,$b){
  try { return ([decimal]$a -eq [decimal]$b) } catch { return $a -eq $b }
}

Write-Host "== T13: Vigencia y Weekdays =="

# --- Reset de uso para pruebas determinísticas ---
try{
  $reset = Invoke-WebRequest -Method POST -Uri "$BaseUrl/pos/coupon/dev/reset-usage" -UseBasicParsing `
    -ContentType "application/json" -Body (J @{ code="TEST10"; customer_id=$CustomerId })
  Write-Host ("reset-usage: " + $reset.Content)
}catch{
  Write-Host "reset-usage: (skip) $_"
}

$ok = $true

# 1) WEEKEND15: sábado 2025-08-30 12:00 (espera OK)
$case1 = POST-R "$BaseUrl/pos/coupon/validate" @{ code="WEEKEND15"; amount=129; customer_id=$CustomerId; at="2025-08-30T12:00:00" }
Write-Host ("WEEKEND15 @Sat: " + (J $case1.json))
if (-not ($case1.ok -and $case1.json.valid -eq $true -and (EqNum $case1.json.discount_value 15))) { $ok=$false }

# 2) WEEKEND15: lunes 2025-08-25 12:00 (espera bloqueado)
$case2 = POST-R "$BaseUrl/pos/coupon/validate" @{ code="WEEKEND15"; amount=129; customer_id=$CustomerId; at="2025-08-25T12:00:00" }
Write-Host ("WEEKEND15 @Mon: " + (J $case2.json))
if (-not ($case2.ok -and $case2.json.valid -eq $false -and $case2.json.reason -eq "weekday_not_allowed")) { $ok=$false }

# 3) DATED5: dentro del rango (2025-08-25) (espera OK 5.00)
$case3 = POST-R "$BaseUrl/pos/coupon/validate" @{ code="DATED5"; amount=100; customer_id=$CustomerId; at="2025-08-25T10:00:00" }
Write-Host ("DATED5 in-range: " + (J $case3.json))
if (-not ($case3.ok -and $case3.json.valid -eq $true -and (EqNum $case3.json.discount_amount 5.00))) { $ok=$false }

# 4) DATED5: fuera del rango (2025-09-05) (espera bloqueado)
$case4 = POST-R "$BaseUrl/pos/coupon/validate" @{ code="DATED5"; amount=100; customer_id=$CustomerId; at="2025-09-05T10:00:00" }
Write-Host ("DATED5 out-range: " + (J $case4.json))
if (-not ($case4.ok -and $case4.json.valid -eq $false -and $case4.json.reason -eq "date_window_not_met")) { $ok=$false }

# 5) Sanity: TEST10 debe seguir ok con 129
$case5 = POST-R "$BaseUrl/pos/coupon/validate" @{ code="TEST10"; amount=129; customer_id=$CustomerId }
Write-Host ("TEST10: " + (J $case5.json))
if (-not ($case5.ok -and $case5.json.valid -eq $true -and (EqNum $case5.json.new_total 116.10))) { $ok=$false }

if ($ok) {
  Write-Host ">> OK: reglas de vigencia/weekday funcionando y reglas previas intactas."
} else {
  Write-Error ">> FAIL: alguna condición no se cumplió; revisar salidas arriba."
}
