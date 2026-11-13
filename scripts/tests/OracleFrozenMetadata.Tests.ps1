#Requires -Version 7.4
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../verify.ps1') -Library
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$path = 'docs/evidence/G4-M2-ORACLE-01/metadata/dbd385a383e229ba349c103d779932a9fb24c7f92c762b5fe0420e59a1be347b.json'
$raw = [IO.File]::ReadAllBytes((Join-Path $root $path))
if (-not (Test-FrozenEvidenceFormat $path $raw)) { throw 'Exact approved Oracle config raw bytes must remain immutable' }
if (Test-FrozenEvidenceFormat $path ([byte[]]($raw + 10))) { throw 'Changed Oracle bytes bypassed format check' }
if (Test-FrozenEvidenceFormat 'source.json' $raw) { throw 'Product source inherited Oracle exception' }
if (Test-FrozenEvidenceFormat ($path.Replace('ORACLE-01', 'ORACLE-02')) $raw) { throw 'Other task inherited Oracle exception' }
if (Test-FrozenEvidenceFormat $path ([byte[]](@(239,187,191) + $raw))) { throw 'BOM bypassed exact hash' }
Write-Output 'Oracle frozen metadata: 5 exact path/byte checks PASS.'
