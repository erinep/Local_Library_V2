$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Missing venv Python at $venvPython"
}

Push-Location $repoRoot
try {
    & $venvPython -m unittest discover -s tests -p "test_*.py" -v
} finally {
    Pop-Location
}
