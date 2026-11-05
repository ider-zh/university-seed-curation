# 初始化核验 · 2026-11-05

本次只做设计、离线脚本与私有 bootstrap 试跑，没有启动真实大学 Research、
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
