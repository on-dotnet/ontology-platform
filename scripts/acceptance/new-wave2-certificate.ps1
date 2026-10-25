#Requires -Version 7.4
[CmdletBinding()]
param([Parameter(Mandatory)][string]$RuntimeFile)
$ErrorActionPreference = 'Stop'
$runtime = Get-Content -Raw -LiteralPath $RuntimeFile | ConvertFrom-Json
if (Test-Path -LiteralPath $runtime.certificatePath) { throw 'Preserve existing private certificate' }
# 私钥仅存在本次进程和新建PFX，不进入系统信任或命令行参数。
$rsa = [Security.Cryptography.RSA]::Create(2048)
try {
    $request = [Security.Cryptography.X509Certificates.CertificateRequest]::new('CN=OntologyPlatform Wave2 local keyring', $rsa, [Security.Cryptography.HashAlgorithmName]::SHA256, [Security.Cryptography.RSASignaturePadding]::Pkcs1)
    $certificate = $request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5), [DateTimeOffset]::UtcNow.AddDays(30))
    try {
        [IO.File]::WriteAllBytes($runtime.certificatePath, $certificate.Export([Security.Cryptography.X509Certificates.X509ContentType]::Pfx, $runtime.certificatePassword))
        if (-not $IsWindows) { [IO.File]::SetUnixFileMode($runtime.certificatePath, [IO.UnixFileMode]::UserRead -bor [IO.UnixFileMode]::UserWrite) }
    } finally { $certificate.Dispose() }
} finally { $rsa.Dispose() }
Write-Output 'CREATED: isolated encrypted PFX; no trust installation.'
