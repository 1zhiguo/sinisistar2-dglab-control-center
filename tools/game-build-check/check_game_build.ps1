param([string]$GameDirectory = '', [string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
try {
    if ([string]::IsNullOrWhiteSpace($GameDirectory)) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = '请选择包含 SiNiSistar2.exe 的游戏目录（或其上层目录）'
        $picker.ShowNewFolderButton = $false
        if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
        $GameDirectory = $picker.SelectedPath
        $picker.Dispose()
    }
    $chosen = Get-Item -LiteralPath $GameDirectory
    $gameRoot = if ($chosen.PSIsContainer) { $chosen.FullName } else { $chosen.DirectoryName }
    if (-not (Test-Path -LiteralPath (Join-Path $gameRoot 'SiNiSistar2.exe') -PathType Leaf)) {
        if (Test-Path -LiteralPath (Join-Path $gameRoot 'WIN/SiNiSistar2.exe') -PathType Leaf) {
            $gameRoot = Join-Path $gameRoot 'WIN'
        } else { throw '未找到 SiNiSistar2.exe，请选择游戏程序所在目录。' }
    }
    $expectedFiles = @(
    @{ File = 'SiNiSistar2.exe'; Expected = '14aa8540d92597f0e7482bf2c11d63a9cd202bb3accbaed7bf0a12a141e259a7' }
    @{ File = 'GameAssembly.dll'; Expected = 'b869493305bbe587598c8709e7fe271f00d79d37803c6a8241946d6a6297499d' }
    @{ File = 'UnityPlayer.dll'; Expected = '43fb0aea1b80c74963dae88ec7fc1c3c1993d893ce94d12972000fcc9b653ad1' }
    @{ File = 'SiNiSistar2_Data/il2cpp_data/Metadata/global-metadata.dat'; Expected = 'a56278d0162b6c148312b56fbe208b54ba9af2d3bad609ebf9349b7ae7ddc84b' }
    )
    $files = @()
    foreach ($entry in $expectedFiles) {
        $filePath = Join-Path $gameRoot $entry.File
        $exists = Test-Path -LiteralPath $filePath -PathType Leaf
        $actual = $null; $length = $null; $version = $null
        if ($exists) {
            $actual = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
            $length = (Get-Item -LiteralPath $filePath).Length
            if ($entry.File -match '\.(exe|dll)$') {
                $version = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($filePath).FileVersion
            }
        }
        $files += [ordered]@{file=$entry.File;exists=$exists;bytes=$length;sha256=$actual;expected_sha256=$entry.Expected;matches=($actual -eq $entry.Expected);file_version=$version}
    }
    $mismatches = @($files | Where-Object { -not $_.matches })
    $coreMismatches = @($mismatches | Where-Object { $_.file -eq 'GameAssembly.dll' -or $_.file -like '*global-metadata.dat' })
    $classification = if ($mismatches.Count -eq 0) {'verified_build'} elseif ($coreMismatches.Count -gt 0) {'core_files_differ'} else {'launcher_or_unity_files_differ'}
    $report = [ordered]@{schema=1;created_utc=[DateTime]::UtcNow.ToString('o');tool='SiNiSistar2 read-only build check';reference_game_version='1.3.1';classification=$classification;all_files_match=($mismatches.Count -eq 0);core_build_matches=($coreMismatches.Count -eq 0);files=$files;game_files_modified=$false;save_data_read=$false;device_connection_started=$false}
    if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { $OutputDirectory = $PSScriptRoot }
    [System.IO.Directory]::CreateDirectory($OutputDirectory) | Out-Null
    $reportPath = Join-Path $OutputDirectory ('sinisistar2-build-check-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmssfff') + '.json')
    [System.IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 8), (New-Object System.Text.UTF8Encoding($true)))
    foreach ($file in $files) {
        $status = if ($file.matches) { '匹配' } elseif (-not $file.exists) { '缺失' } else { '不同' }
        Write-Host ($status + '  ' + $file.file)
    }
    Write-Host ''
    Write-Host ('校验结果已保存：' + $reportPath)
    Write-Host '请将生成的 JSON 发回，并说明 Steam 游戏版本、补丁名称和补丁版本。'
    Write-Host '本工具仅读取四个游戏文件，不修改游戏、不读取存档、不连接设备。'
    exit 0
} catch {
    Write-Host ('检查未完成：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
