param([string]$Python = "py", [string[]]$PythonArgs = @("-3.13"))
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($env:OS -ne "Windows_NT") { throw "Build on an isolated Windows computer." }
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $bundle = Join-Path $projectRoot "dist\AQUA_COMMAND_Mini_v0.1_windows_x64"
    if (Test-Path $bundle) { throw "Output already exists. Preserve it or choose a fresh source directory." }
    & $Python @PythonArgs -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw "Python 3.13 venv failed" }
    $buildPython = Join-Path $projectRoot ".venv-build\Scripts\python.exe"
    & $buildPython -m pip --isolated install --index-url https://pypi.org/simple -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Build dependencies failed" }
    New-Item -ItemType Directory -Force evidence | Out-Null
    $env:PYTHONUTF8 = "1"
    $env:AQUA_RUN_GUI_TESTS = "1"
    & $buildPython -m unittest discover -v *> evidence\windows-native-tests.txt
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; see evidence\windows-native-tests.txt" }
    & $buildPython -m PyInstaller --noconfirm --clean --onedir --windowed --name AQUA_COMMAND_Mini --distpath build\frozen --workpath build\gui --specpath build desktop.py
    if ($LASTEXITCODE -ne 0) { throw "GUI build failed" }
    & $buildPython -m PyInstaller --noconfirm --clean --onefile --console --name AQUA_COMMAND_Mini_CLI --distpath build\frozen --workpath build\cli --specpath build launcher.py
    if ($LASTEXITCODE -ne 0) { throw "CLI build failed" }
    New-Item -ItemType Directory -Force $bundle | Out-Null
    Copy-Item build\frozen\AQUA_COMMAND_Mini\* $bundle -Recurse
    Copy-Item build\frozen\AQUA_COMMAND_Mini_CLI.exe $bundle
    Copy-Item README.md, INSTALL_TH.md, START_HERE_TH.txt, Start.cmd, THIRD_PARTY_NOTICES.md $bundle
    Copy-Item examples, docs $bundle -Recurse
    $pythonBase = & $buildPython -c "import sys; print(sys.base_prefix)"
    Copy-Item (Join-Path $pythonBase "LICENSE.txt") (Join-Path $bundle "PYTHON_LICENSE.txt")
    & $buildPython scripts\smoke_bundle.py $bundle --report evidence\windows-native-bundle-smoke.json
    if ($LASTEXITCODE -ne 0) { throw "Packaged app smoke test failed" }
    Copy-Item evidence $bundle -Recurse
    Get-ChildItem $bundle -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($bundle.Length + 1)
        $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $relative"
    } | Set-Content -Encoding utf8 (Join-Path $bundle "SHA256SUMS.txt")
    Compress-Archive -Path $bundle -DestinationPath "$bundle.zip"
    Write-Host "PoC package: $bundle.zip"
    Write-Host "Native Windows 11 operator acceptance and actual Telegram TEST still require approval."
} finally {
    Pop-Location
}
