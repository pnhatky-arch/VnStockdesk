#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    const char *name = (argc > 0 && argv[0]) ? argv[0] : "";
    const char *action = (strstr(name, "Stop") || strstr(name, "STOP")) ? "stop" : "start";
    setenv("VNSTOCKDESK_LAUNCH_ACTION", action, 1);
    const char *command =
        "project=''; "
        "for candidate in \"$HOME/Drive của tôi/VnStockDesk/System\" \"$HOME/My Drive/VnStockDesk/System\" "
        "\"$HOME\"/Library/CloudStorage/GoogleDrive-*/\"My Drive/VnStockDesk/System\"; do "
        "if [ -f \"$candidate/desktop_launcher.py\" ]; then project=\"$candidate\"; break; fi; done; "
        "python_bin=\"$HOME/Library/Application Support/VnStockDesk/runtime/.venv/bin/python\"; "
        "log_file=\"$HOME/Library/Application Support/VnStockDesk/runtime/native_launcher.log\"; "
        "mkdir -p \"$(dirname \"$log_file\")\"; "
        "if [ -z \"$project\" ]; then echo 'Không tìm thấy VnStockDesk/System' >>\"$log_file\"; exit 2; fi; "
        "if [ ! -x \"$python_bin\" ]; then echo 'Không tìm thấy Python runtime' >>\"$log_file\"; exit 3; fi; "
        "if [ \"$VNSTOCKDESK_LAUNCH_ACTION\" = stop ]; then "
        "exec \"$python_bin\" \"$project/desktop_launcher.py\" --stop >>\"$log_file\" 2>&1; "
        "else exec \"$python_bin\" \"$project/desktop_launcher.py\" >>\"$log_file\" 2>&1; fi";
    execl("/bin/zsh", "zsh", "-lc", command, (char *)0);
    return 127;
}
