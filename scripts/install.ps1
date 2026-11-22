# Requires Windows PowerShell 5.1 or later.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$pythonVersion = '3.14.10'
$pythonUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-amd64.zip"
# From the official windows-3.14.10.json release manifest.
$pythonSha256 = 'cc28026a650970cc1570bb127312f1f9634eb67abfe157ae6ca1acbbc627d091'
$project = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $project '.runtime'
$portableDir = Join-Path $runtimeDir "python-$pythonVersion-amd64"
$portablePython = Join-Path $portableDir 'python.exe'
$venvDir = Join-Path $project '.venv'
$python = Join-Path $venvDir 'Scripts\python.exe'

function Test-Python([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        return $false
    }
    try {
        & $Executable -I -c "import sys, sysconfig, ensurepip, tkinter, venv; tkinter.Tcl(); sys.exit(not (sys.version_info[:2] in ((3, 13), (3, 14)) and sysconfig.get_platform() == 'win-amd64' and not sysconfig.get_config_var('Py_GIL_DISABLED')))" 2>$null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-PortablePython {
    $ready = Join-Path $portableDir '.ready'
    if ((Test-Path -LiteralPath $ready -PathType Leaf) -and (Test-Python $portablePython)) {
        return $portablePython
    }

    $zip = Join-Path ([IO.Path]::GetTempPath()) ("wuwa-score-python-" + [guid]::NewGuid().ToString('N') + '.zip')
    try {
        Write-Host "Downloading Python $pythonVersion (x64)..."
        Invoke-WebRequest -Uri $pythonUrl -OutFile $zip -UseBasicParsing -TimeoutSec 300
        $hashStream = [IO.File]::OpenRead($zip)
        $sha256 = [Security.Cryptography.SHA256]::Create()
        try {
            $hash = [BitConverter]::ToString($sha256.ComputeHash($hashStream)).Replace('-', '')
        } finally {
            $sha256.Dispose()
            $hashStream.Dispose()
        }
        if ($hash -ne $pythonSha256) {
            throw 'The Python ZIP does not match the official SHA-256.'
        }
        Write-Host 'Extracting the project-local Python runtime...'
        Expand-Archive -LiteralPath $zip -DestinationPath $portableDir -Force
        if (-not (Test-Python $portablePython)) {
            throw 'The extracted Python runtime did not pass validation.'
        }
        Set-Content -LiteralPath $ready -Value $pythonVersion
        return $portablePython
    } finally {
        if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
    }
}

function Install-VisualCpp {
    $installer = Join-Path ([IO.Path]::GetTempPath()) ("wuwa-score-vc14-" + [guid]::NewGuid().ToString('N') + '.exe')
    try {
        Write-Host 'Downloading the Microsoft Visual C++ x64 runtime...'
        Invoke-WebRequest -Uri 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $installer -UseBasicParsing -TimeoutSec 300
        $signature = Get-AuthenticodeSignature -LiteralPath $installer
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)CN=Microsoft Corporation(,|$)') {
            throw 'The Visual C++ installer does not have a valid Microsoft signature.'
        }
        Write-Host 'Installing the Visual C++ runtime. Windows may ask for administrator approval.'
        $process = Start-Process -FilePath $installer -ArgumentList '/install', '/quiet', '/norestart' `
            -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        if ($process.ExitCode -notin 0, 1638, 3010) {
            throw "The Visual C++ installer failed (exit $($process.ExitCode))."
        }
        if ($process.ExitCode -eq 3010) {
            Write-Host 'Windows requested a restart. If validation fails, restart and run install.cmd again.'
        }
    } finally {
        if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer }
    }
}

function Invoke-CheckedPython([string[]]$Arguments) {
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python step failed (exit $LASTEXITCODE): $($Arguments -join ' ')"
    }
}

$lock = $null
Push-Location -LiteralPath $project
try {
    $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if ($architecture -ne 'AMD64' -or [Environment]::OSVersion.Version.Major -lt 10) {
        throw 'wuwa-score requires Windows 10 or 11 on x64 (Intel or AMD).'
    }
    [void](New-Item -ItemType Directory -Path $runtimeDir -Force)
    try {
        $lock = [IO.File]::Open((Join-Path $runtimeDir 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch [IO.IOException] {
        throw 'Another wuwa-score installation is running in this folder.'
    }

    if ((Test-Path -LiteralPath (Join-Path $venvDir 'pyvenv.cfg')) -and (Test-Python $python)) {
        Write-Host 'Reusing the project virtual environment.'
    } else {
        $basePython = Get-PortablePython
        if (Test-Path -LiteralPath $venvDir) {
            $backup = '.venv.previous-' + [guid]::NewGuid().ToString('N')
            Rename-Item -LiteralPath $venvDir -NewName $backup
            Write-Host "Saved the old environment as $backup."
        }
        Write-Host 'Creating the project virtual environment...'
        & $basePython -I -m venv $venvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Python $python)) {
            throw 'Could not create the project virtual environment.'
        }
    }

    & $python -I -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('pip') is None)"
    if ($LASTEXITCODE -ne 0) {
        Invoke-CheckedPython @('-I', '-m', 'ensurepip', '--upgrade')
    }

    # The v5 and v6 distributions install into the same onnxocr package.
    & $python -I -c "from importlib.metadata import distributions; import sys; sys.exit(not any(p.metadata['Name'] == 'onnxocr-ppocrv5' for p in distributions()))"
    if ($LASTEXITCODE -eq 0) {
        Invoke-CheckedPython @('-I', '-m', 'pip', 'uninstall', '-y', 'onnxocr-ppocrv5', 'onnxocr-ppocrv6')
    }

    Write-Host 'Installing project dependencies...'
    Invoke-CheckedPython @('-I', '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'requirements.txt')
    Invoke-CheckedPython @('-I', '-m', 'pip', 'check')

    $nativeCheck = @'
import sys
try:
    import cv2
    from openvino import Core
    Core().get_versions('CPU')
except ModuleNotFoundError:
    raise
except (ImportError, OSError, RuntimeError) as error:
    if isinstance(error, RuntimeError) and 'cannot load library' not in str(error).lower():
        raise
    print(error)
    sys.exit(3)
'@
    & $python -I -c $nativeCheck
    if ($LASTEXITCODE -eq 3) {
        Install-VisualCpp
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'Could not import OpenCV or OpenVINO.'
    }

    Write-Host 'Checking the GUI runtime and running a local OCR smoke test...'
    $smokeTest = @'
from tkinter import Tcl
from PIL import Image
from wuwa_score.ocr import EchoReader

Tcl()
EchoReader().read(Image.new('RGB', (640, 360)))
'@
    Invoke-CheckedPython @('-E', '-c', $smokeTest)
    Write-Host 'Installation complete. Double-click start.cmd to launch wuwa-score.'
} catch {
    [Console]::Error.WriteLine("Installation failed: $($_.Exception.Message)")
    exit 1
} finally {
    if ($null -ne $lock) { $lock.Dispose() }
    Pop-Location
}
