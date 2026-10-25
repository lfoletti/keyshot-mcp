# keyshot-mcp

[English](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md) | [简体中文](https://github.com/lfoletti/keyshot-mcp/blob/main/README.zh-CN.md) | [日本語](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ja.md) | [한국어](https://github.com/lfoletti/keyshot-mcp/blob/main/README.ko.md) | Deutsch

Ein geöffnetes Fenster von KeyShot Studio 2026 aus Claude Code steuern, mit dem Model Context Protocol (MCP).

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-orange.svg)](https://github.com/lfoletti/keyshot-mcp/blob/main/README.de.md#status)
[![Tests](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/lfoletti/keyshot-mcp/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/lfoletti/keyshot-mcp)](https://github.com/lfoletti/keyshot-mcp/releases)
[![PyPI](https://img.shields.io/pypi/v/keyshot-mcp)](https://pypi.org/project/keyshot-mcp/)

> **Status: Prototyp.** Die Werkzeuge funktionieren und haben Tests. Das Projekt hängt aber von der Skript-API von KeyShot ab, und diese API kann sich ändern. Sag uns, was du nutzt und was nicht funktioniert: Öffne ein Issue oder eine Diskussion.

![Claude Code liest die KeyShot-Szene, ändert dreimal das Glas der Flasche und macht dann alle Änderungen rückgängig.](https://raw.githubusercontent.com/lfoletti/keyshot-mcp/main/docs/demo.gif)

*Die Demo läuft dreimal schneller als in Echtzeit.*

```
Claude Code ⇄ MCP-Server keyshotmcp (Python 3.12, stdio)
            ⇄ TCP 127.0.0.1:1998, 4 Byte Länge + JSON, Token
            ⇄ MCP start.py (in KeyShot, Timer im UI-Thread)
```

Die Brücke läuft in KeyShot. Der Server läuft in Claude Code. Die beiden sprechen nur auf dem lokalen Computer miteinander.

## Voraussetzungen

| Element | Version |
|---|---|
| KeyShot Studio | 15.1 (2026) oder neuer. Getestet mit 2026.2 Pro (15.1.2.7). |
| Python | 3.12 oder neuer, Windows |
| `mcp` | 1.30.0 |
| Claude Code | jede aktuelle Version |

## Installation

### Von PyPI

Ab Version 1.1.0 ist `keyshot-mcp` ein Python-Paket. Mit [uv](https://docs.astral.sh/uv/):

```
uvx keyshot-mcp install-addin
claude mcp add keyshot -- uvx keyshot-mcp
```

`install-addin` kopiert die zwei Brückenskripte nach `%PUBLIC%\Documents\KeyShot Studio\Scripts` (oder in den Ordner von `--dir`). Starte KeyShot danach neu.

### Als Plugin für Claude Code

Ab Version 1.1.0 ist dieses Repository auch ein Marketplace für Claude Code. Das Plugin `keyshot` startet den Server mit `uvx`, deshalb muss [uv](https://docs.astral.sh/uv/) installiert sein.

```
/plugin marketplace add lfoletti/keyshot-mcp
/plugin install keyshot@keyshot-mcp
```

Führe dann einmal `/keyshot-install-addin` aus und starte KeyShot neu.

### Aus dem Release-Zip oder dem Repository

Jedes Release enthält `keyshot-mcp-<version>-windows.zip`, in dem `libs/` schon gefüllt ist. Entpacke es und beginne bei Schritt 3. Ohne das Zip beginnst du bei Schritt 1.

1. Klone das Repository:
   ```
   git clone https://github.com/lfoletti/keyshot-mcp.git
   ```
2. Installiere `mcp` in den Ordner `libs`. `run.py` lädt es von dort.
   ```
   py -3.12 -m pip install --target libs mcp==1.30.0
   ```
3. Kopiere `addin\Scripts\MCP start.py` und `MCP stop.py` nach
   `C:\Users\Public\Documents\KeyShot Studio\Scripts\`.
4. Starte KeyShot neu. KeyShot liest den Ordner Scripts nur beim Start.
5. Füge den Server zu Claude Code hinzu:
   ```
   claude mcp add keyshot -- py -3.12 -I -S C:\path\to\keyshot-mcp\run.py
   ```
6. Prüfe, ob die Importe stimmen:
   ```
   py -3.12 -I -S run.py --check
   ```
   Die Ausgabe zeigt `keyshot : imports ok` und 33 Werkzeuge.

## Verwendung

1. Öffne in KeyShot *Window > Scripting Console > Scripts* (Fenster > Skriptkonsole > Skripte).
2. Wähle `MCP start` und klicke auf *Run*. Die Konsole zeigt `Pont KeyShot actif sur 127.0.0.1:1998`.
3. Gib in Claude Code `/mcp` ein. Prüfe, ob `keyshot` verbunden ist.
4. Frag Claude, zum Beispiel:
   - «Zeig mir die Szene und liste die Materialien auf.»
   - «Gib dem Deckel gebürstetes Aluminium und mach ein Rendering in 1920 × 1080.»

Um die Brücke zu stoppen, führe das Skript `MCP stop` aus oder schliesse KeyShot.
Um die Brücke zu aktualisieren, kopiere die neue Datei und nutze dann das Werkzeug `reload_bridge`.

## Werkzeuge

| Gruppe | Werkzeuge |
|---|---|
| Szene | `keyshot_status`, `get_scene_info`, `get_scene_tree`, `list_objects`, `set_visibility`, `screenshot`, `save_scene` |
| Kameras und Umgebung | `list_cameras`, `set_camera`, `fit_camera`, `list_environments`, `set_environment`, `set_realtime` |
| Materialien | `list_materials`, `get_material`, `list_library_materials`, `assign_material`, `set_material_parameter`, `rename_material`, `undo_material_changes`, `commit_material_changes`, `save_material_to_library` |
| Materialgraph | `add_material_node`, `connect_material_nodes`, `disconnect_material_input`, `remove_material_node` |
| Rendering | `render_image`, `render_status`, `wait_for_render`, `view_image` |
| Brücke | `lux_functions`, `reload_bridge`, `execute_python` (standardmässig aus) |

Zwei MCP-Prompts geben Claude die Arbeitsweise vor:

| Prompt | Zweck |
|---|---|
| `keyshot_strategy` | Wie man in KeyShot arbeitet, ohne die Szene zu beschädigen. |
| `keyshot_materiaux` | Wie man Materialien aus einem CMF-Blatt (Farbe, Material, Oberfläche) oder einer Beschreibung erstellt: physikalische Werte, Farben, Node-Rezepte. |

Farben: `[r, g, b]` ist linear (0-1). `#RRGGBB` ist sRGB: Die Brücke rechnet es in linear um.

## Einstellungen

Optionale Datei: `%LOCALAPPDATA%\keyshot-mcp\pont-config.json`.

```json
{"execute_python": false, "dossier_sorties": "C:\\path\\to\\outputs"}
```

| Einstellung | Wirkung |
|---|---|
| `execute_python` | `true` schaltet das Werkzeug `execute_python` ein. Der Standard ist `false`. |
| `dossier_sorties` | Ordner für Screenshots, Renderings und Sicherungen der Szene. |
| `dossiers_textures` | Liste weiterer Ordner, aus denen die Brücke Texturbilder lesen darf. Die Texturbibliothek von KeyShot und `dossier_sorties` sind immer erlaubt. |
| `KEYSHOT_MCP_PORT` | Umgebungsvariable. Port der Brücke. Der Standard ist 1998. |
| `KEYSHOT_MCP_TIMEOUT` | Umgebungsvariable. Timeout des Servers in Sekunden. Der Standard ist 60. |
| `KEYSHOT_MCP_EXECUTE_PYTHON` | Umgebungsvariable. `1` schaltet `execute_python` ein. |

Die Brücke schreibt `pont-actif.json` (Port, Token, PID von KeyShot) und `pont.log` in denselben Ordner.

## Sicherheit

- Die Brücke hört nur auf 127.0.0.1. Jede Anfrage braucht das Token aus `pont-actif.json`.
- `execute_python` ist aus. Nur eine lokale Einstellung kann es einschalten.
- Die Werkzeuge bearbeiten einen Materialgraphen nur auf Kopien, die die Brücke angelegt hat.
- `set_camera` verwirft keine Kameraansicht, die nicht gespeichert ist.
- `save_scene` behält eine Kopie der alten `.bip`-Datei.

## Tests

Die Tests nutzen ein falsches `lux`-Modul. KeyShot ist nicht nötig.

```
cd tests
py -3.13 test_pont.py
py -3.13 test_serveur_mcp.py
py -3.13 test_cli.py
py -3.13 test_publication.py
py -3.13 test_plugin.py
py -3.13 test_dev_version.py
```

`test_pont.py` enthält 87 Tests für die Brücke. `test_serveur_mcp.py` enthält 9 End-to-End-Tests. `test_cli.py` testet den Befehl `keyshot-mcp`. `test_publication.py` und `test_plugin.py` prüfen die Dateien für PyPI, die MCP-Registry und das Plugin, und dass das README dem Code folgt. `test_dev_version.py` testet das Versionswerkzeug für TestPyPI. Die Dateien `essai_*.py` brauchen ein offenes KeyShot.

`test_serveur_mcp.py` startet den Server mit dem Python, das den Test ausführt. Wenn die Pakete in `libs` für eine andere Python-Version sind, setze `KEYSHOT_MCP_PYTHON` auf die passende `python.exe`.

## Mitwirken

Lies [CONTRIBUTING.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CONTRIBUTING.md) und [CODE_OF_CONDUCT.md](https://github.com/lfoletti/keyshot-mcp/blob/main/CODE_OF_CONDUCT.md) (auf Englisch). Schreib Issues und Diskussionen wenn möglich auf Englisch.

## Status

keyshot-mcp ist ein funktionierender Prototyp. Er ist mit KeyShot Studio 2026.2 Pro unter Windows getestet.

- Die Brücke nutzt die Skript-API von KeyShot (`lux`). Eine neue Version von KeyShot kann diese API ändern.
- KeyShot kann in einer künftigen Version eine eigene Integration mit Claude bringen. Dann kann dieses Projekt enden.
- Feedback hat Vorrang vor neuen Funktionen. Nutze die Issue-Vorlagen *Bug* und *Feedback*.

## Haftungsausschluss

keyshot-mcp ist ein unabhängiges Projekt. Es ist nicht mit Luxion oder KeyShot verbunden, und Luxion unterstützt oder sponsert es bisher nicht. KeyShot ist eine Marke von Luxion.

## Lizenz

MIT

---

Diese Datei ist eine Übersetzung von [README.md](https://github.com/lfoletti/keyshot-mcp/blob/main/README.md). Bei Abweichungen gilt die englische Fassung.
