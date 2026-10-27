param([switch]$Desktop)
$ErrorActionPreference = 'Stop'
$ProjectDirectory = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$IconPath = Join-Path $ProjectDirectory 'src\sinisistar_dglab\assets\app-icon.ico'
$LauncherPath = Join-Path $ProjectDirectory 'run_native.ps1'
if (-not (Test-Path -LiteralPath $IconPath) -or -not (Test-Path -LiteralPath $LauncherPath)) {
    throw 'The control center icon or launcher is missing.'
}
$ShortcutDirectory = if ($Desktop) { [Environment]::GetFolderPath('Desktop') } else { $ProjectDirectory }
$ShortcutPath = Join-Path $ShortcutDirectory 'SiNiSistar2 x DG-LAB.lnk'
$Shell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $ShortcutPath) {
    $ExistingShortcut = $Shell.CreateShortcut($ShortcutPath)
    if ($ExistingShortcut.Arguments -notlike ('*' + $LauncherPath + '*')) {
        throw 'An unrelated shortcut already uses this name. It was not changed.'
    }
}
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $LauncherPath + '"'
$Shortcut.WorkingDirectory = $ProjectDirectory
$Shortcut.IconLocation = $IconPath + ',0'
$Shortcut.Description = 'SiNiSistar2 x DG-LAB Control Center'
$Shortcut.WindowStyle = 7
$Shortcut.Save()
[System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Shortcut) | Out-Null
[System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($Shell) | Out-Null
Write-Output $ShortcutPath
