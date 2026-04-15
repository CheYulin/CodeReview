### Executive Summary
PR 583 主要针对 **Issue #366**，旨在显著提升 URMA 及 RPC 层的可观测性与分布式诊断效率。核心变更包括：
1. **细化错误状态码**：引入 `K_URMA_WAIT_TIMEOUT` 区分 URMA 专用等待超时与通用 RPC 超时。
2. **标准化诊断标签**：在关键路径引入 `[URMA_WAIT_TIMEOUT]`、`[TCP_CONNECT_RESET]` 等方括号前缀，极大方便了通过日志聚合工具进行故障定位。
3. **增强上下文信息**：在 URMA 事件与重连日志中增加了远程地址、InstanceId 及操作类型（READ/WRITE）。
4. **鲁棒性加固**：在 Worker 层将新错误码纳入自动重试机制，并增加了多处空指针防御性检查。
整体代码质量高，测试用例补充完备，建议在确认 P1 级兼容性影响后合入。

---

### A. 功能与需求符合性
- **符合性**：完全符合 **Issue #366** 对增强错误信息的需求。通过在底层 `Status` 对象中嵌入结构化标签（Tag），解决了以往 URMA 异步错误难以匹配具体请求与节点的痛点。
- **覆盖度**：变更涵盖了从底层的 `UnixSockFd` 到中间层 `UrmaManager` 再到上层 `WorkerOcService` 的完整调用链。
- **追溯性**：新测试用例 `TestUrmaRemoteGetWaitTimeoutReturnsUrmaWaitTimeout` 验证了错误码在跨进程传递中的正确性，闭环了 Issue 要求的增强。

### B. 性能与可扩展性
- **热路径优化**：在 `PollJfcWait` 和 `HandleUrmaEvent` 等高频调用点使用了 `LOG_EVERY_N(..., 100)`，有效防止了在网络抖动期间因大量 IO 日志导致的磁盘 IOPS 尖峰。
- **内存分配**：`UrmaEvent` 增加了 `std::string` 存储远程信息。由于 `UrmaEvent` 仅在请求 In-flight 期间存在，且地址信息长度有限，对系统内存压力微乎其微。

### C. 潜在缺陷（Bug / 竞态 / 资源）

#### P1 级：错误码替换对调用方的语义冲击
- **位置**：`src/datasystem/common/rdma/rdma_util.h:70, 97`
- **摘录**：
```cpp
-            RETURN_STATUS_LOG_ERROR(K_RPC_DEADLINE_EXCEEDED, FormatString("Timed out waiting for any event"));
+            RETURN_STATUS_LOG_ERROR(K_URMA_WAIT_TIMEOUT,
+                                    FormatString("[URMA_WAIT_TIMEOUT] Timed out waiting for any event"));
```
- **问题**：将通用的 `K_RPC_DEADLINE_EXCEEDED` 替换为 `K_URMA_WAIT_TIMEOUT` 属于破坏性变更。如果有未在本 PR 中修改的逻辑（如外部 Client 或其它 Service 层）严格通过 `if (rc.GetCode() == K_RPC_DEADLINE_EXCEEDED)` 做特殊处理（如容灾切换），会导致该逻辑失效。
- **建议**：建议全仓 grep `K_RPC_DEADLINE_EXCEEDED`，确认是否有依赖该特定错误码进行流程控制的场景，或在 `IsRetryable` 等辅助函数中显式兼容这两者。

#### P2 级：空指针检查后的错误上下文
- **位置**：`src/datasystem/common/rdma/urma_manager.cpp:692`
- **摘录**：
```cpp
+        CHECK_FAIL_RETURN_STATUS_PRINT_ERROR(connection != nullptr, K_RUNTIME_ERROR, "Urma connection is null");
```
- **问题**：此处 `K_RUNTIME_ERROR` 属于 fallback 方案，但鉴于 PR 核心目标是增强诊断，此处若触发说明系统内部状态机失效。
- **建议**：建议增加更多上下文（如 `requestId`），并考虑是否应归类为 `K_URMA_ERROR` 以保持层级一致性。

### D. 代码风格与主仓一致性
- **日志规范**：新引入的 `[TAG]` 风格与分布式系统常见的诊断规范高度一致。
- **防御性编程**：在 `UrmaManager::CreateEvent` 中增加了对 `connection` 的 explicit check，提升了代码的安全性。

### E. 具体优化与重构（可执行清单）

[E-1] [P1] 维度：功能/鲁棒性
- 位置：`src/datasystem/worker/object_cache/service/worker_oc_service_get_impl.cpp:1114`
- 摘录：
```cpp
-              StatusCode::K_RPC_UNAVAILABLE }, minRetryOnceRpcMs);
+              StatusCode::K_RPC_UNAVAILABLE, StatusCode::K_URMA_WAIT_TIMEOUT }, minRetryOnceRpcMs);
```
- 问题：在重试列表中增加了 `K_URMA_WAIT_TIMEOUT`。需注意如果超时是由底层硬件资源耗尽引起的，盲目重试可能导致请求堆积。
- 建议：目前合入是安全的，但建议后续在重试器中引入指数退避（Exponential Backoff）。

[E-2] [P3] 维度：风格/格式
- 位置：`src/datasystem/common/rdma/urma_manager.cpp:707`
- 摘录：
```cpp
+        RETURN_STATUS_LOG_ERROR(K_URMA_WAIT_TIMEOUT,
+                                FormatString("[URMA_WAIT_TIMEOUT] timedout waiting for request: %d", requestId));
```
- 问题：`requestId` 在 `UrmaEvent` 中是 `uint64_t`，使用 `%d` 打印可能会在某些平台下导致截断或格式化警告。
- 建议：改为 `FormatString("... request: %lu", requestId)` 或使用宏 `PRIu64`。

### F. 合入结论
**通过**。
PR 质量优良，虽然存在 P1 级的语义变更风险，但鉴于作者已在 Worker 重试逻辑中做了适配，该风险在受控范围内。建议合入后观察监控中错误码分布的变化。
