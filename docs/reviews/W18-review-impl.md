# W18 review-impl(tester 审 dev 的实现)

裁决: **approve**。实现对上契约(含我在 spec 回合带声明补的"拒绝早于 `save_state`"与 PLAN ⑥′)。
六个锚点我在 review-impl 当场登记了(W16),`mutation_check --only` 全部被抓到。

## 一、逐段对契约

| 契约 | 实现 | |
|---|---|---|
| 范围 = 评审目录顶层 `.md`,与命名检查同一个 | `review_rewrite_violation` 第一道就是 `_review_top_level` | ✅ |
| 判据 = 相对 HEAD 有删除行(含删除、改名) | 复用 `has_rewrite`;改名由 W16 的 `--no-renames` 拆成删除 + 新增 | ✅ |
| 不分阶段、不分角色 | 挂在写权限边界的循环上,对每一条改动判 | ✅ |
| 放行:纯追加、新建、协议日志、`ignore_paths` | 三道 `return None` | ✅ |
| 文案给出本回合该写的文件名 + 不要撤销别人的东西 | `review_rewrite_hint`,没有评审文件时退回"要另写就新建一份" | ✅ |
| `verify-setup` 同样判,且**拒绝早于写状态** | 在 `state["setup_verified"] = True` **之前** | ✅ |

**你把两处措辞故意与 W16 的锚点岔开**(`blob_sha(...) is None`、`not has_rewrite(...)`)——
我在 spec 回合的参考实现正是栽在这里(锚点匹配到 2 处、`test_变异点仍能匹配到源码` 当场红),
你提前避开了。文档四处(`rules.md`、强制表第 6 行、排障新增一节、路线图 21)准确。

## 二、六个锚点:登记并实跑

只追加进 `mutation_check.py`(`numstat` 36 行新增、**0 行删除**),`test_变异点仍能匹配到源码` 通过,
`mutation_check --only` 基线全绿、六个全部被抓到。

**登记过程里三处要记下来:**

1. **`if not _review_top_level(cfg, path):` 在 `pair.py` 里有两处**(`check_review_names` 里一模一样),
   `if matches_any(path, cfg["ignore_paths"]) or path in PROTOCOL_LOGS:` 也有两处。两个锚点都加长到
   带后两行才唯一 —— 你给的建议锚点按原样登记会让锚点检查当场红。
2. **你建议的"顺序"变异形状是错的,我照做之后 `mutation_check` 报了"存活"。** 你写的是在
   `state["setup_verified"] = True` 之后插一次 `save_state` —— 但你的拒绝在那一行**之前**,
   `die` 早就退出了,那次插入在拒绝路径上根本执行不到,**拆了等于没拆**。
   改成在**检查之前**插 `state["setup_verified"] = True` + `save_state`(等价于"拒绝晚于写状态"),
   现在只被 `test_改写已提交的结论被拒_且拒绝早于写状态` 抓住。
   **这是 `mutation_check` 自己抓住了一条假的登记** —— 值得记:登记一条抓不到的变异点,
   比不登记更坏,它会让人以为那条防护有守护。
3. **"已在 HEAD 里"确认是等价变异**(与 PLAN ⑥′ 一致),不登记。

## 三、你挑出我一条恒绿的断言 —— 成立,我在下一个 spec 回合修

`test_评审回合改写已提交的评审记录被拒_文案给出该写的文件名` 里的
`assertIn("W1-review-impl.md", r.text)` **恒成立**:被改写的那份文件本身就叫这个名字,
拒绝清单必然把路径打出来。把 `review_rewrite_hint` 整句删掉,全套 0 红 —— 你实测过,我信。

**这是本轮第三次"判据比它声称守的性质宽",而且又是我写的。** 你给的候选形状对:
先在 review-impl 打回一次让 `changes_count` 变 1,此时该写的是 `W1-review-impl-2.md`,
再去改写 `W1-review-impl.md`,断言文案里出现 `-2` —— 那时删掉那句就会红。

**我现在改不了 `tests/`**(review-impl 只能追加 `MUTATIONS`)。**请在 review-test 带这个形状打回**,
我在 spec 回合补。顺便:那一次回弹正好是 W17 捷径的第一个真实用例 —— 补完测试若 GREEN
且没碰承重文件,下一阶段应当直接回 review-test,不再经过 impl 与 review-impl。

## 四、未覆盖(不构成打回)

- **`review_rewrite_hint` 在没有评审文件的回合退回"要另写就新建一份文件"**,这条分支没有用例;
  它只影响文案。上面那条用例修好之后可以顺带钉住,也可以不钉。
