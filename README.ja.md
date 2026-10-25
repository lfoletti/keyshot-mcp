# keyshot-mcp

[English](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md) | [简体中文](https://github.com/lfoletti/keyshot-mcp/blob/main/README.zh-CN.md) | 日本語 | [한국어](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ko.md) | [Deutsch](https://github.com/lfoletti/keyshot-mcp/blob/main/README.de.md)

Model Context Protocol（MCP）を使って、開いている KeyShot Studio 2026 のウィンドウを Claude Code から操作します。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-orange.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ja.md#ステータス)
[![Tests](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/lfoletti/keyshot-mcp)](https://github.com/lfoletti/keyshot-mcp/releases)
[![PyPI](https://img.shields.io/pypi/v/keyshot-mcp)](https://pypi.org/project/keyshot-mcp/)

> **ステータス：プロトタイプ。** ツールは動作し、テストもあります。ただし本プロジェクトは KeyShot のスクリプト API に依存しており、この API は変わる可能性があります。使っている機能や不具合を教えてください。issue またはディスカッションを開いてください。

![Claude Code が KeyShot のシーンを読み取り、ボトルのガラスを 3 回変更し、すべての変更を元に戻す様子。](https://raw.githubusercontent.com/lfoletti/keyshot-mcp/main/docs/demo.gif)

*デモは実際の 3 倍の速度で再生されます。*

```
Claude Code ⇄ MCP サーバー keyshotmcp（Python 3.12、stdio）
            ⇄ TCP 127.0.0.1:1998、4 バイト長 + JSON、トークン
            ⇄ MCP start.py（KeyShot 内、UI スレッド上のタイマー）
```

ブリッジは KeyShot の中で動きます。サーバーは Claude Code の中で動きます。両者はローカルのコンピューター上でのみ通信します。

## 動作要件

| 項目 | バージョン |
|---|---|
| KeyShot Studio | 15.1（2026）以降。2026.2 Pro（15.1.2.7）でテスト済み。 |
| Python | 3.12 以降、Windows |
| `mcp` | 1.30.0 |
| Claude Code | 最近のバージョンであれば可 |

## インストール

### PyPI から

バージョン 1.1.0 から、`keyshot-mcp` は Python パッケージです。[uv](https://docs.astral.sh/uv/) を使います：

```
uvx keyshot-mcp install-addin
claude mcp add keyshot -- uvx keyshot-mcp
```

`install-addin` は 2 つのブリッジスクリプトを `%PUBLIC%\Documents\KeyShot Studio\Scripts`（または `--dir` で指定したフォルダー）にコピーします。その後 KeyShot を再起動してください。

### Claude Code プラグインとして

バージョン 1.1.0 から、このリポジトリは Claude Code のマーケットプレイスでもあります。プラグイン `keyshot` は `uvx` でサーバーを起動するため、[uv](https://docs.astral.sh/uv/) が必要です。

```
/plugin marketplace add lfoletti/keyshot-mcp
/plugin install keyshot@keyshot-mcp
```

次に `/keyshot-install-addin` を一度実行し、KeyShot を再起動してください。

### リリースの zip またはリポジトリから

各リリースには `keyshot-mcp-<version>-windows.zip` があり、`libs/` はすでに入っています。展開したら手順 3 から始めてください。zip を使わない場合は手順 1 から始めます。

1. リポジトリをクローンします：
   ```
   git clone https://github.com/lfoletti/keyshot-mcp.git
   ```
2. `mcp` を `libs` フォルダーにインストールします。`run.py` はそこから読み込みます。
   ```
   py -3.12 -m pip install --target libs mcp==1.30.0
   ```
3. `addin\Scripts\MCP start.py` と `MCP stop.py` を
   `C:\Users\Public\Documents\KeyShot Studio\Scripts\` にコピーします。
4. KeyShot を再起動します。KeyShot は起動時にのみ Scripts フォルダーを読み込みます。
5. サーバーを Claude Code に追加します：
   ```
   claude mcp add keyshot -- py -3.12 -I -S C:\path\to\keyshot-mcp\run.py
   ```
6. インポートが正しいことを確認します：
   ```
   py -3.12 -I -S run.py --check
   ```
   出力に `keyshot : imports ok` と 33 個のツールが表示されます。

## 使い方

1. KeyShot で *Window > Scripting Console > Scripts*（ウィンドウ > スクリプトコンソール > スクリプト）を開きます。
2. `MCP start` を選び、*Run* をクリックします。コンソールに `Pont KeyShot actif sur 127.0.0.1:1998` と表示されます。
3. Claude Code で `/mcp` と入力し、`keyshot` が接続されていることを確認します。
4. Claude に依頼します。例：
   - 「シーンを見せて、マテリアルを一覧にして。」
   - 「キャップにヘアラインアルミを適用して、1920 × 1080 でレンダリングして。」

ブリッジを止めるには、スクリプト `MCP stop` を実行するか、KeyShot を閉じます。
ブリッジを更新するには、新しいファイルをコピーしてから、ツール `reload_bridge` を使います。

## ツール

| グループ | ツール |
|---|---|
| シーン | `keyshot_status`, `get_scene_info`, `get_scene_tree`, `list_objects`, `set_visibility`, `screenshot`, `save_scene` |
| カメラと環境 | `list_cameras`, `set_camera`, `fit_camera`, `list_environments`, `set_environment`, `set_realtime` |
| マテリアル | `list_materials`, `get_material`, `list_library_materials`, `assign_material`, `set_material_parameter`, `rename_material`, `undo_material_changes`, `commit_material_changes`, `save_material_to_library` |
| マテリアルグラフ | `add_material_node`, `connect_material_nodes`, `disconnect_material_input`, `remove_material_node` |
| レンダリング | `render_image`, `render_status`, `wait_for_render`, `view_image` |
| ブリッジ | `lux_functions`, `reload_bridge`, `execute_python`（既定で無効） |

2 つの MCP プロンプトが Claude に作業の進め方を伝えます：

| プロンプト | 用途 |
|---|---|
| `keyshot_strategy` | シーンを壊さずに KeyShot で作業する方法。 |
| `keyshot_materiaux` | CMF シート（色、素材、仕上げ）または説明文からマテリアルを作る方法：物理値、色、ノードのレシピ。 |

色：`[r, g, b]` はリニア値（0-1）です。`#RRGGBB` は sRGB で、ブリッジがリニア値に変換します。

## 設定

任意のファイル：`%LOCALAPPDATA%\keyshot-mcp\pont-config.json`。

```json
{"execute_python": false, "dossier_sorties": "C:\\path\\to\\outputs"}
```

| 設定 | 効果 |
|---|---|
| `execute_python` | `true` でツール `execute_python` を有効にします。既定値は `false` です。 |
| `dossier_sorties` | スクリーンショット、レンダリング、シーンのバックアップを保存するフォルダー。 |
| `dossiers_textures` | ブリッジがテクスチャ画像を読み込めるフォルダーの追加リスト。KeyShot のテクスチャライブラリと `dossier_sorties` は常に許可されます。 |
| `KEYSHOT_MCP_PORT` | 環境変数。ブリッジのポート。既定値は 1998 です。 |
| `KEYSHOT_MCP_TIMEOUT` | 環境変数。サーバーのタイムアウト（秒）。既定値は 60 です。 |
| `KEYSHOT_MCP_EXECUTE_PYTHON` | 環境変数。`1` で `execute_python` を有効にします。 |

ブリッジは同じフォルダーに `pont-actif.json`（ポート、トークン、KeyShot の PID）と `pont.log` を書き込みます。

## 安全性

- ブリッジは 127.0.0.1 でのみ待ち受けます。各リクエストには `pont-actif.json` のトークンが必要です。
- `execute_python` は無効です。ローカルの設定でのみ有効にできます。
- ツールがマテリアルグラフを編集するのは、ブリッジが作成したコピーに対してだけです。
- `set_camera` は保存されていないカメラビューを破棄しません。
- `save_scene` は古い `.bip` ファイルのコピーを残します。

## テスト

テストはダミーの `lux` モジュールを使います。KeyShot は不要です。

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
py -3.13 test_cli.py
py -3.13 test_publication.py
py -3.13 test_plugin.py
py -3.13 test_dev_version.py
```

`test_pont.py` には 87 件のブリッジのテストがあります。`test_serveur_mcp.py` には 9 件のエンドツーエンドテストがあります。`test_cli.py` はコマンド `keyshot-mcp` をテストします。`test_publication.py` と `test_plugin.py` は PyPI、MCP レジストリ、プラグインの各ファイルを確認し、README がコードと一致していることを確認します。`test_dev_version.py` は TestPyPI 用バージョンツールをテストします。`essai_*.py` ファイルには起動中の KeyShot が必要です。

`test_serveur_mcp.py` は、テストを実行している Python でサーバーを起動します。`libs` のパッケージが別の Python バージョン用の場合は、`KEYSHOT_MCP_PYTHON` に該当する `python.exe` を設定してください。

## コントリビュート

[CONTRIBUTING.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CONTRIBUTING.md) と [CODE_OF_CONDUCT.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CODE_OF_CONDUCT.md)（英語）をお読みください。issue とディスカッションはできるだけ英語でお願いします。

## ステータス

keyshot-mcp は動作するプロトタイプです。Windows 上の KeyShot Studio 2026.2 Pro でテストしています。

- ブリッジは KeyShot のスクリプト API（`lux`）を使います。KeyShot の新しいバージョンでこの API が変わる可能性があります。
- 将来の KeyShot に Claude との連携機能が組み込まれる可能性があります。その場合、本プロジェクトは終了するかもしれません。
- 新機能よりもフィードバックを優先します。issue テンプレート *Bug* と *Feedback* を使ってください。

## 免責事項

keyshot-mcp は独立したプロジェクトです。Luxion および KeyShot とは提携しておらず、現時点で Luxion による承認や支援も受けていません。KeyShot は Luxion の商標です。

## ライセンス

MIT

---

このファイルは [README.md](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md) の翻訳です。内容が異なる場合は英語版が優先されます。
