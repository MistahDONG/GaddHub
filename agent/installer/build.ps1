param(
    [string]$Python = "",
    [string]$Compiler = ""
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
if (-not $Python) {
    $Python = Join-Path $root ".venv\Scripts\python.exe"
}
if (-not $Compiler) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        $Compiler = $command.Source
    } else {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        )
        $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $Compiler -or -not (Test-Path -LiteralPath $Compiler)) {
    throw "Inno Setup 6 not found. Install JRSoftware.InnoSetup or pass -Compiler with the ISCC.exe path."
}
if (-not (Test-Path -LiteralPath (Join-Path $root "dist\GaddHub\GaddHub.exe"))) {
    throw "Build the agent with PyInstaller before compiling the installer."
}
$version = & $Python -c "import pathlib, sys, tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))['project']['version'])" (Join-Path $root "pyproject.toml")
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Cannot read a three-part numeric agent version from pyproject.toml."
}
& $Compiler "/Q" "/DAppVersion=$version" (Join-Path $PSScriptRoot "GaddHub.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}
$installer = Join-Path $root "dist\GaddHub-Setup-$version-windows-x64.exe"
if (-not (Test-Path -LiteralPath $installer)) {
    throw "Installer output is missing."
}
Write-Output "Installer: $installer"
