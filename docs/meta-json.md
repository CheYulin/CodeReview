# `workspace/inputs/pr-<id>/meta.json` 说明

目录 **`workspace/inputs/`** 由脚本在首次运行时生成（[`bootstrap_meta.py`](../scripts/lib/bootstrap_meta.py)），与 clone、diff 等一同放在 **`workspace/`** 下（该目录默认不纳入 git，见仓库根目录 `.gitignore`）。以下内容供本地编辑参考。

## 字段

| 字段 | 含义 |
|------|------|
| `pr_url` | GitCode PR 页面，用于核对 base/head、发帖 API |
| `upstream_git` | openeuler 官方仓库 clone 地址 |
| `issues` | 可选；相关 issue 链接（审查上下文） |
| `diff.base_ref` | 基线 ref（fetch 后存在），如 `origin/master` |
| `diff.head_ref` | PR 头 ref，如 `pr-449-head` 或 `contributor/feature-xxx` |
| `diff.exclude_paths` | 可选；传给 `git diff` 的排除 glob |
| `diff.fetch` | 在 `workspace/pr-<id>/repo` 内执行的拉取步骤 |

## `fetch` 条目类型

- **`pr_head`**：脚本会依次尝试多种 ref。**GitCode 通常没有 `pull/N/head`**；可在 **`fork_fallback.branch`** 填 PR 源分支名，或在 `pr_head` 上增加 **`refspec`**。
- **`fork_branch`**：在贡献者 fork 上拉指定分支到本地名：

```json
{
  "type": "fork_branch",
  "remote_name": "contributor",
  "remote_url": "https://gitcode.com/<user>/yuanrong-datasystem.git",
  "remote_branch": "feature-branch",
  "local_branch": "pr-<id>-head"
}
```

令 `head_ref` 与 `local_branch` 一致。

## 与网页一致

在 PR 页面确认 **Base** 与 **Compare** 分支名，再填写 `base_ref` / `head_ref`。
