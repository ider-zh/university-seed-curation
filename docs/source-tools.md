# Skill 的在线来源工具

本项目的 Agent 可在其他环境运行。Wikidata 和 Wikipedia 均通过在线 API 查询，
不需要 SSH、DuckDB、本地 dump 或 229。上游 wikidata-research 的 dump 约定不变。

实现只用 Python 标准库；默认把原始响应写入当前环境 `.private/cache/sources`。
同请求缓存 30 天，过期重取。每次抓取还保存独立不可变 capture，刷新“当前缓存”
不会覆盖以前引用的响应。原始 references/qualifiers、HTML/wikitext 保存在私有 capture；
给 Agent 的默认视图是精选属性、infobox 行或分章节正文。

## Wikidata

```text
python .agents/skills/university-curation/scripts/sources.py wikidata-get Q10924764 --properties P31 P17 P131 P571 P856 --resolve P17 P131 --linked-limit 8
python .agents/skills/university-curation/scripts/sources.py wikidata-search "Sichuan Agricultural University" --language en --limit 5
```

get 返回 requested_qid、实际返回 QID、revision、来源 URL、名称、sitelinks 和所选
声明。必要关联项最多一跳，默认最多 12 个；不递归展开整个图。发现重定向时保留
原请求和目标 QID，不自动合并学校身份。声明显示原 statement ID、rank、snaktype、
value、qualifiers 和原始引用数量；完整 references 可从私有 capture 读取。

search 是在线实体搜索，不是已经审核的高校召回或远程 SPARQL 扫描。
搜索结果不能自动成为机构身份结论。当前不提供全站无限抓取命令。

## Wikipedia

```text
python .agents/skills/university-curation/scripts/sources.py wikipedia-get --language en --qid Q10924764
python .agents/skills/university-curation/scripts/sources.py wikipedia-get --language zh --title "四川农业大学" --view infobox
python .agents/skills/university-curation/scripts/sources.py wikipedia-get --language en --qid Q10924764 --view text --section History --max-chars 12000
python .agents/skills/university-curation/scripts/sources.py wikipedia-get --language en --oldid REVISION_ID --view text --offset 12000
```

默认 summary 给出页面版本、章节索引、infobox 和图片 URL；text 支持章节及字符
窗口，未返回完时给 next_offset。选择语言由 Research Agent 决定，不要求有英语页。
--qid 自动从在线 Wikidata sitelink 得到该语言标题；缺页时明确报告，可换语言。
正文、wikitext、infobox 的原始输入和 revision 来自同一个 parse 响应。

infobox 提取只是“原标签＋文本行”，没有把 President、学生数等转换为已审核业务
事实。Research/Review 仍要完成语义、主体、时期和 preferred 选择。图片只返回 URL。
oldid 固定文章 revision，但模板渲染可能变化；实际观察的响应因此另存私有 capture。

## 运行与错误

- 请求带项目 User-Agent、超时与有限重试，429/503 遵守等待提示。
- 默认 maxlag=5；服务端复制延迟较大时可能返回 maxlag 错误。调用者可显式配置
  `python .agents/skills/university-curation/scripts/sources.py --maxlag 30 ...`。该值是 API 复制延迟容忍值，不是统计年份，
  也不取消 HTTP 限流。无成功响应不会伪造成空数据。
- JSON 标准输出统一 UTF-8，适用于 Windows、Linux 等环境。
- --refresh 主动重取；缓存与原文不能放到公开 PR。
- 已在实际在线 QID、Wikipedia 页面、实体搜索与章节读取上验证，另有离线缓存/
  revision/有界关联项回归测试；并不表示完整 Agent 编排已上线。

协议参考：[Wikidata wbgetentities](https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities)、
[MediaWiki parse](https://www.mediawiki.org/wiki/API:Parsing_wikitext)。

## Host-local cache across Research subagents

Research subagents on one host may use `UNIVERSITY_SOURCE_CACHE` or global
`--cache ABSOLUTE_PATH` for that host's private cache. Independent Review uses
its own host and cache; no cross-role cache sharing is required. Same-key
requests on one host are serialized with an OS file lock and
recheck the 30-day cache after acquiring the lock; different keys remain parallel.
A failed process releases its OS lock automatically. This is a local-filesystem
sharing design, not a distributed lock for an arbitrary network filesystem.

Money-unit QIDs may be looked up on demand: `wikidata-get Q4917 --properties P498`.
Retain the resolved entity's revision and ISO-code claim when present; do not guess
an ISO currency from the institution country. Review's revision-bound retrieval
is tracked separately from Research's shared latest-entity lookup.
