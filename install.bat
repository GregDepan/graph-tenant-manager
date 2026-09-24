@echo off
REM Script d'installation pour Graph Tenant Manager sur Windows
REM Exécuter en tant qu'administrateur si nécessaire

echo ============================================================
echo   Graph Tenant Manager - Installation Windows
echo ============================================================
echo.

REM Vérifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe!
    echo.
    echo Veuillez installer Python 3.10 ou superieur depuis:
    echo https://www.python.org/downloads/
    echo.
    echo Cochez "Add Python to PATH" pendant l'installation.
    echo.
    pause
    exit /b 1
)

echo [OK] Python detecte
python --version
echo.

REM Créer un environnement virtuel
echo Creation de l'environnement virtuel...
python -m venv venv
if errorlevel 1 (
    echo [ERREUR] Echec de creation de l'environnement virtuel
    pause
    exit /b 1
)

echo [OK] Environnement virtuel cree
echo.

REM Activer l'environnement virtuel
echo Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

REM Installer les dépendances
echo Installation des dependances...
echo Cela peut prendre quelques minutes...
echo.

pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo [ERREUR] Echec de l'installation des dependances
    echo.
    echo Essayez d'exécuter ce script en tant qu'administrateur.
    pause
    exit /b 1
)

echo.
echo [OK] Dependances installees avec succes
echo.

REM Copier le fichier de configuration
if not exist config.cfg (
    echo Creation du fichier de configuration...
    copy config.cfg.example config.cfg
    echo [OK] config.cfg cree
    echo.
    echo IMPORTANT: Editez config.cfg avec votre Client ID Azure!
    echo.
)

REM Créer le dossier de logs
if not exist logs mkdir logs
echo [OK] Dossier logs cree

echo.
echo ============================================================
echo   Installation terminee avec succes!
echo ============================================================
echo.
echo Prochaines etapes:
echo.
echo 1. Editez config.cfg avec votre Client ID Azure
echo    (voir les instructions dans le fichier)
echo.
echo 2. Lancez l'application:
echo    - Double-cliquez sur start.bat
echo    - OU exécutez: venv\Scripts\activate ^&^& python main.py
echo.
echo 3. Pour créer un exécutable Windows (.exe):
echo    - Exécutez: build.bat
echo.
echo ============================================================
echo.
pause
