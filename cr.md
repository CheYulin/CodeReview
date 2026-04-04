针对你在 yuanrong-datasystem 项目中负责的 "二级缓存支持海量对象存储" 这一特性，我们需要将业务上下文（RFC 需求）与技术实现（代码差异）深度结合。

以下是为你生成的完整配置与操作指南。

第一步：优化 Gemini Code Review 提示词 (Prompt)
针对这个特定的 PR（Issue #234），我们需要让 Gemini 关注“分布式磁盘”和“海量对象存储”的特性。

建议使用的 System Prompt：

Plaintext
# Role: 高级分布式存储架构师 (Expert in Distrubuted Storage & SFS)
# Context: 正在审查 yuanrong-datasystem 项目中关于“二级缓存新增分布式磁盘类型”的实现。该特性旨在通过分布式磁盘支持海量对象存储，是实现 Worker 故障恢复的基础。

# Technical Focus (审查重点):
1. 接口抽象：检查分布式磁盘缓存层（Disk Cache Layer）的抽象是否通用，是否能兼容不同的对象存储后端。
2. 并发控制：针对分布式磁盘的读写，检查是否存在竞态条件，特别是多线程下的 IO 调度。
3. 空间管理：检查海量对象存储场景下的索引管理（Indexing）和空间回收（GC）逻辑，防止内存溢出。
4. 错误处理：由于涉及分布式磁盘，重点关注网络抖动、磁盘满、IO 超时等异常路径的处理是否完备。
5. 性能影响：评估元数据更新的开销，是否符合分布式缓存的低延迟要求。

# Review Format:




第二步：跨分支/跨仓库审查的操作流程
由于你需要对比 yaohaolin 的开发分支与 openeuler 的主干分支，最专业的方法是利用本地 Git 环境作为媒介，将 diff 喂给 Gemini CLI。

1. 配置远程仓库环境
在你的本地项目目录下执行，确保能拉取到两个仓库的代码：

Bash
# 添加上游仓库
git remote add upstream https://gitcode.com/openeuler/yuanrong-datasystem.git
# 添加你的/开发者的仓库
git remote add origin https://gitcode.com/yaohaolin/yuanrong-datasystem.git

# 获取最新代码
git fetch --all
2. 生成差异并调用 Gemini CLI
你可以编写一个简单的自动化脚本（例如 gemini_cr.sh），方便以后在 AtomGit 上协作：

Bash
#!/bin/bash

# 定义对比的分支
TARGET_BRANCH="upstream/master"
SOURCE_BRANCH="origin/master"  # 或者是具体的 feature 分支

# 1. 获取代码差异 (只对比文件改动，排除文档等非代码文件)
DIFF_DATA=$(git diff $TARGET_BRANCH..$SOURCE_BRANCH -- ':(exclude)*.md' ':(exclude)docs/*')

# 2. 读取我们刚才优化好的提示词
SYSTEM_PROMPT=$(cat <<EOF
# [此处粘贴上面第一步生成的 Prompt 内容]
EOF
)

# 3. 调用 Gemini CLI 进行审查 (以 google-generativeai 为例)
echo "正在分析 $SOURCE_BRANCH 相对于 $TARGET_BRANCH 的变更..."
echo -e "$SYSTEM_PROMPT\n\n---CODE DIFF STARTS---\n$DIFF_DATA" | gemini-chat > review_result.md

echo "审查完成，结果已保存至 review_result.md"
第三步：在 AtomGit/GitCode 上的协作建议
为了实现真正的“在线协作”，你可以按照以下步骤闭环：

本地运行分析：在提交 PR 前，运行上面的脚本，根据 review_result.md 自行修正一遍明显的逻辑问题。

提交评论：将 Gemini 生成的高质量建议，挑选核心部分以评论（Comment）的形式贴在 AtomGit 的 PR 页面中。

引用 Issue：在 PR 描述中明确注明 Closes #234，并附带 Gemini 关注的重点（如：“已通过 AI 审查重点验证了分布式磁盘的元数据一致性逻辑”），这会极大提升 Maintainer 的合入信心。

针对 Issue #234 的特别提醒：
在审查该 PR 时，请务必让 Gemini 检查 “二级缓存”与“分布式磁盘”之间的映射逻辑。

追问 Gemini：“请检查当前实现是否支持对象的条带化（Striping）存储？如果没有，在大对象场景下是否存在单盘瓶颈？”

通过这种“Prompt 引导 + 脚本自动化 + 业务追踪”的方式，你可以把 Gemini CLI 变成一个懂 yuanrong-datasystem 业务的虚拟技术顾问。
