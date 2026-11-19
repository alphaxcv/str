import os
import sys
import time
import signal
import platform
import subprocess
import secrets
import urllib.request
import http.server
import threading
from pathlib import Path

# 配置信息
CONFIG = {
    "PASSWORD": os.getenv("PASSWORD", "789456"),
    "HY2_PORT": int(os.getenv("HY2_PORT", 37680)),
    "FRP_ADR": os.getenv("FRP_ADR", "35.212.176.118"),
    "FRP_REMOTE_PORT": int(os.getenv("FRP_REMOTE_PORT", 10058)),
    "FRP_TOKEN": os.getenv("FRP_TOKEN", "789456"),
    "FRP_PROXY_NAME": os.getenv("FRP_PROXY_NAME", secrets.token_hex(4)),
    "NZ_SERVER": os.getenv("NZ_SERVER", "newnz.seav.eu.org:443"),
    "NZ_CLIENT_SECRET": os.getenv("NZ_CLIENT_SECRET", "cRivpR7ScUwP51hJj7rLw7iCbUE6HmKg"),
    "NZ_UUID": os.getenv("NZ_UUID", "d96e3b97-5a72-4133-b078-413b603f9d98"),
    "PORT": int(os.getenv("PORT", 3000)),
}

DOWNLOAD_DIR = Path(__file__).parent.resolve()

# 架构判断
machine = platform.machine().lower()
is_arm = "arm" in machine or "aarch64" in machine

FILE_INFO = (
    {
        "https://download.hysteria.network/app/latest/hysteria-linux-arm64": "hy2",
        "https://github.com/seav1/dl/releases/download/files/nzv1-arm": "nzv1",
        "https://github.com/seav1/dl/releases/download/files/frpc-arm": "frpc",
    }
    if is_arm
    else {
        "https://download.hysteria.network/app/latest/hysteria-linux-amd64": "hy2",
        "https://github.com/seav1/dl/releases/download/files/nzv1": "nzv1",
        "https://github.com/seav1/dl/releases/download/files/frpc": "frpc",
    }
)

print(f"Detected architecture: {machine}, using {'ARM64' if is_arm else 'AMD64'} binaries.")

processes = {
    "nzv1": None,
    "hy2": None,
    "frpc": None,
}

shutting_down = False
http_server = None


def download_file(url: str, filepath: Path):
    """下载文件，带 User-Agent 和重试容错机制"""
    temp_file = filepath.with_suffix(".tmp")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response, open(temp_file, "wb") as f:
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
                f.write(chunk)
        
        if filepath.exists():
            filepath.unlink()
        temp_file.rename(filepath)
        filepath.chmod(0o755)
    except Exception as e:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except:
                pass
        raise e


def download_files():
    """遍历下载所需二进制文件"""
    for url, name in FILE_INFO.items():
        filepath = DOWNLOAD_DIR / name
        if not filepath.exists():
            print(f"Downloading {name} from {url}...")
            success = False
            for i in range(1, 4):
                try:
                    download_file(url, filepath)
                    success = True
                    break
                except Exception as error:
                    print(f"Download {name} failed ({i}/3): {error}")
                    if i < 3:
                        time.sleep(3)
            
            if not success:
                raise RuntimeError(f"Failed to download {name}")


def generate_ssl():
    """生成自签名 SSL 证书"""
    cert_path = DOWNLOAD_DIR / "cert.pem"
    key_path = DOWNLOAD_DIR / "key.pem"
    
    if cert_path.exists() and key_path.exists():
        return
    
    try:
        subprocess.run(
            [
                "openssl", "req",
                "-newkey", "rsa:2048",
                "-nodes",
                "-keyout", str(key_path),
                "-x509",
                "-days", "36500",
                "-out", str(cert_path),
                "-subj", "/CN=bing.com"
            ],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"SSL certificate generation failed: {e.stderr.decode().strip()}")


