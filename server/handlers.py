"""
hwebserver の URL ハンドラー（hython で動かす）

リクエストを受け取り、server/hipdata.py の関数を呼んで JSON で返す。
"""
import functools
import json
import os
import threading
import traceback

import hou
import hwebserver

from server import hipdata

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# hou はスレッドセーフではないので、hou を触る処理は 1 つずつ順番に行う
_hou_lock = threading.Lock()

# 受け付ける Host ヘッダーと Origin。main.py が起動時にポート番号を入れる
allowed_hosts = set()
allowed_origins = set()


def _json_response(data, status=200):
    body = json.dumps(data, ensure_ascii=False)
    response = hwebserver.Response(body, status, "application/json; charset=utf-8")
    response.setHeader("Cache-Control", "no-store")
    return response


def _error(message, status):
    return _json_response({"error": message}, status)


def api(method):
    """API ハンドラー用のデコレーター

    - HTTP メソッドを確認する
    - 他のサイトからのリクエストを断る（Origin の確認と、POST は JSON 限定）
    - POST の本文を JSON として読み、handler(request, body) に渡す
    - hou の処理をロックの中で行い、例外を JSON のエラーにして返す
    """
    def decorator(handler):
        @functools.wraps(handler)
        def wrapper(request):
            if request.method() != method:
                return _error(f"{method} で呼んでください", 405)

            # hwebserver の ALLOWED_HOSTS は効かないことがあるので、ここでも確かめる
            # （DNS リバインディングで他のサイトから呼ばれるのを防ぐ）
            headers = {k.lower(): v for k, v in request.headers().items()}
            origin = headers.get("origin")
            if headers.get("host") not in allowed_hosts or (origin and origin not in allowed_origins):
                return _error("このサーバーは 127.0.0.1 からの利用に限っています", 403)

            body = {}
            if method == "POST":
                # application/json 以外を断ると、他のサイトからのフォーム送信を防げる
                if not headers.get("content-type", "").startswith("application/json"):
                    return _error("Content-Type は application/json にしてください", 415)
                try:
                    body = json.loads(request.body() or "{}")
                except ValueError:
                    return _error("本文が JSON ではありません", 400)
                if not isinstance(body, dict):
                    return _error("本文は JSON のオブジェクトにしてください", 400)

            try:
                with _hou_lock:
                    return _json_response(handler(request, body))
            except hipdata.HipError as e:
                return _error(str(e), e.status)
            except hou.Error as e:
                return _error(e.instanceMessage() or str(e), 500)
            except Exception as e:
                traceback.print_exc()
                return _error(f"{type(e).__name__}: {e}", 500)
        return wrapper
    return decorator


def _require(body, key):
    value = body.get(key)
    if not value:
        raise hipdata.HipError(f"{key} を指定してください")
    return value


# --- 画面 ------------------------------------------------------------------

@hwebserver.urlHandler("/")
def index(request):
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    # /static のファイルはブラウザに 1 週間キャッシュされる（hwebserver の初期設定で、変えられない）。
    # 更新時刻を URL に付けて、ファイルを変えたら読み直させる
    for name in ("style.css", "app.js"):
        mtime = int(os.path.getmtime(os.path.join(STATIC_DIR, name)))
        html = html.replace(f"/static/{name}", f"/static/{name}?v={mtime}")
    response = hwebserver.Response(html, 200, "text/html; charset=utf-8")
    response.setHeader("Cache-Control", "no-store")
    return response


# --- API -------------------------------------------------------------------

@hwebserver.urlHandler("/api/status")
@api("GET")
def get_status(request, body):
    return hipdata.status()


@hwebserver.urlHandler("/api/files")
@api("GET")
def get_files(request, body):
    return hipdata.list_files(request.GET().get("dir", ""))


@hwebserver.urlHandler("/api/hip/open")
@api("POST")
def post_open(request, body):
    return hipdata.open_hip(_require(body, "path"))


@hwebserver.urlHandler("/api/hip/save")
@api("POST")
def post_save(request, body):
    return hipdata.save_hip(body.get("path"))


@hwebserver.urlHandler("/api/nodes")
@api("GET")
def get_nodes(request, body):
    return hipdata.list_nodes(request.GET().get("path", "/"))


@hwebserver.urlHandler("/api/node")
@api("GET")
def get_node(request, body):
    return hipdata.node_parms(request.GET().get("path", ""))


@hwebserver.urlHandler("/api/parms")
@api("POST")
def post_parms(request, body):
    values = body.get("values")
    if not isinstance(values, dict):
        raise hipdata.HipError("values は {パラメータ名: [値, ...]} の形で指定してください")
    return hipdata.set_parms(_require(body, "path"), values)


@hwebserver.urlHandler("/api/render")
@api("POST")
def post_render(request, body):
    return hipdata.render(_require(body, "path"))


def _exit_process():
    try:
        hou.exit(exit_code=0, suppress_save_prompt=True)
    finally:
        os._exit(0)


@hwebserver.urlHandler("/api/shutdown")
@api("POST")
def post_shutdown(request, body):
    # hwebserver.requestShutdown() はハンドラーのスレッドから呼ぶとサーバーが止まらないので、
    # レスポンスを返し終わったころに hython ごと終了する（ライセンスも返る）
    threading.Timer(0.5, _exit_process).start()
    return {"ok": True}
