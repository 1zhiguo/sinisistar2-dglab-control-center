param([Parameter(Mandatory=$true)][string]$Request)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$job=[IO.File]::ReadAllText($Request,[Text.Encoding]::UTF8) | ConvertFrom-Json
$root=[IO.Path]::GetFullPath($job.game)
$output=[IO.Path]::GetFullPath($job.output)
if (-not [IO.Directory]::Exists($output)) { throw 'Missing staging directory' }
$bytes=[IO.File]::ReadAllBytes([IO.Path]::Combine($root,$job.resources))
$iv=[Text.Encoding]::UTF8.GetString($bytes,[int]$job.crypto.iv_offset,[int]$job.crypto.iv_length)+$job.crypto.iv_suffix
$key=[Text.Encoding]::UTF8.GetString($bytes,[int]$job.crypto.key_offset,[int]$job.crypto.key_length)+$job.crypto.key_suffix
$cipher=New-Object Security.Cryptography.RijndaelManaged
try {
    $cipher.KeySize=256; $cipher.BlockSize=256
    $cipher.Mode=[Security.Cryptography.CipherMode]::CBC
    $cipher.Padding=[Security.Cryptography.PaddingMode]::PKCS7
    $cipher.IV=[Text.Encoding]::UTF8.GetBytes($iv)
    $cipher.Key=[Text.Encoding]::UTF8.GetBytes($key)
    foreach ($name in $job.bundles) {
        if ($name -notmatch '^[a-f0-9]{29}$') { throw 'Invalid bundle name' }
        $file=[IO.Path]::Combine($root,'SiNiSistar2_Data/StreamingAssets/game_bin',$name)
        $encrypted=[IO.File]::ReadAllBytes($file)
        $transform=$cipher.CreateDecryptor()
        try { $plain=$transform.TransformFinalBlock($encrypted,0,$encrypted.Length) }
        finally { $transform.Dispose() }
        [IO.File]::WriteAllBytes([IO.Path]::Combine($output,$name),$plain)
    }
} finally { $cipher.Dispose() }
