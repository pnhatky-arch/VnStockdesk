use scripting additions
on run
    try
        set appPath to POSIX path of (path to me)
        set projectRoot to appPath & ".."
        set rawPythonPath to (POSIX path of (path to home folder)) & "Library/Application Support/VnStockDesk/runtime/.venv/bin/python"
        set rawLauncherPath to projectRoot & "/desktop_launcher.py"
        set pythonPath to quoted form of rawPythonPath
        set launcherPath to quoted form of rawLauncherPath
        do shell script (pythonPath & " " & launcherPath & " >/dev/null 2>&1 &")
    on error errorMessage
        display dialog "Không thể mở VnStockDesk: " & errorMessage buttons {"OK"} default button "OK" with icon stop
    end try
end run
