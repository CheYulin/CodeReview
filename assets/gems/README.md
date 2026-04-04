# Gemini Gems（网页端）

本目录下的 **`yuanrong-pr-review/GEM.md`** 是可与 **Gemini 网页版 → Gems / 自定义指令** 对齐的完整指令稿：复制全文新建一个 Gem，即可在不跑 CLI 时做同类审查。

本地 **Gemini CLI** 由 [scripts/review-pr.sh](../../scripts/review-pr.sh) 自动拼接：

1. [assets/prompts/system-pr-449.md](../prompts/system-pr-449.md) — PR449 业务与技术焦点  
2. `gems/yuanrong-pr-review/GEM.md` — 四维审查 + 证据规则  
3. [assets/prompts/review-evidence-rubric.md](../prompts/review-evidence-rubric.md) — 输出结构与摘录格式  

修改审查策略时，请**三处同步**（或保持 GEM 与 rubric 为真源，`system-pr-449.md` 只写本 PR 差异点）。
