# W69 — review-impl(tester)

结论:**通过**。

## 查过的地方

- `cfg.setdefault("discuss_limit", 1)`;`cmd_discuss` 里 `used` = 本工作项在 `discussed` 里出现的次数,照 spec 回合定下的字面写了 `if used >= cfg["discuss_limit"]:` ——
  第三十八轮重锚的 `讨论_每项一次不查` 与本项两个额度变异点都锚在它上面,`test_变异点仍能匹配到源码` 由红转绿。
  拒绝文案:已进次数、`discuss_limit` 的值、写提案交人类或由人类在配置里调高 —— 含"人类""提案""discuss_limit";撞额度只 `die`,不改状态、不停轮转。
- `discussed` 仍在 `resume` 时追加一次(W67 的写法本来就可重复),含义从"进过"变成"次数",老状态每项最多 1 次,不变。
- `verify-setup`:排除 `bool`、非 `int`、负数。`status`:配了提案目录且有工作项时一行剩余额度(不小于 0)。
- `report`:`讨论` 只认主题 `discuss:` 且正文(去掉开头换行)以 `discuss=open ` 开头;`人类批准的提案` 认批准主题;判定只在认领 ≥ `MIN_SAMPLE` 时给,
  0 → 从未讨论、过半 → 偏高、恰好一半 → `—`;三行都走同一个 `rows`,`--since` 自然跟着起点。
- `ENFORCEMENTS` 的 `discuss-once` 改名 `discuss-quota`;文档(spec 配置表与 §5.6、§8,命令参考,architecture,rules,INSTALL,路线图 D4 ✅ 与 P0-5 已落地)跟上。

## 变异点

`--only`:本项登记的五个(额度写死为 1、用 `>` 判、讨论回合也算进讨论、判定不看样本量、偏高不生效)全部被抓到;重锚过的 `讨论_每项一次不查` 照样被抓到。基线全绿。

## 没覆盖的

- `status` 在 `discuss_limit` 非法(比如字符串)时做减法会抛异常 —— `verify-setup` 先判失败,配置非法时协议本来就不该跑;不阻断。
