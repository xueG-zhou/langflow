# LFX 单独打包计划

> 目标：把 `src/lfx` 作为独立包打包（sdist + wheel），**不推送到 PyPI**，并在本地 venv 中验证产物可用。

## 现状要点

- `src/lfx/pyproject.toml` 已是完整的可独立发布的包定义：
  - `name = "lfx"`，`version = "1.11.0"`
  - build-backend = `hatchling`
  - wheel packages 指向 `src/lfx`
  - 暴露 `lfx` / `lfx-mcp` 两个 CLI 入口（`[project.scripts]`）
- `lfx = { workspace = true }`（根 `pyproject.toml:106`）只是把 lfx 标记为 workspace 成员，不影响独立 `uv build` 出包。
- 工程里已有现成入口，但都不直接合适：
  - `make lfx_build`（根 `Makefile:459`）→ 走 `src/lfx/Makefile` 的 `build` target，里面用了 `@rm -rf dist/` 和 `find ... -exec rm`，是 Unix 语法，Windows PowerShell/cmd 下会失败。
  - `scripts/release-lfx.sh` 也跑了 `uv build`，但同时改版本号、git commit、git tag，面向完整发布，不符合"只打包不发布"的需求。
- `src/lfx/dist/` 已在 `.gitignore` 中，产物不会污染仓库。

## 执行步骤

### 第 1 步：环境前置检查

```powershell
# 确认 uv 可用、当前在仓库根、版本号确认
uv --version
Test-Path src/lfx/pyproject.toml
Select-String -Path src/lfx/pyproject.toml -Pattern '^version'
```

**预期：** uv ≥ 0.4（实测 0.11.25），`pyproject.toml` 存在，`version = "1.11.0"`。

### 第 2 步：清理旧产物（避免混入旧文件）

```powershell
Remove-Item -Recurse -Force src/lfx/dist -ErrorAction SilentlyContinue
```

`src/lfx/dist/` 已被 .gitignore 忽略，删除安全。

### 第 3 步：同时打 sdist + wheel

```powershell
uv build --package lfx --out-dir src/lfx/dist
```

**预期产物：**
- `src/lfx/dist/lfx-1.11.0.tar.gz`（源码包）
- `src/lfx/dist/lfx-1.11.0-py3-none-any.whl`（wheel）

### 第 4 步：列出产物确认

```powershell
Get-ChildItem src/lfx/dist | Select-Object Name, Length, LastWriteTime
```

### 第 5 步：本地安装验证（临时 venv，不污染主环境，不碰 PyPI）

```powershell
# 新建干净 venv
uv venv .venv-lfx-test

# 用该 venv 的 python 安装刚打的 wheel
uv pip install --python .venv-lfx-test\Scripts\python.exe src/lfx/dist/lfx-1.11.0-py3-none-any.whl

# 验证两个 CLI 入口都能跑
& .venv-lfx-test\Scripts\lfx.exe --help
& .venv-lfx-test\Scripts\lfx-mcp.exe --help
```

**预期：** 两条 `--help` 都正常输出帮助文本，证明 wheel 包含 entry point 且依赖能解析。

### 第 6 步：清理临时 venv（验证通过后）

```powershell
Remove-Item -Recurse -Force .venv-lfx-test
```

保留 `src/lfx/dist/` 里的产物供后续使用。

## 全程不做的操作

- ❌ `uv publish` / `make lfx_publish` / `make lfx_publish_testpypi`（不推 PyPI）
- ❌ `scripts/release-lfx.sh`（不 commit、不 tag）
- ❌ 修改 `src/lfx/pyproject.toml` 的 version 或任何配置文件

## 可选变体

| 需求 | 命令 |
|---|---|
| 只要 wheel | `uv build --package lfx --wheel --out-dir src/lfx/dist` |
| 只要 sdist | `uv build --package lfx --sdist --out-dir src/lfx/dist` |
| 不走 workspace，直接按路径打 | `uv build src/lfx --out-dir src/lfx/dist` |

## 产物用途

- **本地分发**：把 `.whl` 拷给同事或部署脚本，`uv pip install lfx-1.11.0-py3-none-any.whl` 即可。
- **临时运行**：`uvx --from src/lfx/dist/lfx-1.11.0-py3-none-any.whl lfx --help`，不在系统里留安装。
- **后续若要发布到 PyPI**：再单独执行 `uv publish src/lfx/dist/*`（需要 PyPI token），不在本计划范围内。
