@echo off
REM Script de compilation pour Graph Tenant Manager
REM Crée un exécutable Windows autonome (.exe)

echo ============================================================
echo   Graph Tenant Manager - Compilation Windows
echo ============================================================
echo.

REM Vérifier que l'environnement virtuel existe
if not exist venv (
    echo [ERREUR] Environnement virtuel non trouve!
    echo.
    echo Executez d'abord install.bat
    echo.
    pause
    exit /b 1
)

REM Activer l'environnement virtuel
echo Activation de l'environnement virtuel...
call venv\Scripts\activate.bat

REM Vérifier PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installation de PyInstaller...
    pip install pyinstaller
)

echo.
echo Compilation en cours...
echo Cela peut prendre plusieurs minutes.
echo.

REM Nettoyer les anciennes builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Compiler avec PyInstaller
pyinstaller --onefile ^
    --windowed ^
    --name "GraphTenantManager" ^
    --icon=NONE ^
    --add-data "config.cfg.example;." ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=azure.identity ^
    --hidden-import=msgraph ^
    main.py

if errorlevel 1 (
    echo.
    echo [ERREUR] La compilation a echoue!
    echo.
    echo Verifiez les messages d'erreur ci-dessus.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Compilation terminee avec succes!
echo.
echo L'executable se trouve dans: dist\GraphTenantManager.exe
echo.

REM Créer un raccourci
echo Creation du lanceur...
(
echo @echo off
echo cd /d "%%~dp0"
echo GraphTenantManager.exe %%*
) > dist\lancer.bat

echo.
echo ============================================================
echo   Build terminee!
echo ============================================================
echo.
echo Fichiers crees:
echo   - dist\GraphTenantManager.exe (application autonome)
echo   - dist\lancer.bat (script de lancement)
echo.
echo Vous pouvez copier le dossier 'dist' entier vers n'importe
echo quel PC Windows. Aucune installation Python requise!
echo.
echo IMPORTANT: N'oubliez pas de configurer config.cfg avec
echo votre Client ID Azure avant de distribuer.
echo.
pause
