# Git 初始化 + 测试框架 + GitHub Actions 设计文档

## 1. 为什么要做

- 项目目前没有版本控制，改代码不敢改，改坏了回不去
- 没有测试，任何改动全靠肉眼验证，质量没保障
- 没有 CI，改完要手动跑，容易遗漏

## 2. 目标

```
初始化 Git → 加 .gitignore → 配 pytest → 写第一个测试 → 配 GitHub Actions
```

## 3. 文件清单

| 文件 | 说明 |
|------|------|
| `.gitignore` | Python 标准忽略清单（`__pycache__/`、`.venv/`、`data/`、`models/`、`*.pyc`等） |
| `.github/workflows/test.yml` | GitHub Actions 工作流 — push/PR 时跑 pytest |
| `requirements-dev.txt` | 开发依赖（pytest, pytest-cov） |
| `tests/` | 测试目录 |
| `tests/test_betting_system.py` | 第一个测试 — KellyCalculator 单元测试 |
| `tests/__init__.py` | 空文件，标记包 |
| `pyproject.toml` (或更新) | pytest 配置 |

## 4. 架构设计

```
football-predictor/
├── .github/
│   └── workflows/
│       └── test.yml          # GitHub Actions: push/PR → pytest
├── tests/
│   ├── __init__.py
│   └── test_betting_system.py # KellyCalculator 单元测试（第一组）
├── .gitignore
├── requirements.txt           # 已有，不动
├── requirements-dev.txt       # 新增：pytest 等开发依赖
└── pyproject.toml             # 新增：pytest 配置
```

## 5. 任务分解

### 任务 1：初始化 Git + 基础文件
- `git init`
- 写 `.gitignore`
- 写 `requirements-dev.txt`
- 写 `pyproject.toml`（pytest 配置）
- `git add + git commit`

### 任务 2：写第一个测试（KellyCalculator）
- 创建 `tests/` 目录
- 写 `test_betting_system.py` — 测试 KellyCalculator 的三个方法：
  - `kelly_fraction()` — 正常情况、边界（odds=1、prob=0）
  - `expected_value()` — 正 EV / 负 EV
  - `edge()` — 正 edge / 负 edge
- 跑通 pytest，确认测试 fail → pass 流程
- `git commit`

### 任务 3：配 GitHub Actions
- 写 `.github/workflows/test.yml`
- 配置：Python 3.11/3.12、安装依赖、跑 pytest
- 只测关键路径，不依赖外部 API（赔率/xG）
- `git commit`

### 任务 4：最终验证
- pytest 全跑通过
- git log 干净
- 汇报完成

## 6. 不做的范围（YAGNI）

- ❌ 不上传 xG 缓存 / 模型文件到 Git
- ❌ 不改已有代码
- ❌ 不加 pre-commit hooks
- ❌ 不加 codecov（后面再加）

## 7. 风险

- 远程 GitHub 仓库需要大哥自己创建，我只管本地 Git + workflow 文件
- 某些测试可能依赖数据文件 → 确保测试只测纯逻辑，不碰 I/O
