#Requires -Version 7.4
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputPath, [Parameter(Mandatory)][ValidatePattern('^[A-Z0-9][A-Z0-9-]{0,79}$')][string]$TaskId, [ValidatePattern('^[0-9a-f]{40}$')][string]$TestedCommit)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputPath) { throw 'EVIDENCE_EXISTS: refusing to replace existing observations' }
$value = [ordered]@{
    evidenceSchemaVersion = 1
    checks = @([ordered]@{ name = 'task-validation'; command = $null; status = 'NOT_RUN'; exitCode = $null; output = 'No task validation has been executed; replace only with actual observations.' })
    ci = [ordered]@{ status = 'NOT_VERIFIED'; runId = $null; url = $null; commit = $null; conclusion = $null }
    metadata = @{ taskId = $TaskId; actualAgentActiveTime = 'UNKNOWN' }
}
if ($TestedCommit) { $value.evidenceSchemaVersion = 2; $value.validationSource = 'LOCAL'; $value.testedCommit = $TestedCommit; $value.ci.status = 'NOT_RUN' }
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), ($value | ConvertTo-Json -Depth 12 -Compress) + "`n", [Text.UTF8Encoding]::new($false))
Write-Output (@{ status = 'GENERATED_NOT_RUN'; path = [IO.Path]::GetFullPath($OutputPath) } | ConvertTo-Json -Compress)
