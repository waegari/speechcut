' Headless launcher for PM2 on Windows (no console window).
' wscript waits for pythonw so PM2 can monitor and restart the process.

Option Explicit

Dim fso, shell, scriptDir, rootDir, pythonw, cmd, exitCode

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("Wscript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
rootDir = fso.GetParentFolderName(scriptDir)
pythonw = rootDir & "\.venv\Scripts\pythonw.exe"

If Not fso.FileExists(pythonw) Then
  WScript.StdErr.WriteLine "pythonw not found: " & pythonw
  WScript.Quit 1
End If

shell.CurrentDirectory = rootDir
cmd = """" & pythonw & """ -m uvicorn eve.api.main:app --host 127.0.0.1 --port 8001"
' 0 = hide window, True = block until pythonw exits (PM2 supervision)
exitCode = shell.Run(cmd, 0, True)
WScript.Quit exitCode
