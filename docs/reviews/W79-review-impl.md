# W79 review-impl —— 工作项的回合预算

**裁决:打回(changes --test-gap)。** 只有一处,但它让第一次撞上预算的那次提交能把篡改过的状态洗进 HEAD。我补了一条复现它的红用例。

## 问题

**`.agents/skills/pair-protocol/scripts/pair.py:3684`(`discuss_handoff`)—— 预算判在 `_discuss_tamper_guard`(`:3693`)之前。**

- `turn_budget_refusal` 第一次撞上时会 `load_state` 读**磁盘**上的状态、追加记录、`save_state`,再只提交状态文件。
- 讨论回合的 `handoff` 不经过 `cmd_handoff` 里那道"先于一切"的篡改检查(`phase == DISCUSS` 在它之前就分出去了)。所以这一支的篡改检查只有 `_discuss_tamper_guard` 一道,现在排在预算之后。
- 后果:agent 在讨论回合手改 `.pair/state.json`,只要改出来的状态正好撞上预算(比如把 `item_turns` 改大),那次单独提交就把改过的整份状态提交进 HEAD。
  - 改的可以是任何字段:`changes_count` 清零躲死锁闸、`discussed` 清空换回讨论额度……
  - 进了 HEAD 之后 `state_is_tampered` 比的就是它,篡改检查再也看不见。
- 其他三个入口顺序是对的:`cmd_handoff` 的篡改检查在转移表之前,`cmd_discuss`、`cmd_resume` 第一行就是 `_discuss_tamper_guard`。

**复现(已作为红用例提交)**:`tests/conformance/test_v1_item_turns.py:298`,`TestTamperedStateNotCommitted.test_讨论回合的_handoff`。

- 上限 2,tester 开讨论(计 1)。dev 把 `item_turns` 改成 9,再追加发言、`handoff`。
- 现在:提交数 3 → 4,HEAD 里的状态带着 `item_turns: 9` 和 `W1 x9`。
- 期望:被"你修改了状态"拒绝并还原,提交数与状态文件都不变。

同一个类里另三条(正常交接、`discuss` 开场、`resume`)现在是绿的,用来钉住另外三个入口的先后。

**修法(怎么改由你定)**:把 `discuss_handoff` 里那三行挪到 `_discuss_tamper_guard(root, "交接")` 之后。我在 `.pair/scratch/` 的副本里这样挪过:`test_v1_item_turns` 22 条与 `test_v1_discuss` 全绿(已删)。

## 查过、没问题的地方

- **判点**:
  - `cmd_handoff` 在 `rename_declarations` 之后、目标不是 `DONE` 时判,在抓改动与跑测试之前;
  - `discuss` 只在非 understand 的分支、额度判完之后判;
  - 讨论回合 `handoff` 与 `resume` 在回合归属之后判。
  - 没有工作项(understand)时 `turn_budget_refusal` 返回 None,`count_item_turn` 不计。
- **第一次撞上**:
  - 读磁盘状态而不是内存里改到一半的那份,写的是磁盘那份;
  - `_commit_state` 是窄提交(`-- STATE_REL`),工作区里本回合的改动留着;
  - 主题与契约逐字一致。
  - 去重用 `startswith(item + " x")`,`W1` 不会误中 `W10 x3`。
  - 记录里的 N 是已换手次数;人类中途调低上限时可能大于上限,可以接受。
- **计数**:
  - `count_item_turn` 在各入口 `save_state` 之前;
  - `DONE` 与认领清零;
  - 代办三件套与 `claim` 不经过它。
- **配置与状态**:
  - 默认 20;`0` 不限;
  - `verify-setup` 与 `discuss_limit` 同一口径(连 `bool` 也拒);
  - `DEFAULT_STATE` 两个键,老状态缺键当 0 与空。
- **`status`**:工作项进行中显示 `已换手 n 次 / 上限(max_item_turns)`,0 时显示"不限";撞过的记录单列一行。
- **拒绝文案**:说明不是惩罚、交给人类的三条路、完成不受限,与契约一致。
- `ENFORCEMENTS` 加了 `item-turn-budget`,不进交接不变量。
- 文档:protocol-spec、command-reference、architecture、troubleshooting、rules、SKILL 跟上,P1-2 标 ✅。
- 没有针对用例输入的特判。

## 变异点

等修好之后的 review-impl 一起登记(契约列的那一批,加"讨论回合的预算判在篡改检查之前")。
