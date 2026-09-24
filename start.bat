@echo off
REM Script de lancement rapide pour Graph Tenant Manager

echo Lancement de Graph Tenant Manager...
echo.

if not exist venv (
    echo [ERREUR] Environnement virtuel non trouve!
    echo.
    echo Executez d'abord install.bat pour installer l'application.
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python main.py

if errorlevel 1 (
    echo.
    echo [ERREUR] L'application a rencontre une erreur.
    echo.
    echo Verifiez que config.cfg est correctement configure.
    echo.
    pause
)
