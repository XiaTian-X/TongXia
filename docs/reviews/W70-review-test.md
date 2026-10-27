# W70 review-test(dev)

裁决: changes

## 我检查了什么

- `tests/conformance/test_v1_contract_tiers.py` 8 条与契约「承重文件的修改分级」逐项对上:
  - 拒绝的情形:
    - PLAN 纯追加一行也拒:文案含"提案"与 `ratify`,没有新提交,停在 spec,工作区里的改动还在;
    - 改掉契约的一个已有行、删掉契约的一行,各被拒;
    - 不带声明改契约照旧被冻结判定拒绝,文案点名文件、含"冻结"与 `ratify`。
  - 对照:同一段 PLAN diff,带声明被拒;撤回后写进提案、双方各在本人回合签字、人类 ratify,改动生效。
  - 守着不该拦的:往契约**中间**插一段补充照旧放行;纯追加但没留决策照旧拒。
- 两条与本项矛盾的既有用例改写成本项的期望,没有删除:
  - `test_v1_frozen` 的带声明改 PLAN:原来期望放行,现在期望被拒;
  - `test_v1_rebound_shortcut` 的回合里改规划:同样改成期望被拒,契约那一条照旧守着"按改动判"。
  - 这两个旧名字只在历史评审里出现过,改名不影响符号引用检查。
- 我在 impl 回合把 4 个探针放在项目内 `.pair/scratch/`,4 个全部变红,和 review-impl 登记的四个变异点一致。
- 用到 `--contract-change` 的 11 个模块共 203 条,全绿。

## 未覆盖

- ADR-025 代价里写的绕过方式:不删旧条款、只追加一条与之矛盾的新条款。这只能靠对方在开工前审查时逐节点名发现,脚本不判语义。
- 路线图 `improvements.md` 按契约「不做」不纳入分级。

## 打回原因:完成时的全量检查挑出一个变异点存活

我第一次 approve 时,完成交接被拒,也没有提交。全量日志里有两件事:

**① 变异点「捷径不看本回合承重文件改动」存活。** `tests/conformance/mutation_check.py:668`,锚在 `.agents/skills/pair-protocol/scripts/pair.py:1282` 的 `if changed_named_frozen: return False`。
- 这道防护原本只为一种情形存在:回合里改了 PLAN。PLAN 不改变契约的 sha,"比对 `reviewed_contract`"那一条看不见它。
- 守它的唯一用例,是你按本项改写的 `test_这一回合改了规划_照旧进_impl`。
- W70 之后,回合里已经不可能改 PLAN。改契约只能纯追加,一定会改变 sha,`reviewed_contract` 比对已经拦住了;`tests/conformance/test_v1_rebound_shortcut.py:107` 那条就是这样红的,拆掉这道防护它照样红。
- 所以这个变异现在是**等价变异**,不是缺用例:正常流程里,"看"和"不看本回合承重文件改动"走不出差别。
- **请注销这个变异点**,在 `mutation_check.py` 里写明 W70 之后等价的理由,和第三十八轮那几次重锚同一个处理办法。实现那一行我先不动:它是无害的纵深防护,删它要进 impl,这一项为此多绕一圈不值。

**② 两条改了名的用例被 W61 判为不再跑的用例。** `test_v1_frozen` 与 `test_v1_rebound_shortcut` 各一条。这是有意的改名,不是回归。下一次完成时,我带 `--accept-new-failures` 声明放行。
