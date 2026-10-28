#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$validator = Join-Path $root 'scripts/test-review-evidence.ps1'
if (-not (Test-Path $validator)) { throw 'Required early evidence validator is missing.' }
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('ontology-evidence-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $temporary | Out-Null
$passed = 0
function Exercise {
    param([string]$Name, $Evidence, [bool]$Accept, [switch]$BadEof)
    $path = Join-Path $temporary ($Name + '.json')
    [IO.File]::WriteAllText($path, ($Evidence | ConvertTo-Json -Depth 20) + $(if ($BadEof) { "`n`n" } else { "`n" }))
    $null = & pwsh -NoProfile -File $validator -EvidenceFile $path -ExpectedHead ('a' * 40) 2>&1
    if (($LASTEXITCODE -eq 0) -ne $Accept) { throw "Unexpected evidence preflight result: $Name" }
    $script:passed++
}
try {
    $good = @{ evidenceSchemaVersion = 1; checks = @(@{ name = 'synthetic-test'; command = 'python3 synthetic.py'; status = 'PASS'; exitCode = 0; output = '1 actual fixture check' }); ci = @{ status = 'NOT_VERIFIED'; runId = $null; url = $null; commit = $null; conclusion = $null }; metadata = @{ taskId = 'G3-M3-001' } }
    Exercise 'valid-current' $good $true
    foreach ($field in @('name', 'command', 'status', 'exitCode', 'output')) {
        $item = $good | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable
        $item.checks[0].Remove($field)
        Exercise ('missing-' + $field) $item $false
    }
    $item = $good | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable
    $item.checks[0].duration = 1
    Exercise 'extra-check-field' $item $false
    $item = $good | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable
    $item.checks[0].status = 'GREEN'
    Exercise 'invalid-status' $item $false
    $item = $good | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable
    $item.ci = @{ status = 'PASS'; runId = '123'; url = 'https://github.com/on-dotnet/ontology-platform/actions/runs/123'; commit = ('b' * 40); conclusion = 'success' }
    Exercise 'head-mismatch' $item $false
    Exercise 'bad-eof' $good $false -BadEof
    $historical = Get-Content -Raw (Join-Path $root 'docs/evidence/G3-M2-001/validation.json') | ConvertFrom-Json -AsHashtable
    Exercise 'historical-metadata' $historical $true
    $generated = Join-Path $temporary 'generated.json'
    & pwsh -NoProfile -File (Join-Path $root 'scripts/new-review-evidence.ps1') -OutputPath $generated -TaskId G3-M3-001 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Generator failed' }
    & pwsh -NoProfile -File $validator -EvidenceFile $generated -ExpectedHead ('a' * 40) | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Generated evidence failed shared schema' }
    $passed++
    $selectionFile = Join-Path $temporary 'selection.json'
    $tooMany = @{ schemaVersion = 1; screenshots = @(1..13 | ForEach-Object { @{ path = "docs/evidence/FIXTURE/$_.png"; page = "page$_"; theme = 'light'; viewport = '1440x900'; stable = $true } }) }
    [IO.File]::WriteAllText($selectionFile, ($tooMany | ConvertTo-Json -Depth 12) + "`n")
    $null = & pwsh -NoProfile -File $validator -EvidenceFile $generated -ScreenshotSelection $selectionFile 2>&1
    if ($LASTEXITCODE -eq 0) { throw 'Screenshot count inflation was accepted' }
    $passed++
    $inventoryFile = Join-Path $temporary 'ignored.json'
    $inventory = @{ count = 0; estimatedBytes = 0; listSha256 = ('a' * 64); scannedAt = '2026-10-28T00:00:00Z'; sizeMethod = 'File length metadata only; no content reads or symlink traversal; unavailable lengths counted separately.'; groups = @() }
    [IO.File]::WriteAllText($inventoryFile, ($inventory | ConvertTo-Json -Depth 12) + "`n")
    $null = & pwsh -NoProfile -File $validator -EvidenceFile $generated -IgnoredInventoryFile $inventoryFile 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Valid bounded ignored inventory was rejected' }
    $passed++
    $inventory.unboundedPaths = @('private-path-must-not-propagate')
    [IO.File]::WriteAllText($inventoryFile, ($inventory | ConvertTo-Json -Depth 12) + "`n")
    $null = & pwsh -NoProfile -File $validator -EvidenceFile $generated -IgnoredInventoryFile $inventoryFile 2>&1
    if ($LASTEXITCODE -eq 0) { throw 'Unbounded ignored inventory field was accepted' }
    $passed++
    Write-Output "EvidencePreflight: $passed checks PASS; schema only, CI/product NOT_RUN."
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
