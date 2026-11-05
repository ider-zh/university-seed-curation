# 初始化核验 · 2026-11-05

首次初始化只做设计、离线脚本与私有 bootstrap 试跑，没有启动真实大学 Research、
Wikipedia/外部网站采集或公开数据 PR。

- 对真实 `institution_candidates.parquet` 校验 delivery manifest 后 dry-run：39,489 条。
- 私有目录创建 10 条候选 JSON：每校一个文件，QID SHA-256 三位桶，身份为 pending。
- 所有初始记录均省略 update_datetime，未把 dump revision 当研究刷新时间。
- 9 个离线测试通过：缺失值/0/显式未知、主体归属、路径与初始化幂等、部分/整校
  时间区分、内容基线保护、固定游标、并发上限与超时拒收、独立核验与修订次数、
  CLI 候选→核验→应用及幂等重试。
- 失败修订尝试追加保存在私有队列，不在后续修订时覆盖。
- GitHub CI 只运行只读离线测试（Python 3.11/3.13）；它不替代真实来源核验、
  reviewer 认证、PR 凭据签名和 main 分支保护。

真实源 adapter、主 Agent/subagent 执行桥、单 Review 执行器、可信审核凭据、
小批 PR 组装与自动合并尚待 rollout 配置及验证。`pr-build` 当前拒绝执行。
Schema 是初始化草案；详细字段仍可通过独立 schema PR 评审和演进。

## v0.2 草案及在线来源工具补充

- 按用户确认改为在线 Wikidata/Wikipedia，可在其他环境使用，不依赖 dump 主机。
- 实测 Q10924764 的在线实体、必要关联项、实体搜索、英语页面、History 章节与缓存
  命中成功。原始响应仅在私有缓存；服务 maxlag 时明确返回错误，可显式调整容忍值。
- Wikipedia page/revision：1379510860；Wikidata revision：2564385783。
  这些是工具验证时实际观察的版本，不是完整大学研究/核验结果。
- v0.2 完整 JSON 示例全部虚构，包含多时期/无时期数量、经费、冲突、七里程碑、
  负责人、校区/城市与 sources。例子与真实源工具测试分离，不能误当作抓取结果。
- 17 项离线测试通过，覆盖 preferred 单来源/无年份可用、冲突保留、当前任职语境、
  引用/主体校验、私有缓存原始版本留档及既有任务/更新流程。
- v0.1 保持兼容；v0.2 领域变更桥、真实 Agent 编排、签名/PR exporter 尚待实施。
