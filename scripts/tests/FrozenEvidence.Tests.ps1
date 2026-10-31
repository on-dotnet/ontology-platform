#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../verify.ps1') -Library
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$path = 'docs/evidence/G3-M4-001/mac-master/actual-v2-manifest.json'
$content = [IO.File]::ReadAllBytes((Join-Path $root $path))
if (-not (Test-FrozenEvidenceFormat $path $content)) { throw 'Original immutable evidence was not recognized' }
if (Test-FrozenEvidenceFormat $path ([byte[]]($content + 32))) { throw 'Changed bytes bypassed text format checks' }
if (Test-FrozenEvidenceFormat 'docs/evidence/G3-M5-001/manifest.json' $content) { throw 'New task inherited historical exception' }
if (Test-FrozenEvidenceFormat 'source.json' $content) { throw 'Product source inherited evidence exception' }
if (Test-FrozenEvidenceFormat $path ([byte[]](@(239, 187, 191) + $content))) { throw 'BOM variant bypassed exact raw evidence hash' }
Write-Output 'FrozenEvidence: exact original bytes only, 5 checks PASS; history unchanged.'
