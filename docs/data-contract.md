# University 数据合同

当前领域 Schema 为 **v0.2.2**；历史 v0.1/v0.2.0/v0.2.1 保留以校验旧记录。
每条新业务数据通过 skill 脚本生成。分布式流程支持注册字段的追加观测，
保留旧观测、冲突与来源；尚不支持任意覆盖或撤销。

## 路径与文件

规范 QID 为 `Q` 加无前导零的正整数；桶为其 UTF-8 字符串的 SHA-256 前两个
十六进制字符。示例路径：`data/universities/df/Q10924764.json`。
共 256 个可能的桶；约五万所学校平均每桶约 195 个文件。桶由 QID 决定，
更新内容不会改变路径。统一 UTF-8、稳定缩进和排序、文件末尾换行。

一所学校只有一个当前 JSON。来源摘要与观测保存在同一记录；原始来源和运行日志
保存在各角色私有区域。未审核结构化提案可进入公开 Draft PR，签名审核意见在 PR
评论传递；main 仅保存已通过的数据与凭据。Git 保存已合并的数据历史。
QID 不得因去重或合并被物理改名；疑似重复以关系与状态表达。

## 必填控制字段与可选业务字段

必填：`schema_version`、`qid`、`record_revision`、`curation`、`seed`。
`update_datetime` 在从未成功完整刷新时省略；`modified_datetime` 表示其他实际修改。
两者由脚本维护，含义见设计文档，不能由 Agent 自行写为“今天”。
业务字段包括名称/机构类型、地点/校区、历史事件/关系、人员/学生、经费和基础展示。
按注册字段逐步添加，逐项允许缺失。公共字段与规范值使用英文；原始语言名称/
历史名称和证据保留。字段不是一个可以随便增加任意键的 `other_facts`。

缺失字段直接省略。业务值不接受 null、空白字符串或占位值。0、false、已知为空
的集合按实际语义保留；集合未知时省略。覆盖状态只有在尝试过后才记录：
`not_found`、`not_applicable`、`disputed` 等；没有覆盖条目代表尚未采集。
源声明的“未知值”“明确无值”用显式状态保留，不伪造 value。

每条事实包含：受控字段名、主体、精确/近似/范围值及单位、适用时期、原始表述、
短来源引用与事实状态。来源类型决定必需的元数据：Wikipedia 需要语言/page/revision，
在线 Wikidata 需要 item/revision/观察时间和 statement 定位，历史 dump 可附 snapshot；
没有 page ID 的来源不填一个假的 null。

来源、事实、模型执行凭据不要混在每个值旁重复输出。脚本维护记录内短 ID 与
批次级版本信息，Agent 使用紧凑任务包和 diff，避免大量低信息密度 hash。

## 初始字段模块

身份/名称、地点与校区、历史/机构关系、学生与人员、经费、基础展示。沿用已讨论的
业务原则：保留所有可识别时期；学生/教师/行政人员/总员工分开；人数与 FTE 分开；
预算、捐赠基金、收入、支出、资产、科研经费分开；保留原币种。不同主体或时期不能
互相覆盖。没有明确统计时期时不使用网页更新时间代替。主图只存 URL，不下载图片。

详细字段注册表与初始 JSON Schema 先随设计验收，身份任务先启用，其他字段任务
只有在相应字段合同存在时才允许领取。

## Schema 演进

Schema 与字段注册表由脚本检查和生成，使用版本标识。`record_revision` 是该
学校的内容修订，与 Schema 版本不同。

- 新字段先提交独立 schema PR，附语义、类型、来源/主体要求、示例和兼容分析。
- 可选字段新增不要求全量空字段回填；读者必须容忍缺失。
- 含义、单位、对象归属、字段重命名或必填变化需要显式迁移；不得仅改版本号。
- 大改需要人工批准。迁移脚本先 dry-run，报告影响文件与逐条失败，禁止静默丢值。
- Agent 普通数据任务不能修改 Schema。批处理 adapter 使用固定 Schema/字段版本。
- CI 验证单个改动及版本兼容；正式发布时验证全库与完整 manifest。

## 完整 JSON 示例

见 `examples/university.complete.synthetic.json`。文件由
`.agents/skills/university-curation/scripts/build_schema_example.py` 生成，并经结构、来源引用、对象和 preferred 校验。
**所有学校、人物、数值、QID、页面版本和 URL 均为虚构，不是研究结果。**

本稿采用领域分组，地点使用学校内稳定 ID，有独立 QID 时附加。这是本次示例的
设计选择，可在审阅时调整，不要求 Wikidata 已为每个校区建立独立条目。

## 结构

| 顶层组 | 内容 |
| --- | --- |
| identity | 多语言名称、机构类型、运营状态、办学性质、外部标识 |
| population | 学生各分组、教学/科研/学术/行政人员、员工总数 |
| finance | 捐赠基金、预算、收入、支出、资产、科研经费 |
| history.milestones | 可重复、分别标识的里程碑，事件类型/主体/日期/说明 |
| leadership | 分职务的现任和历史任职候选；原职衔、任期、人物姓名及可选 QID |
| locations | 校内地点 ID、可选 QID、地点类型、名称、地址、坐标、有效时间、地点统计 |
| related_entities / relationships | 前身、系统、校区等关联对象及有来源的关系 |
| profile | 官网、简介、校训、学位层次、教学语言、学科方向、图片 URL |
| sources | 本记录共享的短来源索引，版本/语言/URL 等只存一次 |
| coverage / curation | 已查缺口、核验范围及身份状态 |

