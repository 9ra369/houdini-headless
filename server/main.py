"""
houdini-headless の Web サーバーを起動する（hython で動かす）

実行例（リポジトリのルートで実行）:
  python -m app.houdini_env hython server/main.py
  python -m app.houdini_env hython server/main.py --port 8010 --hip samples/export_box_usd.hip

起動したらブラウザで http://127.0.0.1:8000 を開く。
止めるときは画面の「停止」ボタンを押すか、ターミナルで Ctrl+Break を押す。
"""
import argparse
import os
import sys

# server パッケージを import できるように、リポジトリのルートを先頭に入れる
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import hwebserver  # noqa: E402

from server import handlers, hipdata  # noqa: E402

HOST = "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="houdini-headless の Web サーバー")
    parser.add_argument("--port", type=int, default=8000, help="待ち受けるポート番号（既定: 8000）")
    parser.add_argument("--hip", help="起動時に開く hip ファイル")
    parser.add_argument("--debug", action="store_true", help="エラーの詳細をレスポンスに含める")
    args = parser.parse_args()

    if args.hip:
        print("Opening:", hipdata.open_hip(args.hip)["hipPath"])

    hosts = {f"{HOST}:{args.port}", f"localhost:{args.port}"}
    handlers.allowed_hosts.update(hosts)
    handlers.allowed_origins.update(f"http://{h}" for h in hosts)
    hwebserver.registerStaticFilesDirectory(handlers.STATIC_DIR, "/static")

    print(f"houdini-headless: http://{HOST}:{args.port}")
    print("止めるときは画面の「停止」ボタンを押すか、Ctrl+Break を押してください")
    sys.stdout.flush()

    hwebserver.run(
        port=args.port,
        debug=args.debug,
        in_background=False,
        # 初期設定では 0.0.0.0（すべての NIC）で待ち受けるので、この PC だけに限る
        settings={
            "PORT": args.port,
            "ADDRESS": HOST,
            "ALLOWED_HOSTS": [HOST, "localhost"],
        },
    )


if __name__ == "__main__":
    main()
