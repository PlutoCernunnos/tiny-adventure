Set objFSO = CreateObject("Scripting.FileSystemObject")
scriptPath = objFSO.GetParentFolderName(WScript.ScriptFullName)
cmd = "pythonw """ & scriptPath & "\mane game.py"""
CreateObject("WScript.Shell").Run cmd, 0, false
