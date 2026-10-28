# houdini-headless

Houdini を GUI で開かずに、ブラウザから hip を開いて操作するためのツールです。
hython（Houdini 同梱の Python）をローカルの Web サーバーとして起動したままにし、ブラウザから hip のノードネットワークを見たり、パラメータを編集したりします。

## 動作環境

| 項目 | バージョン / 場所 |
| --- | --- |
| Houdini | 22.0.368（`C:\Program Files\Side Effects Software\Houdini 22.0.368`） |
| hython | 上記 `bin\hython.exe`（Python 3.13） |
| ブラウザ | Chrome / Edge / Firefox などの最近のもの |

追加のインストールは不要です。
Web サーバーには Houdini 同梱の `hwebserver` を使います。

### Houdini のインストール先

インストール先は [app/houdini_env.py](app/houdini_env.py) が次の順で決めます。

1. 環境変数 `HOUDINI_ROOT`
2. `C:\Program Files\Side Effects Software` の中で一番新しいバージョンの Houdini

特定のバージョンを使いたいときは `HOUDINI_ROOT` を設定してください。

```powershell
$env:HOUDINI_ROOT = "C:\Program Files\Side Effects Software\Houdini 21.0.440"
python -m app.houdini_env --where   # 使われるインストール先を表示
```

## 構成

```text
ブラウザ ──HTTP (JSON)──▶ hython（hwebserver + hou を起動したまま）
```

- hython の起動には 20 秒以上かかるため、リクエストのたびに起動せず、起動したままにします。
- hython はライセンスを 1 本借りたままになります。使い終わったらサーバーを止めてください。
- `hou` はスレッドセーフではないので、リクエストは 1 つずつ順番に処理します。
- 開ける hip は一度に 1 つです。変更は保存するまでメモリ上にだけあります。
- 待ち受けるのは `127.0.0.1`（この PC）だけです。他の PC からは開けません。

## ファイル構成

| パス | 内容 |
| --- | --- |
| `app/` | 通常の Python で動かす側。`hou` は使わない |
| `app/houdini_env.py` | Houdini のインストール先を見つけて、hython や usdcat を実行する |
| `server/` | hython で動かす Web サーバー。`hou` と `hwebserver` を使う |
| `server/main.py` | サーバーの起動スクリプト |
| `server/handlers.py` | URL ごとの処理。リクエストを受けて `hipdata` を呼び、JSON で返す |
| `server/hipdata.py` | `hou` で hip を読み書きする処理。HTTP のことは知らない |
| `server/static/` | ブラウザに返す画面（HTML / JS / CSS） |
| `hython_scripts/` | hython で動かす単体のスクリプト。`hou` を使う |
| `hython_scripts/export_box_usd.py` | box を作り、Solaris 経由で USD に書き出すテストスクリプト |
| `samples/` | テスト用の hip と USD。`export_box_usd.py` の出力先 |

## 使い方

コマンドはどれもリポジトリのルートで実行します。

### Web UI を起動する

```powershell
python -m app.houdini_env hython server/main.py                                    # http://127.0.0.1:8000
python -m app.houdini_env hython server/main.py --hip samples/export_box_usd.hip   # 起動時に hip を開く
python -m app.houdini_env hython server/main.py --port 8010                        # ポートを変える
```

hython の起動には 20〜30 秒かかります。`houdini-headless: http://127.0.0.1:8000` と表示されたら、ブラウザでそのアドレスを開きます。

止めるときは、画面右上の「停止」ボタンを押します（hython が終了し、ライセンスが返されます）。
ターミナルからは `Ctrl+Break` で止められます。Windows では `Ctrl+C` では止まりません。

### 画面の使い方

| 場所 | できること |
| --- | --- |
| 上のバー | hip を開く・保存する・別名で保存する。未保存の変更があると「● 未保存」と表示される |
| 左（ノード） | ノードの階層。クリックで選択、▸ で展開、ダブルクリックでそのネットワークに入る |
| 中央（ネットワーク） | ノードとつながりの図。ドラッグで移動、ホイールで拡大縮小、ダブルクリックで中に入る |
| 右（パラメータ） | 選んだノードのパラメータ。値を変えて「適用」で反映する。ROP なら「ROP を実行」で書き出す |
| 下（ログ） | 実行結果やエラー |

- エクスプレッションやアニメーションが付いたパラメータは、表示のみで変更できません（`ƒ` で式を表示）。
- ランプなど、一部の種類のパラメータは表示できません。
- スクリプトで作った hip のように、ノードがみな同じ位置にあるときは、入力の深さで並べ直して表示します（hip は変わりません）。
- ROP の実行中は、ほかの操作は待たされます。

### hython でスクリプトを実行する

```powershell
python -m app.houdini_env hython hython_scripts/export_box_usd.py
```

### USD の中身を確認する（usdcat）

```powershell
python -m app.houdini_env usdcat samples/box.usda             # テキストで表示
python -m app.houdini_env usdcat samples/box.usda --flatten   # サブレイヤーを統合して表示
```

`app.houdini_env` は、実行するツールのプロセスの中だけで Houdini の `bin` を PATH に追加します。
Houdini の DLL が他のソフトとぶつかることがあるので、システムの PATH には入れないでください。

Houdini の環境が設定済みのシェルを開く方法もあります。
`bin\hcmd.exe`（スタートメニューの「Houdini 22.0.368 Command Line Tools」）を起動してください。

## API

| メソッド | パス | 内容 |
| --- | --- | --- |
| `GET` | `/api/status` | 開いている hip と、未保存の変更があるかを返す |
| `GET` | `/api/files?dir=...` | フォルダの中のサブフォルダと hip を返す（`dir` が空ならドライブ一覧） |
| `POST` | `/api/hip/open` | `{path}` の hip を開く |
| `POST` | `/api/hip/save` | hip を保存する（`{path}` を指定すると別名で保存） |
| `GET` | `/api/nodes?path=/obj` | 指定したノードの子ノードと接続を返す |
| `GET` | `/api/node?path=...` | ノードのパラメータ一覧を返す |
| `POST` | `/api/parms` | `{path, values}` でパラメータをまとめて変更する |
| `POST` | `/api/render` | `{path}` の ROP を実行する |
| `POST` | `/api/shutdown` | hython を終了する |

- POST の本文は JSON で、`Content-Type: application/json` が必要です（他のサイトからのフォーム送信を防ぐため）。
- `Host` が `127.0.0.1:<port>` か `localhost:<port>` 以外のリクエストは断ります。

### hwebserver の注意点（Houdini 22.0.368 で確認）

- 初期設定では `0.0.0.0`（すべての NIC）で待ち受けるので、`settings` の `ADDRESS` で `127.0.0.1` に限っています。
- `ALLOWED_HOSTS` を設定しても効かなかったので、`Host` ヘッダーは `handlers.py` で確かめています。
- `hwebserver.requestShutdown()` をハンドラーから呼んでもサーバーが止まらないので、`/api/shutdown` は hython ごと終了させます。
- `/static` のファイルは 1 週間キャッシュされ、変えられません（ドキュメントにある `setCacheControl` がありません）。そのため、`index.html` を返すときに CSS / JS の URL に更新時刻を付けています。

## ロードマップ

- [x] M1: hython を Web サーバーとして起動し、ブラウザから hip を開いてノードの階層を表示する
- [x] M2: ネットワークのノードと接続を図で表示する
- [x] M3: ノードのパラメータを表示・編集し、hip を保存する
- [x] M4: ROP を実行し、結果とログを表示する
- [ ] 応用例：レンダー設定の変更と Deadline へのジョブ投入（Arnold）
