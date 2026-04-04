# code-review

本地用 **Gemini CLI**（**非 API**：`gemini login` 订阅身份，`unset GEMINI_API_KEY`）对 **GitCode PR** 做自动化代码审查：根据配置拉取上游与 PR 头提交，生成 **git diff**，再把 diff **经 stdin** 送给 `gemini -p`，避免把整份 diff 塞进命令行参数。

## 快速使用

1. 安装 [Gemini CLI](https://github.com/google-gemini/gemini-cli)，执行 `gemini login`。
2. **首次**跑某个 PR 号时，若不存在 `workspace/inputs/pr-<id>/meta.json`，[`review-pr.sh`](scripts/review-pr.sh) 会调用 [`bootstrap_meta.py`](scripts/lib/bootstrap_meta.py) **自动生成模板**。关联 Issue 可在命令行传入 **`--issues 234,233`**（见步骤 3），或编辑 meta 中的 **`related.issues` / `related.rfcs`**；字段说明见 [`docs/meta-json.md`](docs/meta-json.md)。可用环境变量覆盖默认仓库（如 `CODE_REVIEW_GITCODE_OWNER`、`CODE_REVIEW_GITCODE_REPO`、`CODE_REVIEW_UPSTREAM_GIT`）。
3. 在仓库根目录执行：

```bash
# 只指定 PR 号（默认会 bootstrap meta）
./scripts/review-pr.sh 449

# 同时传入关联 Issue 号（逗号分隔，会写入 meta 并注入 Traceability）
./scripts/review-pr.sh 470 --issues 234,233,235

# 可选：RFC 链接用 | 分隔；同时输出 JSON
./scripts/review-pr.sh 449 --issues 234 --rfcs 'https://example.com/rfc.md' --json
```

Issue URL 由环境变量 `CODE_REVIEW_GITCODE_HOST`、`CODE_REVIEW_GITCODE_OWNER`、`CODE_REVIEW_GITCODE_REPO` 拼出（与 `bootstrap_meta.py` 一致）。详见 `./scripts/review-pr.sh --help`。

**PR 源/目的与 API 校验（推荐）**：若已导出 **`GITCODE_TOKEN`**（与发帖 API 可用同一令牌），在生成 diff 之后会自动调用 [`scripts/lib/check_pr_refs.py`](scripts/lib/check_pr_refs.py)：请求 `GET .../pulls/<N>`，将接口返回的 **base/head 提交 SHA** 与本地 **`git rev-parse`** 在 `diff.base_ref` / `diff.head_ref` 上的结果比对；不一致则 **中止**（避免审错分支）。未设置 token 时跳过校验并打印说明。跳过校验：`--no-pr-check` 或 `CODE_REVIEW_SKIP_PR_CHECK=1`。单独自检：`./scripts/check-pr-refs.sh 470`。

4. 阅读 [`results/pr-449/review.md`](results/pr-449/review.md)（及可选的 `review.json`）。

更细步骤见 [`plans/pr-449-gemini-review.md`](plans/pr-449-gemini-review.md)。

### 把审查结论发到 GitCode PR 评论

使用 [GitCode Open API](https://docs.gitcode.com/en/docs/repos/pulls/)（`POST /api/v5/repos/:owner/:repo/pulls/:number/comments`），将 `review.md` 作为 **PR 下的一条评论** 发布（与网页「发表评论」等价，需 **个人访问令牌**，与 Gemini 登录无关）。

1. 在 GitCode **设置 → 访问令牌** 创建 token，勾选可访问对应仓库 / PR 的权限。
2. 导出环境变量（勿提交到 git）：

```bash
export GITCODE_TOKEN='你的令牌'
# 若官方变更了网关，可覆盖（默认如下）：
# export GITCODE_API_BASE_URL='https://api.gitcode.com'
```

3. 发布（默认读 `results/pr-<id>/review.md`，`meta.json` 里的 `pr_url` 用于解析 owner/repo/PR 号）：

```bash
./scripts/post-review-to-gitcode.sh 449
# 先看请求目标与体积，不真正 POST：
./scripts/post-review-to-gitcode.sh 449 --dry-run
# 不要自动加「AI 生成」横幅：
./scripts/post-review-to-gitcode.sh 449 --no-banner
```

若返回 `401/403/404`，核对 token 权限、本地 `workspace/inputs/pr-<id>/meta.json` 中 `pr_url` 与 `gitcode.api_base_url`（可选）是否与当前 GitCode 文档一致。

## 原理与机制（简要）

| 环节 | 做法 |
|------|------|
| **仓库** | `scripts/lib/pr_diff.py` 在 `workspace/pr-<id>/repo` clone 或 **仅 fetch** 更新已有 clone，按 `meta.json` 拉取 PR 头分支，再 `git diff base...head` 写入 `diff.patch`。 |
| **PR 校验** | 若设置 `GITCODE_TOKEN`，`check_pr_refs.py` 用 API 的 base/head **SHA** 对比本地 `diff.base_ref` / `diff.head_ref`，防止与网页 PR 不一致。 |
| **提示词** | `gemini -p` 的内容由三文件拼接：**业务上下文** [`assets/prompts/system-pr-449.md`](assets/prompts/system-pr-449.md) + **审查 Gem** [`assets/gems/yuanrong-pr-review/GEM.md`](assets/gems/yuanrong-pr-review/GEM.md) + **证据型输出** [`assets/prompts/review-evidence-rubric.md`](assets/prompts/review-evidence-rubric.md)。可与网页版 **Gemini Gems** 共用同一套 Gem 文稿。 |
| **模型输入** | **标准输入 = 仅 diff 文件**（`gemini` 的 `-p` 与 stdin 组合，与官方 headless 文档一致），避免超大 argv 与错误转义。 |
| **身份** | 脚本内 `unset GEMINI_API_KEY`，走 CLI 登录态，而非 API Key。 |

## 目录结构

```text
.
├── README.md                 # 本文件
├── plans/                    # 给人看的操作说明（如 PR449 流程）
├── scripts/
│   ├── review-pr.sh              # 生成 diff → 调用 gemini
│   ├── post-review-to-gitcode.sh # 将 review.md POST 到 GitCode PR 评论
│   └── lib/
│       ├── pr_diff.py              # clone/fetch、写 diff.patch
│       ├── bootstrap_meta.py       # 首次生成 workspace/inputs/pr-*/meta.json
│       ├── meta_links_prompt.py    # 从 meta 生成 Traceability 段并入提示词
│       ├── merge_meta_cli.py       # 命令行 --issues/--rfcs 写入 meta
│       ├── check_pr_refs.py        # GitCode API SHAs vs 本地 base_ref/head_ref
│       └── post_gitcode_comment.py
│   ├── check-pr-refs.sh            # 单独运行 PR ref 校验
├── docs/meta-json.md         # meta.json 字段说明
├── workspace/
│   ├── inputs/pr-<id>/       # 本地 meta.json（与 workspace 一并忽略）
│   └── pr-<id>/              # clone、diff.patch、run.log
├── assets/
│   ├── prompts/              # 业务提示 + 输出细则（CLI -p 片段）
│   ├── gems/                 # 与网页 Gems 对齐的 GEM 文稿
│   └── skills/               # Cursor Agent Skill（可选）
└── results/pr-<id>/          # 审查输出 review.md、stderr.log 等
```

## Git commit message template

Two-line English format: **line 1 = purpose (why)**; **line 2 = specific changes (what)**. See [`.gitmessage`](.gitmessage). Enable for this repo:

```bash
git config commit.template .gitmessage
```

根目录 [`cr.md`](cr.md) 为早期需求说明，可与 `assets/prompts` 对照；`temp_repo/`、`workspace/`（含 `workspace/inputs/`）已在 [`.gitignore`](.gitignore) 中忽略。
