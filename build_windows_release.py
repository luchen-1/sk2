from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_NAME = "护肤品价格助手"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"
PACKAGE_DIR = RELEASE_DIR / f"{APP_NAME}-windows"
ZIP_PATH = RELEASE_DIR / f"{APP_NAME}-windows.zip"


def run(command: list[str]) -> None:
    print(" ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def copy_file(source: str, target_name: str | None = None) -> None:
    source_path = ROOT / source
    if not source_path.exists():
        raise FileNotFoundError(source)
    shutil.copy2(source_path, PACKAGE_DIR / (target_name or source_path.name))


def copy_tree(source: str) -> None:
    source_path = ROOT / source
    if source_path.exists():
        shutil.copytree(source_path, PACKAGE_DIR / source_path.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def write_release_readme() -> None:
    text = """# 护肤品价格助手 Windows 免安装版

## 使用方法

1. 解压整个文件夹。
2. 双击 `护肤品价格助手.exe`。
3. 浏览器会自动打开本地控制台。
4. 首次运行会自动创建 `.env` 模板，请用记事本填写邮箱配置。
5. 在网页里点击“系统自检”，再点击“测试邮件”验证邮箱。

## 注意

- 不需要安装 Python。
- 不要打开 `.spec` 文件，它只是打包配置，不是启动程序。
- 不要删除 `products.xlsx`。
- 不要把填写后的 `.env` 发给别人。
- 数据库、报告、备份和截图会保存在当前文件夹中。
"""
    (PACKAGE_DIR / "使用说明.txt").write_text(text, encoding="utf-8")


def main() -> None:
    remove(DIST_DIR)
    remove(BUILD_DIR)
    remove(PACKAGE_DIR)
    remove(ZIP_PATH)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--console",
            "--name",
            APP_NAME,
            "--exclude-module",
            "streamlit",
            "--exclude-module",
            "pyarrow",
            "--exclude-module",
            "altair",
            "--exclude-module",
            "PIL",
            "--hidden-import",
            "openpyxl",
            "windows_launcher.py",
        ]
    )

    built_dir = DIST_DIR / APP_NAME
    if not built_dir.exists():
        raise FileNotFoundError(built_dir)
    shutil.copytree(built_dir, PACKAGE_DIR)

    copy_file("products.xlsx")
    copy_file("products.csv")
    copy_file(".env.example")
    copy_file("README.md")
    copy_tree("chrome_extension")
    write_release_readme()

    shutil.make_archive(str(ZIP_PATH.with_suffix("")), "zip", RELEASE_DIR, PACKAGE_DIR.name)
    print(f"发布包已生成: {ZIP_PATH}")


if __name__ == "__main__":
    main()
