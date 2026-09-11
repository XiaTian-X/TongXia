# W13 review-impl(tester 审 dev 的实现)

裁决: **approve**。实现逐段对上契约;你列的 8 个 `claim` 侧变异我在隔离副本里逐个重跑、
**全部复现**;`mutation_check` 全量 **101/101** 被抓到,我登记的 4 个沉淀侧新点都在其中。

---

## 一、逐段对契约

| 契约那一句 | 实现 | 对上了吗 |
|---|---|---|
| 现场算,`setup_verified` 那个键不被改写 | `stale_verification` 只读 state、返回理由;`claim` 里 `die` | ✅ 拒绝路径不写状态,`test_契约改过之后不能认领` 钉着 HEAD 与状态文件都不动 |
| 只作用于 `claim`,`status` 可以提示,`whose-turn` 不动 | `claim` 另起一段;`status` 在 `elif` 分支里只 `print`;`whose-turn` 没动 | ✅ |
| sha 取工作区内容,两端同口径 | `worktree_sha` = `git hash-object -- <path>`,`verify-setup` 与 `claim` 都用它 | ✅ 两种口径错配各被一条用例抓住(下表) |
| 按角色各存一份 | `setup_verified_contract = {角色: sha}`,`claim` 取 `.get(me)` | ✅ |
| 键缺失算作废 | `seen is None` → 拒绝,文案单独一种 | ✅ |
| 契约读不到同样拒绝 | `is_file()` 为假 → `None` → 拒绝 | ✅ |
| 「已沉淀」两处改判据、另两处不改 | `settled` 照我定死的字面,紧接 `mine`;打回与当场两行一字未动 | ✅ |

**另外核过的:**

- **`verify-setup` 先复制再写。** 你注意到 `load_state` 是 `dict(DEFAULT_STATE)` 的浅拷贝,
  直接往默认的 `{}` 里写会改掉 `DEFAULT_STATE` 本身 —— 这个坑我没想到,你绕开了。
- **只在全部检查通过之后才记录。** 记录那几行在所有 `die` 之后、`save_state` 之前,
  没通过的校验不会留下一份"校验过这一份契约"的记录。
- **`status` 的提示里不会漏出 `None`。** `cmd_status` 用的是 `resolve_role`,
  解析不出角色直接停,走不到 `stale_verification(…, None)`。
- **两个 sha 一眼分得开。** `contract_sha` / `setup_verified_contract`,`DEFAULT_STATE`
  里两段注释并排写清按工作项 vs 按角色、HEAD vs 工作区;协议规格的状态表也有这一行。
- **文档四处**(协议规格的 `claim` 前置条件与状态表、架构图、排障、路线图条目 17)准确;
  协议规格里"缺少新键时检查自动跳过"对新键是错的,你补了例外,这一处要是漏了就是
  一条会误导人的规范。

## 二、你列的 8 个变异:逐格复现

隔离副本里改 `pair.py`、跑 `test_v1_validity` + `test_v1_setup`,每个锚点都恰好匹配 1 处:

| 变异 | 红的 |
|---|---|
| `die("拒绝认领 —— " + stale)` → `pass` | claim 那六条 |
| 比对端 `worktree_sha` → `blob_sha` | **只有**人类没提交那条 |
| 记录端 `worktree_sha` → `blob_sha` | 人类没提交 + 提交之后同一份内容 |
| `seen` 取任一角色的值(全局单值) | **只有**只有 dev 校验过那条 |
| `if seen == now:` → `if seen is None or seen == now:` | 只有 dev 校验过 + 键缺失 |
| 读不到时 `return None` | **只有**契约读不到那条 |
| 门禁判断 → `if True:` | 门禁没开那条、沉淀两组全部、`test_可以配置关闭门禁` |
| 记录那行 → `pass` | 八条(重跑恢复、中途不挡交接、`test_交了结论后通过并允许认领` 等) |

和你笔记里的表一致。**"两端同口径分两半"那条的设计成立**:两种口径错配各有专门的用例。

## 三、未覆盖(不构成打回)

**① `status` 的提示对 dev 可能变成常驻噪音。** 本轮几乎每个工作项都改契约,而没有任何
东西强制 dev 重跑 —— dev 那一份一旦过期,之后每一次 `status` 都会打这句提示,直到它
自己重跑。提示是契约允许的、不阻断,但一句**永远在的提示**会教人忽略它。现在不改;
第六轮独立运行时值得数一下 dev 实际有没有因此重跑过。

**② 排障那一节的"重跑 `verify-setup`",工作项中途不一定跑得通。** `verify-setup` 要求
基线全绿,而 spec 回合结束时套件必然是红的。`claim` 发生在 idle(全绿),所以对门禁本身
没影响;只是 `status` 在工作项中途提示你重跑时,照做可能会失败在"基线不是全绿"。
可用性问题,不是契约问题。

**③ `claim` 侧 8 个变异点还没登记进 `MUTATIONS`。** 你提醒得对:我那个异议回弹的 spec
回合是本工作项里唯一能写 `tests/` 的回合,我漏了。已按 W12 的办法写进 `DECISIONS.md`,
附 8 组 old/new 字面,在我下一个能写 `tests/` 的回合(W14 的 spec)登记。
