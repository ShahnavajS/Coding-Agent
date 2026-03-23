$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$env:NODE_PATH = "$PWD\frontend\node_modules"
& ".\node_modules\.bin\electron-forge.cmd" "package"
