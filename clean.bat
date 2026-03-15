@echo off
echo Cleaning project...

rmdir /s /q dist
rmdir /s /q build
rmdir /s /q telebridge.egg-info
rmdir /s /q .pytest_cache

for /r %%i in (__pycache__) do rmdir /s /q "%%i"

del /s /q *.pyc
del /s /q *.pyo

echo Done cleaning project.
pause
