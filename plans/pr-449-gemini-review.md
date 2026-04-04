# PR #449：Gemini CLI（非 API）代码审查操作手册

本手册配合仓库内脚本与资源使用，**不修改计划文件**；审查由本机已登录的 Gemini CLI（订阅 / 非 `GEMINI_API_KEY`）执行。

## 1. 前置条件

- 已安装 [Gemini CLI](https://github.com/google-gemini/gemini-cli)，`gemini --version` 可执行。
- **非 API 模式**：不要在环境中设置 `GEMINI_API_KEY`（脚本会 `unset`）。使用 `gemini login` 完成登录，`gemini whoami` 显示已登录即可。
- 可选：`jq`（仅在使用 `--json` 输出时解析）；`python3`（脚本用其读取 `meta.json`）。

## 2. 核对 PR 与 Issue

- PR：<https://gitcode.com/openeuler/yuanrong-datasystem/pull/449>
- Issue：[#234](https://gitcode.com/openeuler/yuanrong-datasystem/issues/234)（本次 AR 主体）、[#233](https://gitcode.com/openeuler/yuanrong-datasystem/issues/233)、[#235](https://gitcode.com/openeuler/yuanrong-datasystem/issues/235)

在 PR 页面记下 **Base 分支** 与 **Head 分支**（或 commit），与本地 `workspace/inputs/pr-<id>/meta.json` 中的 `base_ref` / `head_ref` 保持一致（位于 `workspace/`，默认不提交，首次运行脚本会自动生成）。

## 3. 配置 `meta.json`

编辑本地 `workspace/inputs/pr-<id>/meta.json`：

1. 若 `fetch` 里 `pr_head` 在 GitCode 上失败，改为 **fork_branch** 方式，填入贡献者仓库 URL 与 PR 实际分支名（见 [docs/meta-json.md](../docs/meta-json.md)）。
2. 若需排除部分路径（如仅审 `src/`），在 `diff.exclude_paths` 中加入路径片段或留空表示全量 diff。

## 4. 生成 diff 并运行审查

在仓库根目录（`code-review/`）执行：

```bash
./scripts/review-pr.sh 449
```

脚本会：

- 在 `workspace/pr-449/repo` clone 或更新上游仓库并执行 `meta.json` 中的 `fetch`
- 写入 `workspace/pr-449/diff.patch`
- 将 **diff 经 stdin** 送入 `gemini -p`；提示词由三文件拼接：**[system-pr-449.md](../assets/prompts/system-pr-449.md)** + **[GEM.md](../assets/gems/yuanrong-pr-review/GEM.md)** + **[review-evidence-rubric.md](../assets/prompts/review-evidence-rubric.md)**（与网页 Gems 同源，要求**有摘录、有改法**），避免巨型命令行参数
- 输出到 `results/pr-449/review.md`，stderr 写入 `results/pr-449/stderr.log`，运行日志 `workspace/pr-449/run.log`

### JSON 原始响应（可选）

```bash
./scripts/review-pr.sh 449 --json
```

会额外写入 `results/pr-449/review.json`（需本机 Gemini CLI 支持 `--output-format json`）。

## 5. 超大 diff 时的策略

若单次审查超上下文或超时：

1. 查看 `workspace/pr-449/diff.patch` 的 `git diff --stat`（脚本可在 `run.log` 前打印统计，或手动在 `repo` 内执行）。
2. 按目录拆分多次调用：临时修改 `meta.json` 中 `base_ref`/`head_ref` 不变，用 `git diff base...head -- path1 path2` 生成较小 patch，多次运行脚本（可将 patch 路径改为手动管道，见脚本注释）。
3. 优先覆盖二级缓存、分布式磁盘、故障恢复相关路径。

## 6. 将结果用于 GitCode

1. 阅读 `results/pr-449/review.md`，区分 **必须修改** 与 **建议**。
2. 将摘要与关键评论粘贴到 PR 讨论区；可引用 Issue #234–235 说明已对照 AR 审查。
3. 中间目录 `workspace/`（含 `workspace/inputs/`）可随时删除后由脚本重建；`results/` 是否纳入版本控制由团队约定。

## 7. Cursor Skill（可选）

复用同一套审查标准时，可将 [assets/skills/yuanrong-pr-review/SKILL.md](../assets/skills/yuanrong-pr-review/SKILL.md) 复制到项目 `.cursor/skills/` 或个人 `~/.cursor/skills/`，供 Cursor Agent 在编辑器内对照（与 CLI 提示词内容应对齐维护）。

## 8. Gemini 网页 Gem（可选）

在 **Gemini** 中新建 Gem，将 [assets/gems/yuanrong-pr-review/GEM.md](../assets/gems/yuanrong-pr-review/GEM.md) 全文粘贴为指令；手动审查时把 **git diff** 贴在对话里即可。行为应与 CLI 使用的「三文件拼接」一致；详见 [assets/gems/README.md](../assets/gems/README.md)。
