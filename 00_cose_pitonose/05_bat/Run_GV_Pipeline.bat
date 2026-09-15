@echo off
setlocal EnableExtensions

set "BASE_DIR=\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus"
set "SCRIPT_DIR=%BASE_DIR%\00_cose_pitonose\03_script"
set "CONFIG_DIR=%BASE_DIR%\00_cose_pitonose\02_config"
rem Ambiente Python condiviso con Retail Analysis Hub, WAFER e RPA SAP (un solo setup per utente).
set "SHARED_ENV=\\luxnt\Retail\AAA_Retail\zzzz_Coli\Script\05 - bat\00 - shared env\shared_env.cmd"
set "VENV_PY="
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
echo Verifica ambiente Python condiviso...
call "%SHARED_ENV%"
if errorlevel 1 exit /b 1
set "VENV_PY=%SHARED_PY%"
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

