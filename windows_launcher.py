from __future__ import annotations

import shutil
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from config import BUNDLED_ROOT, PROJECT_ROOT, configure_console, ensure_runtime_dirs
from dashboard import HOST, PORT, run_server


ENV_TEMPLATE = """SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=请填写邮箱
SMTP_PASSWORD=请填写邮箱SMTP授权码
EMAIL_FROM=请填写邮箱
EMAIL_TO=请填写接收提醒的邮箱
"""


def ensure_env_template() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        return
    example_path = PROJECT_ROOT / ".env.example"
    bundled_example_path = BUNDLED_ROOT / ".env.example"
    if example_path.exists():
        shutil.copy2(example_path, env_path)
    elif bundled_example_path.exists():
        shutil.copy2(bundled_example_path, env_path)
    else:
        env_path.write_text(ENV_TEMPLATE, encoding="utf-8")
    print("已创建 .env 模板。请用记事本填写邮箱配置后，再在网页里测试邮件。")


def open_browser_later() -> None:
    url = f"http://{HOST}:{PORT}/"
    health_url = f"{url}health"
    for _ in range(60):
        try:
            with urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    webbrowser.open(url)


def main() -> None:
    configure_console()
    ensure_runtime_dirs()
    ensure_env_template()
    threading.Thread(target=open_browser_later, daemon=True).start()
    run_server(HOST, PORT)


if __name__ == "__main__":
    main()
