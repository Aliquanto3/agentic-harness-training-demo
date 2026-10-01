<#
Empêche la mise en veille du PC et l'extinction de l'écran tant que ce script tourne,
sans droits d'administrateur : il pose l'état ES_CONTINUOUS | ES_SYSTEM_REQUIRED |
ES_DISPLAY_REQUIRED (la méthode des utilitaires « caffeine ») et le renouvelle chaque minute.

Usage, dans une fenêtre PowerShell à part, laissée ouverte :
    powershell -ExecutionPolicy Bypass -File tools\keep_awake.ps1
Arrêt : Ctrl+C ou fermer la fenêtre ; l'état normal revient aussitôt.
Le script écrit son PID dans %TEMP%\wavestack-keep-awake.pid pour qu'on puisse vérifier qu'il tourne.
#>

Add-Type -Namespace WaveStack -Name Power -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@

$ES_CONTINUOUS = [uint32]0x80000000
$ES_SYSTEM_REQUIRED = [uint32]0x00000001
$ES_DISPLAY_REQUIRED = [uint32]0x00000002
$flags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED

$pidFile = Join-Path $env:TEMP "wavestack-keep-awake.pid"
Set-Content -Path $pidFile -Value $PID -Encoding ascii

try {
    while ($true) {
        $previous = [WaveStack.Power]::SetThreadExecutionState($flags)
        if ($previous -eq 0) { Write-Warning "SetThreadExecutionState a échoué (code $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))." }
        Write-Host ("{0:HH:mm:ss}  veille et écran bloqués (PID {1})" -f (Get-Date), $PID)
        Start-Sleep -Seconds 60
    }
}
finally {
    [void][WaveStack.Power]::SetThreadExecutionState($ES_CONTINUOUS)
    Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
}
