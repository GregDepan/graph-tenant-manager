@echo off
REM ============================================================
REM  Graph Tenant Manager — Lancement sans compilation
REM  Si Python n'est pas installe, il sera propose automatiquement.
REM ============================================================
title Graph Tenant Manager
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python n'a pas ete trouve.
    echo.
    echo Installation automatique proposee (winget).
    echo Si rien ne se passe, installez Python depuis https://python.org
    echo en cochant "Add Python to PATH", puis relancez ce fichier.
    echo.
    winget install -e --id Python.Python.3.11 --silent
    if errorlevel 1 (
        echo.
        echo Echec de l'installation auto. Installez Python manuellement :
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo Verification des dependances (premiere fois : ~2 minutes)...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo Echec d'installation des dependances. Verifiez votre connexion internet.
    pause
    exit /b 1
)

echo Demarrage de Graph Tenant Manager...
start "" pythonw main.py
exit /b 0