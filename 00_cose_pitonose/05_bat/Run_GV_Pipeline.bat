@echo off
setlocal EnableExtensions

set "BASE_DIR=\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus"
set "SCRIPT_DIR=%BASE_DIR%\00_cose_pitonose\03_script"
set "CONFIG_DIR=%BASE_DIR%\00_cose_pitonose\02_config"
set "VENV_DIR=%LOCALAPPDATA%\GV_Consensus_Pipeline\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%CONFIG_DIR%\requirements_gv.txt"
set "FORECAST_SCRIPT=%SCRIPT_DIR%\update_forecast_gv.py"
set "SALES_SCRIPT=%SCRIPT_DIR%\update_sales_gv.py"
set "CONSENSUS_SCRIPT=%SCRIPT_DIR%\generate_consensus_frames_gv.py"

call :ENSURE_ENV
if errorlevel 1 goto FAILED

:MENU
cls
echo ================================================
echo        GV Pipeline - Demand Management
echo ================================================
echo.
echo  1. Aggiorna forecast
echo  2. Aggiorna sales
echo  3. Crea consensus
echo  4. Aggiorna forecast + sales e crea consensus
echo.
echo  Q. Esci
echo.
set /p "CHOICE=Seleziona opzione: "

if /I "%CHOICE%"=="1" goto FORECAST_ONLY
if /I "%CHOICE%"=="2" goto SALES_ONLY
if /I "%CHOICE%"=="3" goto CONSENSUS_ONLY
if /I "%CHOICE%"=="4" goto FULL
if /I "%CHOICE%"=="Q" goto END

echo.
echo Opzione non valida.
pause
goto MENU

:ENSURE_ENV
echo.
echo Verifica ambiente Python GV...
if exist "%VENV_PY%" goto CHECK_PACKAGES

echo Creo venv utente in: %VENV_DIR%
py -3 -m venv "%VENV_DIR%" >nul 2>&1
if errorlevel 1 (
    python -m venv "%VENV_DIR%" >nul 2>&1
)
if not exist "%VENV_PY%" (
    echo ERRORE: Python non trovato o creazione venv fallita.
    echo Installare Python 3 oppure verificare il path con questi comandi PowerShell:
    echo   py -0p
    echo   where.exe python
    exit /b 1
)

:CHECK_PACKAGES
"%VENV_PY%" -c "import pandas, openpyxl, pyarrow" >nul 2>&1
if not errorlevel 1 exit /b 0

echo Installo/aggiorno pacchetti GV da requirements...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
    echo ERRORE: installazione pacchetti fallita.
    echo Verificare connessione/pip corporate e riprovare.
    exit /b 1
)
"%VENV_PY%" -c "import pandas, openpyxl, pyarrow" >nul 2>&1
if errorlevel 1 (
    echo ERRORE: pacchetti Python ancora non disponibili dopo installazione.
    exit /b 1
)
exit /b 0


:FORECAST_ONLY
call :RUN_FORECAST
if errorlevel 1 goto FAILED
goto DONE

:SALES_ONLY
call :RUN_SALES
if errorlevel 1 goto FAILED
goto DONE

:CONSENSUS_ONLY
call :RUN_CONSENSUS
if errorlevel 1 goto FAILED
goto DONE

:FULL
call :RUN_FORECAST
if errorlevel 1 goto FAILED
call :RUN_SALES
if errorlevel 1 goto FAILED
call :RUN_CONSENSUS
if errorlevel 1 goto FAILED
goto DONE

:RUN_FORECAST
echo.
echo ------------------------------------------------
echo Aggiornamento forecast GV
echo ------------------------------------------------
"%VENV_PY%" "%FORECAST_SCRIPT%"
exit /b %ERRORLEVEL%

:RUN_SALES
echo.
echo ------------------------------------------------
echo Aggiornamento sales GV
echo ------------------------------------------------
"%VENV_PY%" "%SALES_SCRIPT%" --source update
exit /b %ERRORLEVEL%

:RUN_CONSENSUS
echo.
echo ------------------------------------------------
echo Creazione consensus GV
echo ------------------------------------------------
"%VENV_PY%" "%CONSENSUS_SCRIPT%"
exit /b %ERRORLEVEL%

:FAILED
echo.
echo Pipeline interrotta per errore.
pause
exit /b 1

:DONE
echo.
echo Operazione completata.
pause
goto END

:END
endlocal

