# keyshot-mcp

[English](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md) | [简体中文](https://github.com/lfoletti/keyshot-mcp/blob/main/README.zh-CN.md) | [日本語](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ja.md) | 한국어 | [Deutsch](https://github.com/lfoletti/keyshot-mcp/blob/main/README.de.md)

Model Context Protocol(MCP)을 사용해 Claude Code에서 열려 있는 KeyShot Studio 2026 창을 제어합니다.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-orange.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ko.md#상태)
[![Tests](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/lfoletti/keyshot-mcp)](https://github.com/lfoletti/keyshot-mcp/releases)
[![PyPI](https://img.shields.io/pypi/v/keyshot-mcp)](https://pypi.org/project/keyshot-mcp/)

> **상태: 프로토타입.** 도구는 작동하며 테스트도 있습니다. 하지만 이 프로젝트는 KeyShot의 스크립팅 API에 의존하며, 이 API는 바뀔 수 있습니다. 어떤 기능을 쓰는지, 무엇이 실패하는지 알려 주세요. issue나 토론을 열어 주세요.

![Claude Code가 KeyShot 장면을 읽고, 병의 유리를 세 번 바꾼 다음, 모든 변경을 되돌립니다.](https://raw.githubusercontent.com/lfoletti/keyshot-mcp/main/docs/demo.gif)

*데모는 실제보다 3배 빠르게 재생됩니다.*

```
Claude Code ⇄ MCP 서버 keyshotmcp (Python 3.12, stdio)
            ⇄ TCP 127.0.0.1:1998, 4바이트 길이 + JSON, 토큰
            ⇄ MCP start.py (KeyShot 안, UI 스레드의 타이머)
```

브리지는 KeyShot 안에서 실행됩니다. 서버는 Claude Code 안에서 실행됩니다. 둘은 로컬 컴퓨터에서만 통신합니다.

## 요구 사항

| 항목 | 버전 |
|---|---|
| KeyShot Studio | 15.1(2026) 이상. 2026.2 Pro(15.1.2.7)에서 테스트했습니다. |
| Python | 3.12 이상, Windows |
| `mcp` | 1.30.0 |
| Claude Code | 최신 버전이면 됩니다 |

## 설치

### PyPI에서 설치

버전 1.1.0부터 `keyshot-mcp`는 Python 패키지입니다. [uv](https://docs.astral.sh/uv/)를 사용합니다:

```
uvx keyshot-mcp install-addin
claude mcp add keyshot -- uvx keyshot-mcp
```

`install-addin`은 두 개의 브리지 스크립트를 `%PUBLIC%\Documents\KeyShot Studio\Scripts`(또는 `--dir`로 지정한 폴더)에 복사합니다. 그런 다음 KeyShot을 다시 시작하세요.

### Claude Code 플러그인으로 설치

버전 1.1.0부터 이 저장소는 Claude Code 마켓플레이스이기도 합니다. 플러그인 `keyshot`은 `uvx`로 서버를 시작하므로 [uv](https://docs.astral.sh/uv/)가 설치되어 있어야 합니다.

```
/plugin marketplace add lfoletti/keyshot-mcp
/plugin install keyshot@keyshot-mcp
```

그런 다음 `/keyshot-install-addin`을 한 번 실행하고 KeyShot을 다시 시작하세요.

### 릴리스 zip 또는 저장소에서 설치

각 릴리스에는 `libs/`가 이미 채워진 `keyshot-mcp-<version>-windows.zip`이 있습니다. 압축을 풀고 3단계부터 시작하세요. zip이 없으면 1단계부터 시작합니다.

1. 저장소를 복제합니다:
   ```
   git clone https://github.com/lfoletti/keyshot-mcp.git
   ```
2. `mcp`를 `libs` 폴더에 설치합니다. `run.py`는 그곳에서 불러옵니다.
   ```
   py -3.12 -m pip install --target libs mcp==1.30.0
   ```
3. `addin\Scripts\MCP start.py`와 `MCP stop.py`를
   `C:\Users\Public\Documents\KeyShot Studio\Scripts\`에 복사합니다.
4. KeyShot을 다시 시작합니다. KeyShot은 시작할 때만 Scripts 폴더를 읽습니다.
5. 서버를 Claude Code에 추가합니다:
   ```
   claude mcp add keyshot -- py -3.12 -I -S C:\path\to\keyshot-mcp\run.py
   ```
6. 가져오기가 올바른지 확인합니다:
   ```
   py -3.12 -I -S run.py --check
   ```
   출력에 `keyshot : imports ok`와 33개의 도구가 표시됩니다.

## 사용법

1. KeyShot에서 *Window > Scripting Console > Scripts*(창 > 스크립팅 콘솔 > 스크립트)를 엽니다.
2. `MCP start`를 선택하고 *Run*을 클릭합니다. 콘솔에 `Pont KeyShot actif sur 127.0.0.1:1998`이 표시됩니다.
3. Claude Code에서 `/mcp`를 입력합니다. `keyshot`이 연결되어 있는지 확인합니다.
4. Claude에게 요청합니다. 예:
   - "장면을 보여 주고 재질 목록을 알려 줘."
   - "뚜껑에 브러시드 알루미늄을 적용하고 1920 × 1080으로 렌더링해 줘."

브리지를 멈추려면 스크립트 `MCP stop`을 실행하거나 KeyShot을 닫습니다.
브리지를 업데이트하려면 새 파일을 복사한 다음 도구 `reload_bridge`를 사용합니다.

## 도구

| 그룹 | 도구 |
|---|---|
| 장면 | `keyshot_status`, `get_scene_info`, `get_scene_tree`, `list_objects`, `set_visibility`, `screenshot`, `save_scene` |
| 카메라와 환경 | `list_cameras`, `set_camera`, `fit_camera`, `list_environments`, `set_environment`, `set_realtime` |
| 재질 | `list_materials`, `get_material`, `list_library_materials`, `assign_material`, `set_material_parameter`, `rename_material`, `undo_material_changes`, `commit_material_changes`, `save_material_to_library` |
| 재질 그래프 | `add_material_node`, `connect_material_nodes`, `disconnect_material_input`, `remove_material_node` |
| 렌더링 | `render_image`, `render_status`, `wait_for_render`, `view_image` |
| 브리지 | `lux_functions`, `reload_bridge`, `execute_python`(기본값: 꺼짐) |

두 개의 MCP 프롬프트가 Claude에게 작업 방법을 알려 줍니다:

| 프롬프트 | 용도 |
|---|---|
| `keyshot_strategy` | 장면을 손상시키지 않고 KeyShot에서 작업하는 방법. |
| `keyshot_materiaux` | CMF 시트(색상, 소재, 마감) 또는 설명으로 재질을 만드는 방법: 물리 값, 색상, 노드 레시피. |

색상: `[r, g, b]`는 선형 값(0-1)입니다. `#RRGGBB`는 sRGB이며, 브리지가 선형 값으로 변환합니다.

## 설정

선택 파일: `%LOCALAPPDATA%\keyshot-mcp\pont-config.json`.

```json
{"execute_python": false, "dossier_sorties": "C:\\path\\to\\outputs"}
```

| 설정 | 효과 |
|---|---|
| `execute_python` | `true`이면 도구 `execute_python`을 켭니다. 기본값은 `false`입니다. |
| `dossier_sorties` | 스크린샷, 렌더링, 장면 백업을 저장할 폴더. |
| `dossiers_textures` | 브리지가 텍스처 이미지를 읽을 수 있는 추가 폴더 목록. KeyShot 텍스처 라이브러리와 `dossier_sorties`는 항상 허용됩니다. |
| `KEYSHOT_MCP_PORT` | 환경 변수. 브리지 포트. 기본값은 1998입니다. |
| `KEYSHOT_MCP_TIMEOUT` | 환경 변수. 서버 시간 제한(초). 기본값은 60입니다. |
| `KEYSHOT_MCP_EXECUTE_PYTHON` | 환경 변수. `1`이면 `execute_python`을 켭니다. |

브리지는 같은 폴더에 `pont-actif.json`(포트, 토큰, KeyShot PID)과 `pont.log`를 씁니다.

## 보안

- 브리지는 127.0.0.1에서만 수신합니다. 모든 요청에는 `pont-actif.json`의 토큰이 있어야 합니다.
- `execute_python`은 꺼져 있습니다. 로컬 설정으로만 켤 수 있습니다.
- 도구는 브리지가 만든 사본에서만 재질 그래프를 편집합니다.
- `set_camera`는 저장되지 않은 카메라 뷰를 버리지 않습니다.
- `save_scene`은 이전 `.bip` 파일의 사본을 남깁니다.

## 테스트

테스트는 가짜 `lux` 모듈을 사용합니다. KeyShot이 필요하지 않습니다.

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
py -3.13 test_cli.py
py -3.13 test_publication.py
py -3.13 test_plugin.py
py -3.13 test_dev_version.py
```

`test_pont.py`에는 87개의 브리지 테스트가 있습니다. `test_serveur_mcp.py`에는 9개의 종단 간 테스트가 있습니다. `test_cli.py`는 명령 `keyshot-mcp`를 테스트합니다. `test_publication.py`와 `test_plugin.py`는 PyPI, MCP 레지스트리, 플러그인 파일을 확인하고, README가 코드와 일치하는지 확인합니다. `test_dev_version.py`는 TestPyPI 버전 도구를 테스트합니다. `essai_*.py` 파일은 열려 있는 KeyShot이 필요합니다.

`test_serveur_mcp.py`는 테스트를 실행하는 Python으로 서버를 시작합니다. `libs`의 패키지가 다른 Python 버전용이면 `KEYSHOT_MCP_PYTHON`을 해당 `python.exe`로 설정하세요.

## 기여

[CONTRIBUTING.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CONTRIBUTING.md)와 [CODE_OF_CONDUCT.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CODE_OF_CONDUCT.md)(영어)를 읽어 주세요. issue와 토론은 가능하면 영어로 작성해 주세요.

## 상태

keyshot-mcp는 작동하는 프로토타입입니다. Windows의 KeyShot Studio 2026.2 Pro에서 테스트했습니다.

- 브리지는 KeyShot 스크립팅 API(`lux`)를 사용합니다. 새 KeyShot 버전에서 이 API가 바뀔 수 있습니다.
- 향후 KeyShot 버전에 자체 Claude 통합이 추가될 수 있습니다. 그러면 이 프로젝트는 중단될 수 있습니다.
- 새 기능보다 피드백이 우선입니다. issue 템플릿 *Bug*와 *Feedback*을 사용해 주세요.

## 면책 조항

keyshot-mcp는 독립 프로젝트입니다. Luxion 또는 KeyShot과 제휴하지 않았으며, 현재까지 Luxion의 보증이나 후원을 받지 않습니다. KeyShot은 Luxion의 상표입니다.

## 라이선스

MIT

---

이 파일은 [README.md](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md)의 번역입니다. 내용이 다를 경우 영어판이 우선합니다.
