# houdini-headless

Houdini を GUI で開かずに操作するためのツール集です。
hython（Houdini 同梱の Python）を使い、hip の中身を調べたり、ノードやパラメータを操作したりします。

## 動作環境

| 項目 | バージョン / 場所 |
| --- | --- |
| Houdini | 22.0.368（`C:\Program Files\Side Effects Software\Houdini 22.0.368`） |
| hython | 上記 `bin\hython.exe`（Python 3.13） |
| GUI 用 Python | 通常の Python 3.13 + PySide6 |

hython は起動中ずっと Houdini のライセンスを使います。
そのため、GUI は通常の Python で動かし、Houdini の処理が必要なときだけ hython を別プロセスで呼び出す構成にしています。

## ファイル構成

| ファイル | 内容 |
| --- | --- |
| `export_box_usd.py` | box を作り、Solaris 経由で USD に書き出すテストスクリプト |
| `export_box_usd.hip` | 上のスクリプトが保存する hip（GUI で開いて確認する用） |
| `box.usda` / `usd/import_box.usd` | 上のスクリプトが書き出す USD |

## 使い方

### hython でスクリプトを実行する

```powershell
& "C:\Program Files\Side Effects Software\Houdini 22.0.368\bin\hython.exe" export_box_usd.py
```

### USD の中身を確認する（usdcat）

usdcat も Houdini の `bin` に入っています。

```powershell
$env:PATH = "C:\Program Files\Side Effects Software\Houdini 22.0.368\bin;$env:PATH"
usdcat box.usda             # テキストで表示
usdcat box.usda --flatten   # サブレイヤーを統合して表示
```

`bin` を PATH に追加するのは、今開いているターミナルの中だけにしてください。
Houdini の DLL が他のソフトとぶつかることがあるので、システムの PATH に常に入れておくのは避けます。

Houdini の環境が設定済みのシェルを開く方法もあります。
`bin\hcmd.exe`（スタートメニューの「Houdini 22.0.368 Command Line Tools」）を起動してください。

## ロードマップ

- [ ] hip 内のネットワーク（SOP / ROP など）のノードをビジュアライズする GUI
- [ ] ノードのパラメータの取得と上書き
- [ ] 応用例：レンダー設定の変更と Deadline へのジョブ投入（Arnold）