## 通用 field set

每个字段保存 `candidates`；每个候选包含本字段内短 ID、值、来源证据及核验状态。
源明确未知/无值时用 value_state，省略 value。未搜集到的业务字段整体省略。

preferred 保存 candidate_id、reason_code，以及必要的说明/限定标记；不重复保存值。
普通单来源字段不反复写长理由，复杂选择才附解释。候选 ID 只在其字段内有效，
例如学生数 c1 与预算 c1 是不同候选，不是全库长 ID。

证据包含 source_ref、locator 和可选原始表述。sources 保存在线 Wikidata item/revision/
retrieved_at，或 Wikipedia language/page_id/revision_id/retrieved_at/URL。旧 dump 来源
仍可携带 snapshot_id。完整抓取指纹和原文快照留在私有控制面，不堆在每个业务值旁。

## preferred-v1 的规则

1. 缺少年份、只有一个来源、近似值或区间都可被选择；不会仅因完整性不足拒用。
2. 负责人首先比较明确现任、infobox 当前字段、任职至今、最后已知任职等语境。
   infobox 没写离任日期仍可使用，但记录 reported_current，不编造任期。
3. 定量数据在同口径/同币种内保留最新明确时期的候选参与选择；无时期候选也
   继续参与，不被自动排除。随后比较核验支持、来源角色及来源观察新近程度。
   官方原始资料/政府数据、学术原始资料、百科、知识库等优先级是可审阅的初始策略。
4. 只有一个可用值就选择它。Wikipedia 的无年份学生数/预算在示例中都成为 preferred，
   同时披露 period_not_stated；检索时间不写成统计年份。
5. 同年同口径冲突允许选择主展示值，其他候选和 unresolved 冲突继续保存，
   preferred 标记 conflicting_candidates，不能把“选用了”伪装成“冲突已解决”。
6. 人数/FTE、币种、对象和统计时期保留原样。不同口径可有首选展示值，但不合并、
   不换汇、不凭 preferred 名称宣称数据“最新”或所有指标天然可比。

这些是确定性的选择规则，不是置信度百分比。来源家族用于表达来源关联，不能
把 Wikipedia、Wikidata 和转载计作多份独立证明。选择代码不按来源数量投票。

## 对象、时间及历史

根字段默认主体为 institution。locations 下的统计属于该地点；里程碑声明自身的
主体，例如 related:predecessor。显式跨主体覆盖会被拒绝。城市中心坐标和校区坐标
分别存储，不因其中一个缺失而互填。

定量 period 区分日历年、学年、财政年度、日期和区间。未注明时期时省略 period，
标注 period_status=not_stated。经费示例给出 FY2024 的实际起止日期；金额使用十进制
字符串和原币种，避免浮点丢精度。数量分别支持精确、约数、区间、headcount/FTE。

七个里程碑分别保留前身职业学校、当前机构成立、高等教育资格、大学资格、特许、
迁址和更名。每个事件各自有日期候选和 preferred；不自动折成一个 founding_year，
也不把前身的年龄冒充当前法律实体的年龄。排名项目可选择不同日期口径。

## 维护与实施边界

```text
python .agents/skills/university-curation/scripts/maintain_schema.py generate
python .agents/skills/university-curation/scripts/build_schema_example.py
python .agents/skills/university-curation/scripts/curate.py validate examples/university.complete.synthetic.json
```

Schema/示例生成及 v0.2 校验已实现，示例不能通过 create 进入正式学校目录。
v0.1 的数据更新与任务逻辑保持兼容。v0.2 初始试跑导出已有独立签名与验收桥，
见 `docs/reviewed-pr-export.md`；当前分布式追加增量通过严格 Schema 与独立 Review
生成，不允许用 v0.1 claims 操作冒充领域更新，也不任意覆盖或撤销旧事实。

## v0.2.2：Wikidata 词条位置

`locations.kind = institution` 只表示根 Wikidata 词条关联的位置，`qid` 必须等于根 QID。
它不自动表示校区、总部、行政区中心、历史旧址或某段有效时期。直接 P625 与其他来源的
不同位置分别保留，不因坐标不同就丢弃。`source_precision_degrees` 保存原始角度精度，
不能解释为 `accuracy_metres`；`globe_qid = Q2` 才能使用本合同的 EPSG:4326。
`source_rank` 保留 Wikidata normal/preferred；preferred-rank unknown/no-value 不得被
normal-rank 值替代为 preferred。原始声明 ID 放在 evidence locator，源 revision 在 sources。
非地球、带限定符或已有词条级位置的情况转为专门 geography 任务，不静默跳过。

## 存储迁移

256 桶布局使用 SHA-256 前两位。`buckets.py` 对旧三位桶做全量、逐字节不变的移动，
历史 review/batch 凭据不改写；迁移清单保存旧路径、新路径、基线提交和内容摘要。
迁移 PR 不允许夹带事实更新。数据内容与修订号不因路径移动变化。
