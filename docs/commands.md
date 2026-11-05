# 已实现的离线脚本接口

Python 3.11+，安装 `jsonschema`。Parquet seed 输入额外安装 `pyarrow`。
脚本在仓库根目录运行，无需先做 editable install。测试不访问网络。

```text
python scripts/maintain_schema.py check
python -m unittest discover -s tests -v
python scripts/curate.py --help
```

## 初始化与浏览

```text
python scripts/curate.py seed-init --input /private/seed/institution_candidates.parquet --manifest /private/seed/delivery_manifest.json
python scripts/curate.py seed-init --input /private/seed/institution_candidates.parquet --manifest /private/seed/delivery_manifest.json --write --limit 10
python scripts/curate.py --state /private/shared/queue.sqlite3 snapshot --workspace .private/bootstrap --base-ref INPUT_GIT_OR_IMPORT_REF
python scripts/curate.py --state /private/shared/queue.sqlite3 tasks --run RUN_ID --limit 10
```

`seed-init` 默认仅预检；`--write` 默认写入 `.private/bootstrap`，不会自动放入公开
Git 路径。写入公开位置需要 `--acceptance` 绑定输入 manifest 的人工验收记录。
`--limit` 是脚本 smoke test，不是分层质量抽样。初始 JSON 缺省没有 update_datetime。

分页返回 `next_cursor`（还有下一页时才出现）。下次使用同一 run 和 cursor，
游标不跨快照使用。`tasks` 只浏览；分配必须用 `claim`，不能自己挑一个已显示的 QID。

## 私有 Research / Review

```text
python scripts/curate.py --state /private/shared/queue.sqlite3 claim --run RUN --role research --actor RESEARCH_WORKER --session SESSION
python scripts/curate.py propose QID --workspace WORKTREE --changes .private/changes.json --output .private/proposals/ATTEMPT.json
python scripts/curate.py --state /private/shared/queue.sqlite3 submit --task TASK --lease TOKEN --proposal .private/proposals/ATTEMPT.json
python scripts/curate.py --state /private/shared/queue.sqlite3 claim --run RUN --role review --actor REVIEW_WORKER --session NEW_SESSION
python scripts/curate.py --state /private/shared/queue.sqlite3 packet --task TASK
python scripts/curate.py --state /private/shared/queue.sqlite3 review --task TASK --lease TOKEN --session NEW_SESSION --verdict .private/verdict.json
python scripts/curate.py --state /private/shared/queue.sqlite3 apply --task TASK --workspace WORKTREE --kind university_refresh
```

全局 `--state` 和测试用 `--now` 选项放在子命令之前。所有工作区使用同一绝对
state 路径。租约有效期默认 30 分钟，长任务定期执行 `heartbeat`；不要把租约 token
放进 Git、PR 或公开日志。

`changes.json` 支持 identity_status、new_sources、new_claims、withdraw_claim_ids、
coverage。new_claims 不带 ID；脚本分配。不能覆盖旧来源、删掉整个记录或篡改修订号。
withdrawn 事实仍保留，不是物理删除。脚本保存私有候选，Review 校验每个 changed_claim_id。

verdict 至少包含 decision、source_checks（每个变更事实一个支持结论）、
reviewed_groups。完整刷新必须审核整个 core-v1 profile；部分补充用 field_update，
确定性外部源用 batch_import，均不得重置 update_datetime。

## 当前未启用的边界

离线数据更新 receipt 校验只验证声明的 actor/session 与内容绑定。生产环境仍需
执行桥绑定真实 Agent 会话、可信审核器签名和访问隔离；不应把这些离线检查当作
对恶意本地操作者的认证。真实 Provider、源 adapter 与 GitHub exporter 都未配置。

`pr-build` 当前必定拒绝，避免未经可信核验便输出到公开 PR。上线时必须在独立
集成阶段加入真实 review attestation、main 基线检查、受保护分支和实际 PR 合并回执。
已经本地 applied 的学校会保持任务锁，直至该集成确认合并或取消，防止另一个 run
重复处理同一学校。初始版本不自动标记“已合并”。
