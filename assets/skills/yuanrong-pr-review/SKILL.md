---
name: yuanrong-pr-review
description: >-
  Evidence-based code review for openeuler/yuanrong-datasystem PRs: AR1 (#234),
  recovery (#233, #235), SFS aggregation, functionality, performance, bugs,
  style; every P0/P1 finding must quote the diff and suggest concrete fixes.
---

# yuanrong-datasystem PR 审查

与下列文件**同步维护**（同一套「Gem」规则）：

- [assets/prompts/system-pr-449.md](../../prompts/system-pr-449.md) — 业务与 AR 要点  
- [assets/gems/yuanrong-pr-review/GEM.md](../../gems/yuanrong-pr-review/GEM.md) — 四维审查 + 证据规则  
- [assets/prompts/review-evidence-rubric.md](../../prompts/review-evidence-rubric.md) — 输出结构与摘录格式  

## 审查维度

| 维度 | 说明 |
|------|------|
| 功能与需求 | 对照 **meta.json → `related`** 中的 Issue/RFC（及旧式 `issues`）；边界与错误路径 |
| 性能 | 热路径、锁、分配、IO、元数据频率；不足证据时写清要测什么 |
| 潜在缺陷 | 竞态、生命周期、错误码、资源泄漏等 |
| 风格 | 与 diff 内同文件/邻域模式一致 |

## 证据要求（硬性）

每条 **P0/P1** 及每条**具体**优化建议须包含：**路径**、**diff 逐字摘录**（代码块）、**一句话推论**、**可执行改法**。禁止空泛「建议重构」。

## PR / Issue / RFC 追溯

在 **`workspace/inputs/pr-<id>/meta.json`** 中维护 **`related.issues`**、**`related.rfcs`**（可选 **`closes`**）。CLI 会在提示词中注入 **Traceability** 段；审查结论应能映射到这些条目。

### 背景示例（无 meta 列表时）

| 标签 | Issue | 关注点 |
|------|-------|--------|
| AR1 | [#234](https://gitcode.com/openeuler/yuanrong-datasystem/issues/234) | 分布式磁盘、海量对象、二级缓存映射 |
| AR2 | [#233](https://gitcode.com/openeuler/yuanrong-datasystem/issues/233) | Worker 故障恢复后从二级缓存加载 |
| AR3 | [#235](https://gitcode.com/openeuler/yuanrong-datasystem/issues/235) | 恢复后元数据更新与一致性 |

## 技术焦点（AR1 / 分布式缓存）

缓存抽象、并发与 IO、索引与 GC、异常路径、元数据延迟、大对象/条带化（有 diff 证据时写）。

## SFS / 聚合（若相关）

死锁、缓冲区、元数据与数据块原子性、IOPS、异常处理。

## 自动化

### 审查生成

```bash
./scripts/review-pr.sh <pr-id> [--issues N,N...] [--rfcs 'URL|URL...']
```

### 评论发布

| 方式 | 脚本 | 说明 |
|------|------|------|
| 整体评论 | `./scripts/post-review-to-gitcode.sh <pr-id>` | 将完整 review.md 作为一条 PR 评论发布 |
| **行内评论** | `./scripts/post-review-inline.sh <pr-id> [--dry-run]` | 解析 Section E findings，尝试发布到对应代码行；无法定位时自动降级为一般评论 |

行内评论工作流：
1. 解析 `review.md` 中 Section E 的 `位置：path:line` 字段
2. 通过 `diff.patch` 映射到 GitCode PR 的绝对行号
3. 使用指纹去重，避免重复评论
4. 支持 `--dry-run` 预览，`--fallback-only` 跳过行内直接发布一般评论

详见 [plans/pr-449-gemini-review.md](../../../plans/pr-449-gemini-review.md)。
