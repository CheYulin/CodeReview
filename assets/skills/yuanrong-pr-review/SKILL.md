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

仓库根目录：`./scripts/review-pr.sh 449`。详见 [plans/pr-449-gemini-review.md](../../../plans/pr-449-gemini-review.md)。
