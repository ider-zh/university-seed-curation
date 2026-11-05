# 完整大学 JSON 示例

打开 [university.complete.synthetic.json](university.complete.synthetic.json)。
全部内容均为虚构的 Schema 演示，包含的 QID、人物、数字、地址、URL、page/revision
ID 均不能用作真实事实。示例生成脚本与校验器禁止将此文件创建为正式学校记录。

建议依次检查：

| JSON 路径 | 展示的问题 |
| --- | --- |
| population.students_total | 只有 Wikipedia、无统计年份，约 25,000 人仍可 preferred |
| population.teaching_staff | 同年 980/1,020 冲突；选择年度报告，同时保留冲突 |
| population.employees_total | 2,300 人与 2,100 FTE 分开，未混成一个统计口径 |
| finance.budget | Wikipedia 未写时期的预算仍可使用 |
| finance.endowment | 保留 FY2023 与 FY2024，各有真实口径的财政期示意 |
| finance.research_funding | 保留金额范围、币种和时期 |
| history.milestones | 七个时间里程碑，前身与当前机构分开 |
| leadership.president | 无离任日期的 infobox 现任与历史任职均保留 |
| leadership.chancellor | 明确现任的另一职务，未与 President 混同 |
| locations | 无独立 QID 的校区、本校统计与城市中心坐标分开 |
| sources | 短引用 s1…s10 关联语言、URL、在线 revision 与观察时间 |

preferred 是候选引用及选择说明，不复制数值。无年份就省略 period，没有 null。
本文件是完整可验证的单校记录，不要求真实记录填满全部业务字段。
