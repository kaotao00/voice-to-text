Set shell = CreateObject("WScript.Shell")
scriptPath = Replace(WScript.ScriptFullName, "start_codex_voice_watcher.vbs", "codex_voice_watcher.ps1")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & scriptPath & """", 0, False
