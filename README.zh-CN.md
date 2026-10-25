# keyshot-mcp

[English](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md) | 简体中文 | [日本語](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ja.md) | [한국어](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ko.md) | [Deutsch](https://github.com/lfoletti/keyshot-mcp/blob/main/README.de.md)

通过模型上下文协议（MCP），在 Claude Code 中控制已打开的 KeyShot Studio 2026 窗口。

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-orange.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/README.zh-CN.md#状态)
[![Tests](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/lfoletti/keyshot-mcp)](https://github.com/lfoletti/keyshot-mcp/releases)
[![PyPI](https://img.shields.io/pypi/v/keyshot-mcp)](https://pypi.org/project/keyshot-mcp/)

> **状态：原型。** 工具可以使用，并且有测试。但本项目依赖 KeyShot 的脚本 API，该 API 可能会变化。请告诉我们你用了什么、哪里出错：提交 issue 或发起讨论。

![Claude Code 读取 KeyShot 场景，三次修改瓶子的玻璃，然后撤销全部修改。](https://raw.githubusercontent.com/lfoletti/keyshot-mcp/main/docs/demo.gif)

*演示以实际速度的 3 倍播放。*

```
Claude Code ⇄ MCP 服务器 keyshotmcp（Python 3.12，stdio）
            ⇄ TCP 127.0.0.1:1998，4 字节长度 + JSON，令牌
            ⇄ MCP start.py（在 KeyShot 中，UI 线程上的定时器）
```

桥接程序运行在 KeyShot 内部。服务器运行在 Claude Code 中。两者只在本机通信。

## 环境要求

| 项目 | 版本 |
|---|---|
| KeyShot Studio | 15.1（2026）或更高。已用 2026.2 Pro（15.1.2.7）测试。 |
| Python | 3.12 或更高，Windows |
| `mcp` | 1.30.0 |
| Claude Code | 任意较新版本 |

## 安装

### 从 PyPI 安装

从 1.1.0 版起，`keyshot-mcp` 是一个 Python 包。使用 [uv](https://docs.astral.sh/uv/)：

```
uvx keyshot-mcp install-addin
claude mcp add keyshot -- uvx keyshot-mcp
```

`install-addin` 把两个桥接脚本复制到 `%PUBLIC%\Documents\KeyShot Studio\Scripts`（或 `--dir` 指定的文件夹）。然后重启 KeyShot。

### 作为 Claude Code 插件安装

从 1.1.0 版起，本仓库也是一个 Claude Code 插件市场。插件 `keyshot` 用 `uvx` 启动服务器，因此需要先安装 [uv](https://docs.astral.sh/uv/)。

```
/plugin marketplace add lfoletti/keyshot-mcp
/plugin install keyshot@keyshot-mcp
```

然后运行一次 `/keyshot-install-addin`，并重启 KeyShot。

### 从发布 zip 或仓库安装

每个发布版本都附带 `keyshot-mcp-<version>-windows.zip`，其中 `libs/` 已经装好。解压后从第 3 步开始。没有 zip 时，从第 1 步开始。

1. 克隆仓库：
   ```
   git clone https://github.com/lfoletti/keyshot-mcp.git
   ```
2. 把 `mcp` 安装到 `libs` 文件夹。`run.py` 从那里加载它。
   ```
   py -3.12 -m pip install --target libs mcp==1.30.0
   ```
3. 把 `addin\Scripts\MCP start.py` 和 `MCP stop.py` 复制到
   `C:\Users\Public\Documents\KeyShot Studio\Scripts\`。
4. 重启 KeyShot。KeyShot 只在启动时读取 Scripts 文件夹。
5. 把服务器添加到 Claude Code：
   ```
   claude mcp add keyshot -- py -3.12 -I -S C:\path\to\keyshot-mcp\run.py
   ```
6. 检查导入是否正确：
   ```
   py -3.12 -I -S run.py --check
   ```
   输出应显示 `keyshot : imports ok` 和 33 个工具。

## 使用

1. 在 KeyShot 中打开 *Window > Scripting Console > Scripts*（窗口 > 脚本控制台 > 脚本）。
2. 选择 `MCP start`，然后点击 *Run*。控制台显示 `Pont KeyShot actif sur 127.0.0.1:1998`。
3. 在 Claude Code 中输入 `/mcp`。确认 `keyshot` 已连接。
4. 向 Claude 提问，例如：
   - “显示场景，并列出材质。”
   - “给瓶盖应用拉丝铝材质，然后渲染一张 1920 × 1080 的图片。”

要停止桥接程序，运行脚本 `MCP stop`，或关闭 KeyShot。
要更新桥接程序，复制新文件，然后使用工具 `reload_bridge`。

## 工具

| 分组 | 工具 |
|---|---|
| 场景 | `keyshot_status`, `get_scene_info`, `get_scene_tree`, `list_objects`, `set_visibility`, `screenshot`, `save_scene` |
| 相机与环境 | `list_cameras`, `set_camera`, `fit_camera`, `list_environments`, `set_environment`, `set_realtime` |
| 材质 | `list_materials`, `get_material`, `list_library_materials`, `assign_material`, `set_material_parameter`, `rename_material`, `undo_material_changes`, `commit_material_changes`, `save_material_to_library` |
| 材质节点图 | `add_material_node`, `connect_material_nodes`, `disconnect_material_input`, `remove_material_node` |
| 渲染 | `render_image`, `render_status`, `wait_for_render`, `view_image` |
| 桥接 | `lux_functions`, `reload_bridge`, `execute_python`（默认关闭） |

两个 MCP 提示词为 Claude 提供工作方法：

| 提示词 | 用途 |
|---|---|
| `keyshot_strategy` | 如何在 KeyShot 中工作而不损坏场景。 |
| `keyshot_materiaux` | 如何根据 CMF 表（颜色、材料、表面处理）或文字描述制作材质：物理数值、颜色、节点配方。 |

颜色：`[r, g, b]` 是线性值（0-1）。`#RRGGBB` 是 sRGB，桥接程序会把它转换为线性值。

## 设置

可选文件：`%LOCALAPPDATA%\keyshot-mcp\pont-config.json`。

```json
{"execute_python": false, "dossier_sorties": "C:\\path\\to\\outputs"}
```

| 设置 | 作用 |
|---|---|
| `execute_python` | 设为 `true` 时启用工具 `execute_python`。默认为 `false`。 |
| `dossier_sorties` | 截图、渲染图和场景备份的输出文件夹。 |
| `dossiers_textures` | 桥接程序可以读取纹理图片的其他文件夹列表。KeyShot 的纹理库和 `dossier_sorties` 始终允许读取。 |
| `KEYSHOT_MCP_PORT` | 环境变量。桥接端口。默认为 1998。 |
| `KEYSHOT_MCP_TIMEOUT` | 环境变量。服务器超时时间，单位为秒。默认为 60。 |
| `KEYSHOT_MCP_EXECUTE_PYTHON` | 环境变量。设为 `1` 时启用 `execute_python`。 |

桥接程序在同一文件夹中写入 `pont-actif.json`（端口、令牌、KeyShot 进程 PID）和 `pont.log`。

## 安全

- 桥接程序只监听 127.0.0.1。每个请求都必须带有 `pont-actif.json` 中的令牌。
- `execute_python` 默认关闭。只有本地设置才能启用它。
- 工具只在桥接程序创建的副本上编辑材质节点图。
- `set_camera` 不会丢弃未保存的相机视图。
- `save_scene` 会保留旧 `.bip` 文件的副本。

## 测试

测试使用一个模拟的 `lux` 模块，不需要 KeyShot。

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
py -3.13 test_cli.py
py -3.13 test_publication.py
py -3.13 test_plugin.py
py -3.13 test_dev_version.py
```

`test_pont.py` 有 87 个桥接程序测试。`test_serveur_mcp.py` 有 9 个端到端测试。`test_cli.py` 测试命令 `keyshot-mcp`。`test_publication.py` 和 `test_plugin.py` 检查 PyPI、MCP 注册表和插件文件，并检查 README 与代码保持一致。`test_dev_version.py` 测试 TestPyPI 版本工具。`essai_*.py` 文件需要打开的 KeyShot。

`test_serveur_mcp.py` 用运行测试的 Python 启动服务器。如果 `libs` 中的包是为另一个 Python 版本安装的，请把 `KEYSHOT_MCP_PYTHON` 设为对应的 `python.exe`。

## 参与贡献

请阅读 [CONTRIBUTING.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CODE_OF_CONDUCT.md)（英文）。Issue 和讨论请尽量使用英文。

## 状态

keyshot-mcp 是一个可用的原型。已在 Windows 上用 KeyShot Studio 2026.2 Pro 测试。

- 桥接程序使用 KeyShot 脚本 API（`lux`）。新的 KeyShot 版本可能会改变这个 API。
- KeyShot 未来的版本可能会加入自己的 Claude 集成。届时本项目可能停止。
- 反馈优先于新功能。请使用 issue 模板 *Bug* 和 *Feedback*。

## 免责声明

keyshot-mcp 是一个独立项目。它与 Luxion 或 KeyShot 没有关联，目前也未获得 Luxion 的认可或赞助。KeyShot 是 Luxion 的商标。

## 许可证

MIT

---

本文件译自 [README.md](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md)。两者不一致时，以英文版为准。
