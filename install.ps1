# Script PowerShell d'installation pour Graph Tenant Manager
# Exécuter dans PowerShell (peut nécessiter des droits admin)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Graph Tenant Manager - Installation Windows (PowerShell)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier Python
Write-Host "[1/5] Vérification de Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python détecté: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERREUR] Python n'est pas installé!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Veuillez installer Python 3.10+ depuis:" -ForegroundColor Yellow
    Write-Host "https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "IMPORTANT: Cochez 'Add Python to PATH' pendant l'installation" -ForegroundColor Yellow
    Read-Host "Appuyez sur Entrée pour quitter"
    exit 1
}

# Créer l'environnement virtuel
Write-Host ""
Write-Host "[2/5] Création de l'environnement virtuel..." -ForegroundColor Yellow
python -m venv venv
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERREUR] Échec de création du venv" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée"
    exit 1
}
Write-Host "[OK] Environnement virtuel créé" -ForegroundColor Green

# Activer le venv
Write-Host ""
Write-Host "[3/5] Activation de l'environnement..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Installer les dépendances
Write-Host ""
Write-Host "[4/5] Installation des dépendances..." -ForegroundColor Yellow
Write-Host "Cela peut prendre quelques minutes..." -ForegroundColor Gray
pip install --upgrade pip | Out-Null
pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERREUR] Échec de l'installation des dépendances" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée"
    exit 1
}
Write-Host "[OK] Dépendances installées" -ForegroundColor Green

# Créer le fichier de config
Write-Host ""
Write-Host "[5/5] Configuration..." -ForegroundColor Yellow
if (-not (Test-Path "config.cfg")) {
    Copy-Item "config.cfg.example" "config.cfg"
    Write-Host "[OK] config.cfg créé" -ForegroundColor Green
    Write-Host ""
    Write-Host "IMPORTANT: Éditez config.cfg avec votre Client ID Azure!" -ForegroundColor Yellow
} else {
    Write-Host "[INFO] config.cfg existe déjà" -ForegroundColor Gray
}

# Créer le dossier logs
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
    Write-Host "[OK] Dossier logs créé" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Installation terminée avec succès!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Prochaines étapes:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Éditez config.cfg avec votre Client ID Azure" -ForegroundColor White
Write-Host "   (voir les instructions dans le fichier)" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Lancez l'application:" -ForegroundColor White
Write-Host "   - Double-cliquez sur start.bat" -ForegroundColor Gray
Write-Host "   - OU: .\venv\Scripts\Activate.ps1; python main.py" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Pour créer un exécutable (.exe):" -ForegroundColor White
Write-Host "   - Exécutez: .\build.bat" -ForegroundColor Gray
Write-Host ""

Read-Host "Appuyez sur Entrée pour quitter"