def create_config_files():
    """创建配置文件"""
    hy_config = f"""listen: :{CONFIG['HY2_PORT']}
tls:
  cert: {DOWNLOAD_DIR / 'cert.pem'}
  key: {DOWNLOAD_DIR / 'key.pem'}
auth:
  type: password
  password: "{CONFIG['PASSWORD']}"
masquerade:
  type: proxy
  proxy:
    url: https://bing.com
    rewriteHost: true
transport:
  udp:
    hopInterval: 30s
"""
    (DOWNLOAD_DIR / "config.yaml").write_text(hy_config, encoding="utf-8")

    frpc_config = f"""[common]
server_addr = "{CONFIG['FRP_ADR']}"
server_port = 7000
token = "{CONFIG['FRP_TOKEN']}"
[{CONFIG['FRP_PROXY_NAME']}]
type = "udp"
local_ip = "127.0.0.1"
local_port = {CONFIG['HY2_PORT']}
remote_port = {CONFIG['FRP_REMOTE_PORT']}
"""
    (DOWNLOAD_DIR / "frpc.toml").write_text(frpc_config, encoding="utf-8")


def watch_process(name, proc):
    """监控子进程输出并处理异常退出"""
    while not shutting_down:
        line = proc.stderr.readline()
        if not line:
            break
        msg = line.decode("utf-8", errors="ignore").strip()
        if msg:
            print(f"[{name}] {msg}", file=sys.stderr)
            
    proc.wait()
    processes[name] = None
    
    if not shutting_down:
        print(f"[{name}] exited, restarting in 3 seconds...", file=sys.stderr)
        time.sleep(3)
        run_services()


def run_process(name, cmd, args, custom_env=None):
    """启动子进程并开启守护线程"""
    if shutting_down or processes[name]:
        return
    
    env = os.environ.copy()
    if custom_env:
        env.update(custom_env)
        
    try:
        proc = subprocess.Popen(
            [cmd] + args,
            cwd=str(DOWNLOAD_DIR),
            env=env,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL
        )
        processes[name] = proc
        threading.Thread(target=watch_process, args=(name, proc), daemon=True).start()
    except Exception as e:
        print(f"[{name}] start failed: {e}", file=sys.stderr)


def run_services():
    """按需拉起所有后端服务"""
    if (DOWNLOAD_DIR / "nzv1").exists() and not processes["nzv1"]:
        env = {
            "NZ_SERVER": CONFIG["NZ_SERVER"],
            "NZ_CLIENT_SECRET": CONFIG["NZ_CLIENT_SECRET"],
            "NZ_TLS": "true"
        }
        if CONFIG["NZ_UUID"]:
            env["NZ_UUID"] = CONFIG["NZ_UUID"]
        run_process("nzv1", str(DOWNLOAD_DIR / "nzv1"), [], env)

    if (DOWNLOAD_DIR / "hy2").exists() and not processes["hy2"]:
        run_process("hy2", str(DOWNLOAD_DIR / "hy2"), ["server", "-c", str(DOWNLOAD_DIR / "config.yaml")])

    if (DOWNLOAD_DIR / "frpc").exists() and not processes["frpc"]:
        run_process("frpc", str(DOWNLOAD_DIR / "frpc"), ["-c", str(DOWNLOAD_DIR / "frpc.toml")])


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """轻量级健康检查 HTTP 服务"""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
        
    def log_message(self, format, *args):
        pass


def start_http_server():
    global http_server
    http_server = http.server.HTTPServer(("0.0.0.0", CONFIG["PORT"]), HealthCheckHandler)
    print(f"app is running on port {CONFIG['PORT']}")
    http_server.serve_forever()


def shutdown(signum=None, frame=None):
    """优雅退出程序"""
    global shutting_down
    if shutting_down:
        return
    shutting_down = True
    
    print("\nShutting down gracefully...")
    
    for name, proc in processes.items():
        if proc:
            try:
                proc.terminate()
            except:
                pass
                
    if http_server:
        threading.Thread(target=http_server.shutdown, daemon=True).start()
        
    time.sleep(1)
    sys.exit(0)


def main():
    # 兼容 Streamlit 等平台可能在子线程执行脚本的特性，避免 signal 报错
    if threading.current_thread() is threading.main_thread():
        try:
            signal.signal(signal.SIGINT, shutdown)
            signal.signal(signal.SIGTERM, shutdown)
        except Exception:
            pass
    
    try:
        download_files()
        generate_ssl()
        create_config_files()
        run_services()
        
        threading.Thread(target=start_http_server, daemon=True).start()
        
        while not shutting_down:
            time.sleep(1)
            
    except Exception as error:
        print(f"Initialization failed: {error}", file=sys.stderr)
        shutdown()


if __name__ == "__main__":
    main()
