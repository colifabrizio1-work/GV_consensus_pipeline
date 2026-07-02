@echo off
setlocal

set "PYTHON_EXE=C:\Users\colifa\AppData\Local\Programs\Python\Python312\python.exe"
set "SCRIPT_PATH=\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\update_forecast_gv.py"

"%PYTHON_EXE%" -u "%SCRIPT_PATH%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo Update Forecast GV failed with exit code %EXIT_CODE%.
) else (
    echo Update Forecast GV completed successfully.
)

exit /b %EXIT_CODE%
