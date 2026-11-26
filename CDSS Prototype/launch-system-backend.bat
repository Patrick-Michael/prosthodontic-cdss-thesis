cd /d "%~dp0"

call ".venv\Scripts\activate.bat"
set "CDSS_GODOT_EXECUTABLE=%~dp0Godot\Godot_v4.7.2-stable_win64.exe"
set "CDSS_GODOT_PROJECT=%~dp0cdss-frontend"
python -m uvicorn app_with_godot:app --app-dir cdss_core --host 127.0.0.1 --port 8201
cmd