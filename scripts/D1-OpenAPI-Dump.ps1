param(
  [string]$BaseUrl = "http://127.0.0.1:8010"
)

Write-Host "== D1 OpenAPI Dump =="

function GET($u){
  try { Invoke-RestMethod -Method GET -Uri $u -TimeoutSec 15 } catch { $null }
}

$spec = GET "$BaseUrl/openapi.json"
if (-not $spec) { Write-Error "No pude obtener /openapi.json"; exit 1 }

function Show-Schema([psobject]$schema, [string]$title){
  Write-Host ""
  Write-Host "---- $title ----"
  if ($null -eq $schema) { Write-Host "(sin schema)"; return }
  try {
    $req = $schema.required
    if ($req) { Write-Host ("required: " + ($req -join ", ")) } else { Write-Host "required: (ninguno)" }
  } catch { Write-Host "required: (?)" }

  try {
    $props = $schema.properties.PSObject.Properties.Name
    if ($props) {
      Write-Host "properties:"
      foreach($p in $props){
        try {
          $ps = $schema.properties.$p
          $t = $ps.type
          $fmt = $ps.format
          if ($ps.items) {
            $it = $ps.items.type
            Write-Host ("  - {0}: {1} (items: {2})" -f $p, $t, $it)
            if ($ps.items.properties) {
              $iprops = $ps.items.properties.PSObject.Properties.Name
              $ireq = $ps.items.required
              if ($iprops) { Write-Host ("      item.props: " + ($iprops -join ", ")) }
              if ($ireq)   { Write-Host ("      item.required: " + ($ireq -join ", ")) }
            }
          } else {
            if ($fmt) { Write-Host ("  - {0}: {1} ({2})" -f $p, $t, $fmt) }
            else { Write-Host ("  - {0}: {1}" -f $p, $t) }
          }
        } catch {
          Write-Host ("  - {0}" -f $p)
        }
      }
    } else {
      Write-Host "properties: (ninguna)"
    }
  } catch { Write-Host "properties: (?)" }
}

function Get-ReqSchema($spec, $path, $method){
  try { return $spec.paths.$path.$method.requestBody.content.'application/json'.schema } catch { $null }
}

$draftSchema = Get-ReqSchema $spec '/pos/order/draft' 'post'
$paySchema   = Get-ReqSchema $spec '/pos/order/pay' 'post'

Show-Schema $draftSchema "POS DRAFT schema (/pos/order/draft)"
Show-Schema $paySchema   "POS PAY schema (/pos/order/pay)"

Write-Host ""
Write-Host "== FIN D1 =="
