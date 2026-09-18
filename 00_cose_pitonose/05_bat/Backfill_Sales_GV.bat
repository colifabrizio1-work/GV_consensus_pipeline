@echo off
setlocal

rem One-off: backfill dello storico sales per i datest entrati in scope dopo la
rem costruzione dei parquet annuali (split UK 2026-09: 027150 / 027300 / 028000).
rem Sorgente e datest arrivano da scarichi.sales_historical_uk in datasets.json.
rem Rilanciarlo e' idempotente: riscrive solo (datest del CSV) x (settimane del CSV).

rem Ambiente Python condiviso per utente (Hub, WAFER, GV, RPA, pipeline): 05 - bat\00 - shared env.
call "\\luxnt\Retail\AAA_Retail\zzzz_Coli\Script\05 - bat\00 - shared env\shared_env.cmd"
if errorlevel 1 (
    echo Ambiente Python condiviso non pronto.
    exit /b 9001
)
set "PYTHON_EXE=%SHARED_PY%"
set "SCRIPT_PATH=\\luxnt\Retail\AAA_Retail\Demand Management GV\10. Automatizzazione file consensus\00_cose_pitonose\03_script\backfill_sales_gv.py"

"%PYTHON_EXE%" -u "%SCRIPT_PATH%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo Backfill Sales GV failed with exit code %EXIT_CODE%.
) else (
    echo Backfill Sales GV completed successfully.
)

exit /b %EXIT_CODE%
