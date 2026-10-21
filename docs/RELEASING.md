# 发版

一次发版是升一个版本号、合并到 `main`，然后在 Actions 里触发 `release`
工作流，它会打标签并建 Release。

**不要本地打标签。** 标签和 Release 是两个对象，分开手做会漏。

分支推送不发布任何东西。

## 清单

1. 在 `dev` 上定 `X.Y.Z`。**版本号有三处，一起改**：

   | 文件 | 形式 | 谁读 |
   | --- | --- | --- |
   | `metadata.yaml` | `v0.1.0`（**带 `v` 前缀**） | AstrBot |
   | `pyproject.toml` | `0.1.0`（不带前缀） | 本地构建与打包 |
   | `uv.lock` | `0.1.0`（`uv lock` 生成） | 锁定依赖 |

   只改前两处会漏 lock，`test/test_metadata.py::test_三处版本号一致` 会拦下。
   改完 `pyproject.toml` 记得跑 `uv lock`。

   `docs/CHANGELOG.md` 的首个小节标题要写成 `## [X.Y.Z] - YYYY-MM-DD`，
   工作流按这个格式去取 Release 说明。

2. 跑检查：

   ```sh
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest
   ```

3. 提交并推开发分支：

   ```sh
   git commit -am "chore: release X.Y.Z"
   git push origin dev
   ```

4. 等这个分支的 CI 变绿。此时什么都没发布。

5. 合并到 `main`：

   ```sh
   git switch main
   git pull
   git merge --no-ff dev -m "merge: dev -> main"
   git push origin main
   ```

6. 在 Actions 里触发 `release` 工作流 → Run workflow → 填版本号（带 `v`）。

   工作流会自己完成剩下的事，每一步前先检查：触发的是 `main`、版本号格式、
   三处版本号一致、`main` 的 CI 绿、标签未被占用、发布包里没有 `test/` 和
   `.github/` 且有 `main.py`。然后打标签（显式写 `main`）、建 Release。

## 当前不上插件市场

`logo.png` 没做，也不去 <https://cloud.astrbot.app/publish> 提交。要上市场时：

1. 补 `logo.png`（256×256、RGB 无 alpha，文件名是 AstrBot 硬编码的）
2. 在 `release.yml` 的「确认发布包内容」里加回 logo 检查
3. 每个版本都要去 publish 页面重新提交一次——市场不跟 GitHub Release 走

## 部署

见 `docs/DEPLOY.md`。

## `requirements.txt` 是手写的

不要用 `uv export` 生成。原因：

- `uv export` 会把每个包钉成 `==`。AstrBot 装插件时把这份清单喂给 pip，
  而 pip 装在与核心同一的环境里；核心给这些包装了版本护栏，插件若要求精确
  版本，护栏会拦下 pip，安装整体失败。
- 它还会把传递依赖全部展开写进去，而插件只需要声明直接依赖。

加依赖时**两边一起改**：`pyproject.toml` 的 `dependencies` 与
`requirements.txt`。约束由 `test/test_requirements.py` 钉住。
