# 18个候选的有限历史暴露与任务就绪审计

Issue #520，身份`cpp-build-candidate-exposure-audit-v1`，运行release42decdbd。零新构建/Provider/凭据读取，不是方法效果或新样本资格。固定#492十二槽+#496六槽全部18个候选，没有替换。

## 审计观察

固定7da3b633与915a6d67两个完整Git树、benchmarks/docs/research范围，精确owner/name边界、不区分大小写，得到225条命中、79个Git文件，保存每条命中及完整文件快照。独立第二实现逐行复算一致。全部18项在该范围有来源记录；命中数不衡量暴露强度，文件路径含agent也不自动认定模型观察。

指定#502/#504冻结protocol/result中有6个候选、合计36个真实模型臂：uncrustify、libsndfile、libsodium、libverto、libhydrogen、buffer；失败臂也计入暴露。其余12项在**这两个队列**没有模型臂，不说明此前未运行；libtommath、libtomcrypt、check、tiny-AES-c已有其他历史开发线索，见原来源报告及本次Git命中。没有全历史、外部聊天或训练集审计，不宣称任何候选完全未见。

| 目前任务就绪登记 | 候选 | 后续动作 |
| --- | --- | --- |
| 已有11项参考资格 | uncrustify、libpng、libzip、libsndfile、libtommath、libtomcrypt、libsodium、libverto、check、libhydrogen、buffer | 可用于明确已见身份的后续前瞻比较，不能未经角色冻结就称holdout；libpng/libzip资格来自新#508，不回填#493 |
| 缺固定外部来源3项 | FastLZ、HDiffPatch、picohttpparser | 分别固定语料子模块、相邻依赖及测试合同、picotest gitlink后，再用新身份资格；不能关闭功能/测试凑样本 |
| 其余4项 | libffi、tiny-AES-c、libcrc、commander | 分别保留bootstrap后续未知、旧开发暴露且本轮未做新任务资格、metadata失败、完整功能oracle未定义 |

就绪登记取自已读取且hash冻结的#492/#496/#493/#500/#508报告，不是本阶段新构建观察。人工参考资格也不等于模型成功。可以先公开定义任务再前瞻评估模型，但需如实描述设计阶段暴露；来源审阅本身不是一律不能评估的理由，不能把“没在两个队列中看到模型”当独立保留集保证。

相同owner形成15个保守维护者关联标签：libtom两项、jedisct1两项、clibs两项分别关联。它们不是经核实的代码亲缘、fork或测试同源组；未来正式项目族划分还需共同代码/依赖审计，也不能将15个标签当独立样本数。

## 封存与验证

raw `/home/yiwei/.codex/outputs/forge-candidate-exposure-audit-v1/`，102普通文件、0链接、53091260 bytes；inventory `a5e0f8dcff639c91ba5fceb976130b241b0938c91c2a2f12d123f8b72e7e9b17`。协议`benchmarks/analyses/cpp-build-candidate-exposure-audit-v1.json`，预注册同名Markdown。六项边界/身份/脚本/失败臂测试、Ruff py310和format通过。

独立stdlib审计`/home/yiwei/.codex/outputs/forge-continuous-research-2026-10-19/candidate-exposure-v1-independent.json` valid=true、issues=[]：完整封存/9组件、79个Git文件、全部225命中第二实现、消费收据及指定队列模型臂核对一致。父protocol/result消费字节匹配各自inventory，父独立audit valid/无issues；没有重新计算每次Provider响应，也没有重新验证参考构建。最终结果head三项实际CI全SUCCESS才合并依赖分支，不进入main。

## 对下一阶段的决定

不把现有11项参考任务包装成未见项目池。下一次RQ1可以先在明确已见且前瞻冻结的任务上验证强接口完整路径与成本异质性；如果要宣称跨项目泛化，另做新项目来源/家族/任务资格及预先角色划分，所有未合格槽位留痕。RQ2依然先审计同源状态动作分歧，#516三例只作开发控制；本阶段没有给复杂选择器增加支持证据。

本轮Provider估算与未知预留不变，不新增付费臂。UTC22:45后仅清理交接，23:00绝对停止；后续运行须另有有效时窗和冻结协议，不因共享$20尚有余额跨过截止继续。
