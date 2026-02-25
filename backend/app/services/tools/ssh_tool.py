import socket
import paramiko


class SSHRunner:
    def __init__(self, host: str, port: int, username: str, password: str, timeout_s: int = 20):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout_s = timeout_s

    def run(self, cmd: str, timeout_s: int = 120):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout_s,
                banner_timeout=self.timeout_s,
                auth_timeout=self.timeout_s,
            )
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout_s)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            return {"exit_code": exit_code, "stdout": out, "stderr": err}
        except (socket.timeout, paramiko.SSHException) as e:
            return {"exit_code": 255, "stdout": "", "stderr": f"SSH error: {e}"}
        finally:
            try:
                client.close()
            except Exception:
                pass
