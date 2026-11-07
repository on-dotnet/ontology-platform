# 当前工作流调用事实

- prepare：1次，exit2；后端locked restore 1次exit0，下载0；Web历史来源缺失。没有为了凑第二次prepare而重跑后端restore。
- plan：Base b3b68500d76ab5965fcc540afb883ca605cb15dd → P0文档候选798018375050b97d9f0c747b48feae887da91e52，exit2，affected仅policy；8个本任务JSON证据未映射。产品源码/测试/锁没有修改。
- verify：上述计划exit2/UNMAPPED_INPUTS；没有用直接运行M1替代。任务登记缺口留待P0恢复一起接入，不宣称完整工程验收。
- closeout --dry-run：exit0，只输出活跃任务缓存KEEP；删除0。不是资源删除验收；本轮未创建可回收的产品容器/卷/证书。
- test-review-evidence.ps1：exit0，Schema-only；未证明产品或CI。

正常产品迭代不产中间PARTIAL ZIP。本轮因明确授权边界停止，只交BLOCKED P0审查见证；以后恢复不能把此包当产品最终包。

package-check首次exit2：text-format拒绝0字节resolver-MSTest.Sdk.txt。该命令本来stdout/stderr为空，保留resolver-MSTest.Sdk.json中真实exit0与空字节SHA256，以及ignored原始0字节日志；不添加换行冒充原输出。移除冗余空文本后仅重验文档/打包预检。历史失败保留于此。

后续package-check曾以符号HEAD调用，被FULL_COMMIT_REQUIRED立即拒绝(exit2)，改为完整SHA后在5c99f6ff73e6644548226d7ff19bb3c34061c277通过(exit0)：格式、证据Schema、diff-check皆0，估算3758446字节。仅廉价交付预检，不是产品验收。非作者发现decision.md把NONE与draft nullable扩展捆绑过宽，已澄清保存后测试无需改DTO；原结论保留在独立Review记录。
