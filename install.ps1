#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Installe uv, WaveStack et le modele Qwen par defaut sans droits administrateur,
    puis lance l'application. Idempotent : relancer ce script ne retelecharge ni le
    projet ni le modele s'ils sont deja presents.

.PARAMETER InstallDir
    Dossier du projet. Par defaut : le dossier du script s'il contient deja
    pyproject.toml (clone ou zip existant), sinon "<Documents>\WaveStack".

.PARAMETER DataDir
    Dossier de donnees (venv, caches, modeles). Par defaut WAVESTACK_DATA_DIR ou
    "%LOCALAPPDATA%\WaveStack". Reste toujours hors de $InstallDir et de Documents.

.PARAMETER UvInstallDir
    Dossier d'installation de uv (passe a son installeur via UV_INSTALL_DIR).

.PARAMETER NoLaunch
    N'ouvre pas l'application a la fin (utile pour les tests).

.PARAMETER DryRun
    Affiche les dossiers resolus sans rien installer, cloner, telecharger ni lancer.
#>
[CmdletBinding()]
param(
    [string]$InstallDir,
    [string]$DataDir,
    [string]$UvInstallDir,
    [switch]$NoLaunch,
    [switch]$DryRun
)

# Corps dans un bloc enfant : sous `irm | iex`, ses variables et preferences ne restent
# pas dans la session de l'utilisateur.
& {
    $ErrorActionPreference = 'Stop'

    # Memes valeurs que README.md (une seule source de verite : voir tests/test_installers.py)
    $QwenUrl  = 'https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf'
    $QwenFile = 'Qwen3.5-2B-Q4_K_M.gguf'
    $RepoUrl  = 'https://github.com/Aliquanto3/agentic-harness-training-demo.git'
    $ZipUrl   = 'https://github.com/Aliquanto3/agentic-harness-training-demo/archive/refs/heads/main.zip'
    $ZipRoot  = 'agentic-harness-training-demo-main'

    # -- Dossier du projet : sur place si on est deja dans un clone ou un zip, sinon un
    #    dossier visible sous Documents (chemin reel, eventuellement redirige par OneDrive).
    if (-not $InstallDir) {
        if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'pyproject.toml'))) {
            $InstallDir = $PSScriptRoot
        } else {
            $documents = [Environment]::GetFolderPath('MyDocuments')
            $InstallDir = Join-Path $documents 'WaveStack'
        }
    }

    # -- Dossier de donnees : venv, caches et modeles, jamais sous Documents/OneDrive.
    if (-not $DataDir) {
        $DataDir = $env:WAVESTACK_DATA_DIR
        if (-not $DataDir) { $DataDir = Join-Path $env:LOCALAPPDATA 'WaveStack' }
    }
    $VenvDir   = Join-Path $DataDir 'venv'
    $CacheDir  = Join-Path $DataDir 'uv-cache'
    $ModelsDir = Join-Path $DataDir 'models'
    $ModelPath = Join-Path $ModelsDir $QwenFile

    Write-Host "Projet      : $InstallDir"
    Write-Host "Donnees     : $DataDir"
    Write-Host "Modele Qwen : $ModelPath"

    if ($DryRun) {
        Write-Host "(mode a blanc : aucune commande reseau ou d'installation executee)"
        return
    }

    # -- uv, dans le profil utilisateur, sans droits administrateur.
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host 'Installation de uv...'
        if ($UvInstallDir) { $env:UV_INSTALL_DIR = $UvInstallDir }
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        if ($LASTEXITCODE -ne 0) { throw "L'installation de uv a echoue (code $LASTEXITCODE)." }
        $uvBin = if ($UvInstallDir) { $UvInstallDir } else { Join-Path $env:USERPROFILE '.local\bin' }
        $env:PATH = "$uvBin;$env:PATH"
    }

    # -- Projet : clone si absent ; inchange s'il est deja la (idempotent).
    if (-not (Test-Path (Join-Path $InstallDir 'pyproject.toml'))) {
        Write-Host "Recuperation de WaveStack dans $InstallDir..."
        $parent = Split-Path -Parent $InstallDir
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        if (Get-Command git -ErrorAction SilentlyContinue) {
            git clone $RepoUrl $InstallDir
            if ($LASTEXITCODE -ne 0) { throw "git clone a echoue (code $LASTEXITCODE)." }
        } else {
            # Pas de git sur le poste : archive zip de la branche main, sans droits admin.
            $zip = Join-Path $env:TEMP 'wavestack-main.zip'
            Invoke-WebRequest -UseBasicParsing $ZipUrl -OutFile $zip
            Expand-Archive -LiteralPath $zip -DestinationPath $parent -Force
            Rename-Item -LiteralPath (Join-Path $parent $ZipRoot) (Split-Path -Leaf $InstallDir)
            [IO.File]::Delete($zip)  # Remove-Item refuse les chemins courts 8.3 de %TEMP%
        }
    } else {
        Write-Host "WaveStack deja present dans $InstallDir, pas de nouveau clone."
    }

    # -- Modele Qwen : telecharge si absent (idempotent).
    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    if (-not (Test-Path $ModelPath)) {
        Write-Host 'Telechargement du modele Qwen (1,3 Go)...'
        $ProgressPreference = 'SilentlyContinue'
        # Telechargement vers .part puis renommage : une coupure ne laisse pas un faux modele.
        Invoke-WebRequest -UseBasicParsing $QwenUrl -OutFile "$ModelPath.part"
        Move-Item -Force -LiteralPath "$ModelPath.part" $ModelPath
    } else {
        Write-Host 'Modele Qwen deja present, pas de nouveau telechargement.'
    }

    if (-not $NoLaunch) {
        # Venv et caches sous le dossier de donnees, jamais sous Documents ; l'appli lit ses
        # modeles dans le meme dossier. Variables retirees ensuite (session de `irm | iex`).
        $saved = @{}
        $vars = @{ UV_PROJECT_ENVIRONMENT = $VenvDir; UV_CACHE_DIR = $CacheDir; WAVESTACK_DATA_DIR = $DataDir }
        foreach ($k in $vars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); Set-Item "env:$k" $vars[$k] }
        Push-Location $InstallDir
        try {
            Write-Host 'Lancement de WaveStack...'
            & uv run wavestack
        } finally {
            Pop-Location
            foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
        }
    }

    Write-Host ''
    Write-Host 'Pour relancer WaveStack plus tard : reexecutez install.bat (ou install.ps1) dans ce dossier.'
}
