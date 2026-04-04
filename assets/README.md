# assets

- `prompts/` — **业务上下文**（如 `system-pr-449.md`）与 **证据型输出细则**（`review-evidence-rubric.md`）。CLI 下与下面 `gems/` 合并后作为 `gemini -p`；**diff 始终在 stdin**。
- `gems/` — 与 **Gemini 网页版 Gems** 对齐的指令稿（见 `gems/yuanrong-pr-review/GEM.md`），可与 CLI 共用一套规则。
- `skills/` — **Cursor** Agent Skills（`SKILL.md`）；与 `prompts/` + `gems/` 的审查标准保持同步。
