param(
    [string]$Exe = (Join-Path $PSScriptRoot "..\dist\CADtoCAE_Step02_PartScript\CADtoCAE_Step02_PartScript.exe")
)

$ErrorActionPreference = "Stop"
if (-not ("Step02SmokeWindows" -as [type])) {
    Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class Step02SmokeWindows {
    private delegate bool Callback(IntPtr window, IntPtr data);
    [DllImport("user32.dll")] private static extern bool EnumWindows(Callback callback, IntPtr data);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr window, StringBuilder text, int count);
    public static string[] Titles(int processId) {
        var titles = new List<string>();
        EnumWindows((window, data) => {
            uint owner;
            GetWindowThreadProcessId(window, out owner);
            if (owner == processId) {
                var text = new StringBuilder(1024);
                GetWindowText(window, text, text.Capacity);
                if (text.Length > 0) titles.Add(text.ToString());
            }
            return true;
        }, IntPtr.Zero);
        return titles.ToArray();
    }
}
'@
}
$ExePath = (Resolve-Path -LiteralPath $Exe).Path
$Process = Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path $ExePath -Parent) -WindowStyle Hidden -PassThru
try {
    $Deadline = (Get-Date).AddSeconds(30)
    $Started = $false
    while ((Get-Date) -lt $Deadline) {
        Start-Sleep -Milliseconds 250
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "Step02 exited during startup: $($Process.ExitCode)"
        }
        $Titles = [Step02SmokeWindows]::Titles($Process.Id)
        $Title = $Titles | Where-Object { $_ -like "CADtoCAE Step02 Part*" } | Select-Object -First 1
        if ($Title) {
            $Started = $true
            break
        }
        if ($Titles | Where-Object { $_ -like "*Unhandled exception*" }) {
            throw "Step02 opened a PyInstaller error dialog."
        }
    }
    if (-not $Started) { throw "Step02 GUI title was not detected within 30 seconds." }
    Start-Sleep -Seconds 3
    $Process.Refresh()
    if ($Process.HasExited -or [Step02SmokeWindows]::Titles($Process.Id) -notcontains $Title) {
        throw "Step02 did not remain open after startup."
    }
    Write-Output "PASS: PID=$($Process.Id); title=$Title; GUI remained open."
} finally {
    $Process.Refresh()
    if (-not $Process.HasExited) {
        [void]$Process.CloseMainWindow()
        if (-not $Process.WaitForExit(5000)) { $Process.Kill() }
    }
    $Process.Dispose()
}
