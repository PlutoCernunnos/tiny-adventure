# Create a desktop shortcut to launch_game.vbs in this folder
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$target = Join-Path $scriptDir 'launch_game.vbs'
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Tiny Adventure.lnk'
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $target
$Shortcut.WorkingDirectory = $scriptDir
$Shortcut.Save()
Write-Host "Shortcut created on your Desktop: $shortcutPath"
