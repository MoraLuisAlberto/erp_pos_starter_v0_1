param(
  [string]$BaseUrl = "http://127.0.0.1:8010"
)

Write-Host "== T7: Coupon rules probe =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function POSTRAW([string]$Url, $Body){
  try {
    $r = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -ErrorAction Stop
    return @{ status=[int]$r.StatusCode; text=$r.Content }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    return @{ status=$s; text=$t }
  }
}

$tests = @(
  @{ name="TEST10 ok (129→10%)"; body=@{ code="TEST10"; amount=129 } },
  @{ name="SAVE50 ok (220→-50)"; body=@{ code="SAVE50"; amount=220 } },
  @{ name="SAVE50 fail (<200)";  body=@{ code="SAVE50"; amount=129 } },
  @{ name="NITE20 ok (20:00)";   body=@{ code="NITE20"; amount=129; at="2025-08-25T20:00:00" } },
  @{ name="NITE20 fail (10:00)"; body=@{ code="NITE20"; amount=129; at="2025-08-25T10:00:00" } },
  @{ name="404 code";            body=@{ code="NOPE";   amount=129 } }
)

$i=0
foreach($t in $tests){
  $i++
  Write-Host ""
  Write-Host ("-- Case {0}: {1}" -f $i, $t.name)
  Write-Host ("Body: " + (J $t.body))
  $r = POSTRAW "$BaseUrl/pos/coupon/validate" $t.body
  Write-Host ("Status: {0}" -f $r.status)
  $r.text | Out-String | Write-Host
}
Write-Host ""
Write-Host "== T7 FIN =="
