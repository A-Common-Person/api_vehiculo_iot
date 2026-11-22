param(
    [ValidateSet('administrador', 'usuario')]
    [string]$CrearCuenta,
    [string]$IPRedLocal,
    [switch]$PrepararDispositivo
)

$ErrorActionPreference = 'Stop'
$proyecto = Split-Path -Parent $PSScriptRoot
$python = Join-Path $proyecto '.venv\Scripts\python.exe'
if ($PrepararDispositivo -and !$IPRedLocal) {
    throw 'Indica -IPRedLocal con la IPv4 privada de esta computadora.'
}
if (!(Test-Path -LiteralPath $python)) {
    throw 'No se encontro .venv del backend. Instala las dependencias del proyecto.'
}

$servidor = (Read-Host 'Endpoint de instancia-rds-iot-43-pruebas').Trim()
if ($servidor -notmatch '^instancia-rds-iot-43-pruebas\.[a-z0-9-]+\.us-east-1\.rds\.amazonaws\.com$') {
    throw 'Se requiere el endpoint completo de RDS de pruebas en us-east-1.'
}
$usuario = (Read-Host 'Usuario MySQL [admin]').Trim()
if (!$usuario) { $usuario = 'admin' }

$certificado = Join-Path $env:TEMP 'iot43-rds-us-east-1-bundle.pem'
$certificadoUri = 'https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem'
Invoke-WebRequest -UseBasicParsing -Uri $certificadoUri -OutFile $certificado

$configuracion = @{
    ADMINISTRACION_HABILITADA = 'true'
    DB_HOST = $servidor
    DB_PORT = '3306'
    DB_USER = $usuario
    DB_NAME = 'vehiculo_iot'
    DB_SSL_CA = $certificado
    DB_PASSWORD = $null
}

$anteriores = @{}
foreach ($clave in $configuracion.Keys) {
    $anteriores[$clave] = [Environment]::GetEnvironmentVariable($clave, 'Process')
}

Push-Location -LiteralPath $proyecto
try {
    $secreto = Read-Host 'Contrasena de MySQL de la copia de pruebas' -AsSecureString
    $puntero = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secreto)
    try {
        $configuracion.DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($puntero)
        foreach ($clave in $configuracion.Keys) {
            [Environment]::SetEnvironmentVariable($clave, $configuracion[$clave], 'Process')
        }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($puntero)
        $secreto.Dispose()
        $configuracion.DB_PASSWORD = $null
    }

    if ($CrearCuenta) {
        & $python -m app.crear_usuario --rol $CrearCuenta
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la cuenta de pruebas.' }
    }

    Write-Output 'Swagger local en http://127.0.0.1:8001/docs'
    if ($IPRedLocal) {
        $argumentos = @('--ip-red-local', $IPRedLocal)
        if ($PrepararDispositivo) {
            $carpetaSketch = Join-Path (Split-Path -Parent $proyecto) 'Carrito_WS'
            $argumentos += @('--preparar-archivo', (Join-Path $carpetaSketch 'IoT43Local.h'))
        }
        & $python -m app.ensayo_hardware @argumentos
    } else {
        & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --ws-max-size 4096 --ws-max-queue 4 --ws-per-message-deflate false
    }
    if ($LASTEXITCODE -ne 0) { throw 'FastAPI termino con un error.' }
} finally {
    foreach ($clave in $anteriores.Keys) {
        [Environment]::SetEnvironmentVariable($clave, $anteriores[$clave], 'Process')
    }
    Pop-Location
}
