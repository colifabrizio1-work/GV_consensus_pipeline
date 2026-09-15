@echo off
setlocal

rem Ambiente Python condiviso per utente (Hub, WAFER, GV, RPA, pipeline): 05 - bat\00 - shared env.
call "\\luxnt\Retail\AAA_Retail\zzzz_Coli\Script\05 - bat\00 - shared env\shared_env.cmd"
if errorlevel 1 (
    echo Ambiente Python condiviso non pronto.
    exit /b 9001
)
set "PYTHON_EXE=%SHARED_PY%"
set "SCRIPT_PATH=\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\update_forecast_gv.py"

"%PYTHON_EXE%" -u "%SCRIPT_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo Update Forecast GV failed with exit code %EXIT_CODE%.
) else (
    echo Update Forecast GV completed successfully.
)

exit /b %EXIT_CODE%
