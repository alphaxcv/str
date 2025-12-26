import os
import subprocess

os.chmod("start.sh", 0o755)
subprocess.run(["/bin/bash", "./start.sh"])