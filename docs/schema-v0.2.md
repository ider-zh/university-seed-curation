# University Schema v0.2 · preferred 候选设计

状态：供检查的重大 Schema 草案；v0.1 保留兼容。没有迁移正式学校记录。

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
见 `docs/reviewed-pr-export.md`；通用增量 diff 尚未实现，仍明确拒绝用 v0.1 claims
操作冒充领域更新，不隐式迁移旧数据或覆盖现有学校。
