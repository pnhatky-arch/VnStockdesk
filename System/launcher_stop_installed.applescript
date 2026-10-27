use scripting additions
on run
    try
        set projectRoot to "/Users/phamgia/Drive của tôi/VnStockDesk/System"
        set rawPythonPath to (POSIX path of (path to home folder)) & "Library/Application Support/VnStockDesk/runtime/.venv/bin/python"
        set rawLauncherPath to projectRoot & "/desktop_launcher.py"
        do shell script (quoted form of rawPythonPath & " " & quoted form of rawLauncherPath & " --stop >/dev/null 2>&1")
        display notification "Dashboard đã được dừng" with title "VnStockDesk"
    on error errorMessage
        display dialog "Không thể dừng VnStockDesk: " & errorMessage buttons {"OK"} default button "OK" with icon stop
    end try
end run
