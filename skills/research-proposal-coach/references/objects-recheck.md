# 对象、本人决定与局部复核

何时保存草稿和提出正式建议见主 Skill「决定何时读写」。本模块说明操作顺序。

## 保存与确认

1. 使用已知的最新项目和要求版本。普通观察与问法用工具 schema，特殊字段不明才查 `research.contract.object_types` 或 `content_schema`。新建对象用 `proposal_save_objects`，`expected_revision=0`；更新草稿用字段 patch，保留未列字段。
2. 需要正式候选时，用保存回执里的对象 ID 和修订填写 quality 的 `proposal`，附字段 patch、理由和需要启用或撤销的关联。同一对象已有待选建议时先检查是否有效，更新时明确替代旧建议。何时核对单项或整阶段，见主 Skill 第 4 节。
3. 学生作出网页决定后使用实际修订与关联。首次确认或改正文会生成新修订；为已有确认且无需复核的对象补来源关系可沿用正文修订。关系草稿要经学生确认才参与依赖。

整阶段从「当前任务」打开「核对阶段成果」，可逐项「保存修改」，最后点「确认并继续」。F 从「核对并提交老师审阅」查看固定稿和本稿答辩，最后点「提交老师」。只核对一项时，在侧栏进入「研究工作区」，到「依据与选择」找到该条建议。说明建议名称，请学生选「接受建议」「保留原方案」或「暂缓决定」。已有理由和依据继续沿用。

原话和答辩只能引用本项目实际学生消息，来源和材料引用已有记录，不编编号或快照正文。Question归属Topic用`belongs_to`（question → topic）；来源或证据影响Problem时，用`supports`、`challenges`、`limits`保存关系草稿，在理由中说明如何改变理解；取得关联ID后放入proposal的`relation_changes.activate_draft_ids`，等待本人决定。假设适用条件写入`hypothesis.scope`，不与RQ范围或方法限制混同。具体引用形状与关联方向以契约为准。

## 变更与复核

读取`research.needs_review`及对象、关系的`needs_review`标记，解释上游变化影响了哪些判断。学生在网页选择保留并说明理由，或提出修改后确认；模型不调用`proposal_recheck`代本人清除。按依赖顺序先处理上游，再核对下游。比较关系只核对比较本身，不扩散为所有成果重做。

更新已确认的 CheckRun 时，新建记录并用 `supersedes` 引用旧检查；旧检查仍是草稿时，可更新它或另存独立检查。scope_refs覆盖当前相连的RQ、hypothesis、method及版本；在content的字符串字段`rq_alignment`、`alternative_discrimination`、`conclusion_limits`分别保存RQ匹配、竞争解释判别力、结论边界的科学判断，不适用时说明类型理由。同时保留`reasoned_findings`、`reviewer_response`与未决项。程序结构检查不代替有证据的科学判断。旧修订、依据快照、提交和审阅意见保留。

## 冲突与接续

新操作使用新request_id；原请求重试保留编号。版本冲突先重读并说明差异，不盲重发。待同步不等于已保存。过期阶段会话按网站入口接续，不能通过换活动或复制其他绑定绕过。`proposal_focus`仅切换认知活动和聚焦对象。
