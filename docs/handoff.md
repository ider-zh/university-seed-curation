# 当前状态与交接

当前 main 已合并 PR #1–#4，包含 Schema/skill、可信导出代码、三所真实学校数据与
skill 入口整理。公开数据是 Q13371、Q1075625、Q519556；十校私有试跑保留不变。
主候选池尚未全量导入，当前三校不等于 39,489 条已公开。

本次代码变更：256 桶、skill 内部库迁移、受限 root P625 增量适配器。Q519556
坐标遗漏源于 Research 未提交 P625，旧 Review 缺少原始声明覆盖检查。新增任务使用
现有 Wikidata revision 重新取证并进行独立 Terra medium Review，失败/旧尝试均保留。

交付顺序是代码 PR、纯路径迁移数据 PR、Q519556 坐标数据 PR。后两项不混合，
每项绑定准确 Git base；若学校数据基线变化则重新准备/核验，不能覆盖用户修改。
路径迁移保持记录字节不变；坐标更新不重置整校 update_datetime，也不改写原审核凭据。

当前可用：离线队列/租约、在线来源缓存、十校私有试跑、已验收初始导出、可信 Git-blob
校验，以及本分支的坐标补充/路径迁移。尚未提供：任意 v0.2 字段更新、生产分布式调度、
provider 签名模型身份、独立 GitHub reviewer 账户、required checks/分支保护与自动合并。
正式数据集发布仍需单独人工验收。

阅读顺序：README → AGENTS → 自己的 skill 角色；字段查 data-contract，执行查
commands/source-tools，审核与发布查 review-policy-v2/reviewed-pr-export。旧阶段
报告与设计由 Git 历史保留（整理前提交 8535ab0），不要当成当前操作说明。
