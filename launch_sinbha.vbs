Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir
' Run npm start completely hidden (0 = hide window, False = don't wait)
WshShell.Run "cmd /c npm start", 0, False
