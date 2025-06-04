@echo off
setlocal EnableDelayedExpansion

set hosts=8.8.8.8 1.1.1.1 google.com
set timeout=2
set internet=false

for %%h in (%hosts%) do (
    ping -n 1 -w !timeout! %%h >nul 2>&1 && set internet=true
    if !internet!==true goto :check_done
)

:check_done
if %internet%==true (
    docker compose pull
) else (
    echo No internet connection detected.
    echo Skipping pull operation.
)

echo Starting containers...
docker compose up -d --build

endlocal