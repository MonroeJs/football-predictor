# 执行计划：Git + 测试 + CI

基于设计文档 `2026-06-03-git-test-ci-design.md`

## 任务 1：Git 初始化 + 基础配置

**文件：**
- `.gitignore`
- `requirements-dev.txt`
- `pyproject.toml`
- 设置 git user.name / user.email

**验证：**
- `git status` 干净
- `.gitignore` 正确忽略 `__pycache__/`, `data/`, `models/`, `.venv/`, `*.pyc`
- `requirements-dev.txt` 包含 pytest>=7, pytest-cov>=4

## 任务 2：第一个测试（KellyCalculator）

**文件：**
- `tests/__init__.py`
- `tests/test_betting_system.py`

**测试内容：**
- `test_kelly_fraction_normal` — prob=0.6, odds=2.5 → f ≈ 0.267
- `test_kelly_fraction_no_edge` — prob=0.5, odds=2.0 → f = 0.0 (无 edge)
- `test_kelly_fraction_boundary` — prob=0, odds=1 → f = 0.0
- `test_expected_value_positive` — prob=0.6, odds=2.0 → EV > 0
- `test_expected_value_negative` — prob=0.4, odds=2.0 → EV < 0
- `test_implied_prob` — odds=2.0 → implied_prob=0.5
- `test_edge_positive` — prob=0.6, odds=1.8 → edge > 0

**TDD 流程：** 每个测试先写 → 确认 fail → 再实现 → 确认 pass

**验证：**
- `pytest tests/ -v` 全部通过

## 任务 3：GitHub Actions

**文件：**
- `.github/workflows/test.yml`

**工作流：**
- on: push, pull_request (main 分支)
- Python 3.11
- 安装依赖: `pip install -r requirements.txt -r requirements-dev.txt`
- 跑: `pytest tests/ -v --tb=short`

**验证：**
- 文件写入正确

## 最终验证

- `git log --oneline` 干净
- `pytest tests/ -v` 全部通过
- 推送到 GitHub 后 Actions 能跑
