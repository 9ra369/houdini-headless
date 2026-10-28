"""
Houdini のインストール先を見つけて、bin 内のツール（hython / usdcat など）を実行するモジュール

インストール先は次の順で決める:
  1. 環境変数 HOUDINI_ROOT（例: C:\\Program Files\\Side Effects Software\\Houdini 22.0.368）
  2. C:\\Program Files\\Side Effects Software 内で一番新しいバージョンの Houdini

コマンドラインからの実行例（リポジトリのルートで実行）:
  python -m app.houdini_env --where
  python -m app.houdini_env hython hython_scripts/export_box_usd.py
  python -m app.houdini_env usdcat samples/box.usda --flatten
"""
import os
import re
import subprocess
import sys
from pathlib import Path

SIDEFX_DIR = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Side Effects Software"
_VERSION_RE = re.compile(r"^Houdini (\d+)\.(\d+)\.(\d+)$")


def houdini_root() -> Path:
    """Houdini のインストールフォルダを返す"""
    env_root = os.environ.get("HOUDINI_ROOT")
    if env_root:
        root = Path(env_root)
        if not (root / "bin").is_dir():
            raise FileNotFoundError(f"HOUDINI_ROOT に bin フォルダがありません: {root}")
        return root

    # "Houdini 22.0.368" のようなフォルダを探し、バージョンを数値で比べて一番新しいものを選ぶ
    candidates = []
    if SIDEFX_DIR.is_dir():
        for path in SIDEFX_DIR.iterdir():
            m = _VERSION_RE.match(path.name)
            if m and (path / "bin").is_dir():
                candidates.append((tuple(int(v) for v in m.groups()), path))
    if not candidates:
        raise FileNotFoundError(
            f"Houdini が見つかりません: {SIDEFX_DIR}\n"
            "環境変数 HOUDINI_ROOT にインストール先を設定してください"
        )
    return max(candidates)[1]


def bin_dir() -> Path:
    return houdini_root() / "bin"


def tool_path(name: str) -> Path:
    """bin 内のツールのパスを返す（例: "hython" -> .../bin/hython.exe）"""
    for ext in (".exe", ".cmd"):
        path = bin_dir() / f"{name}{ext}"
        if path.is_file():
            return path
    raise FileNotFoundError(f"{bin_dir()} に {name} が見つかりません")


def tool_env() -> dict:
    """bin を PATH の先頭に加えた環境変数を返す

    PATH を変えるのは子プロセスの中だけ。
    Houdini の DLL が他のソフトとぶつからないよう、このプロセスやシステムの PATH は変えない。
    """
    env = os.environ.copy()
    env["PATH"] = str(bin_dir()) + os.pathsep + env.get("PATH", "")
    return env


def run_tool(name: str, *args: str, **kwargs) -> subprocess.CompletedProcess:
    """bin 内のツールを実行する。kwargs は subprocess.run にそのまま渡す"""
    cmd = [str(tool_path(name)), *map(str, args)]
    return subprocess.run(cmd, env=tool_env(), **kwargs)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        if argv[0] == "--where":
            print(houdini_root())
            return 0
        return run_tool(argv[0], *argv[1:]).returncode
    except FileNotFoundError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
