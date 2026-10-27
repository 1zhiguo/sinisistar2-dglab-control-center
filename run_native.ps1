$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Create .venv and install requirements-native.txt first. See README.md." }
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Push-Location -LiteralPath $ProjectRoot
try { & $PythonPath -m sinisistar_dglab.app @args; $ApplicationExit = $LASTEXITCODE }
finally { Pop-Location }
exit $ApplicationExit
