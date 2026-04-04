# `workspace/inputs/pr-<id>/meta.json` 说明

目录 **`workspace/inputs/`** 由脚本在首次运行时生成（[`bootstrap_meta.py`](../scripts/lib/bootstrap_meta.py)），与 clone、diff 等一同放在 **`workspace/`** 下（该目录默认不纳入 git，见仓库根目录 `.gitignore`）。以下内容供本地编辑参考。

## 字段

| 字段 | 含义 |
|------|------|
| `pr_url` | GitCode PR 页面，用于核对 base/head、发帖 API |
| `upstream_git` | openeuler 官方仓库 clone 地址 |
| `related` | **推荐**：与本 PR 的追溯信息，会注入 Gemini 提示词（见下） |
| `issues` | 可选；**旧式** `{{ "name": "url" }}` 字典，仍会被合并进追溯块 |
| `diff.base_ref` | 基线 ref（fetch 后存在），如 `origin/master` |
| `diff.head_ref` | PR 头 ref，如 `pr-449-head` 或 `contributor/feature-xxx` |
| `diff.exclude_paths` | 可选；传给 `git diff` 的排除 glob |
| `diff.fetch` | 在 `workspace/pr-<id>/repo` 内执行的拉取步骤 |

## `related`（PR ↔ Issue / RFC）

`review-pr.sh` 会把本节内容拼进提示词末尾的 **Traceability** 段，要求审查结论在可行时 **对应到具体 Issue 或 RFC**。

```json
"related": {
  "description": "One-line: what this PR is for (optional).",
  "issues": [
    "https://gitcode.com/openeuler/yuanrong-datasystem/issues/234",
    { "title": "AR1 disk cache", "url": "https://gitcode.com/.../issues/234" }
  ],
  "rfcs": [
    "https://example.com/rfc-secondary-cache.md"
  ],
  "closes": [234, 235]
}
```

- **`issues` / `rfcs`**：字符串 URL，或带 `title`/`label` + `url` 的对象。
- **`closes`**：可选；期望关闭或关联的 issue 编号或说明（展示用）。
- 若留空，提示词会标明「未列出」，审查仍可进行，但建议在 PR 有明确关联时填上。

### 命令行传入（推荐）

无需手改文件即可写入 `related`：

```bash
./scripts/review-pr.sh 470 --issues 234,233,235
./scripts/review-pr.sh 449 --issues 234 --rfcs 'https://example.com/a|https://example.com/b'
```

会调用 `merge_meta_cli.py` 更新 `workspace/inputs/pr-<id>/meta.json`，并同步 `pr_url` / `pr_number`。使用 `--issues` 时会**移除**旧式顶层 `issues` 字典，避免与 `related.issues` 重复。

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
