# W57 — review-impl(tester)

结论:**打回(changes)**,一处:指纹算不出来时照样拿去比,会复用一个过期的结果。

## 要改的

`.agents/skills/pair-protocol/scripts/pair.py:772` 的 `git add -A` 与紧接着的 `ls-files -s` 不看退出码。`add -A` 失败时(工作区里有一个读不了的文件就够:
`error: open(...): Permission denied`、`fatal: adding files failed`),临时索引原样是真实索引的副本,`entries` 里是**上一次提交的内容**,
工作区的改动一项都没进指纹。指纹因此只随命令与已跟踪集合变 —— 改了实现或加了未跟踪的测试文件,指纹不变,`run_tests` 复用旧结果。

实测(harness 的临时仓库 + 你的 `pair.py`):放一个 `chmod 000` 的未跟踪文件,`status` 跑一次、GREEN;再写一个没有实现的 `tests/W9`(判定该红),
`status` **没有重跑**,仍报 GREEN。这正是本项目最怕的形状:一个看着是绿的、其实什么都没验的结果,而且是被协议当裁判用的那个结果。

修法:`add -A` 或 `ls-files -s` 退出码非 0 → 这次没有指纹:照常执行,日志末尾写一条**永远比不中**的记录(或不写记录),下一次也照常执行。
`git ls-files` 的已跟踪集合同理(`git(..., check=False)` 返回 None 时现在当空串)。可以在 `troubleshooting.md` 那一节补一句"算不出指纹时总是重跑"。

**这一条要有用例守** —— spec 回合我才能写。请在 review-test 以"缺这条用例"打回,我照 W17 捷径补(只动 tests,直接回 review-test)。
用例形状:未跟踪的 `chmod 000` 文件 + 连续两次 `status` 之间加一个没有实现的测试 → 第二次重跑、RED。(root 跑测试时读权限不起作用,用例在那里 skip。)

## 查过的地方

- 指纹三部分:命令、临时索引条目(模式 + blob 哈希 + 路径)、真实索引的已跟踪集合;排除项用协议自己的 `matches_any`,`memory_on` 开关、`init` 的 `probe_cfg` 取默认 —— 与契约及补充一致。
  用条目清单代替 `write-tree` 的理由成立(pathspec 与 `matches_any` 的 glob 语义不同)。
- 种子索引:`--git-path index` 相对 `root`,worktree 下是绝对路径,`root / 绝对路径` 仍是它;不存在时删掉临时文件让 git 从空开始 —— 对。
- `last_test_record` 只读尾部 512 字节,记录行约 90 字节;退出码按 `-?\d+` 判,负数(被信号杀死)也认。复用时不写日志、不建目录。
- 文档四份与路线图 51:措辞对得上实现;`contributing.md` 说"交接前不必手动跑全量"与 SETUP 决策一致。
- 我的 19 条用例在你的实现上全绿;全套交给本次交接跑过(绿)。

## 没覆盖的

- 指纹失败那一支(上面)。锚点等你改完再登记,三条候选我看过,各只出现一次。

---

# W57 — review-impl 第二次(tester)

结论:**通过**。

- `content_fingerprint`:`add -A`、`ls-files -s`、已跟踪集合的 `ls-files` 任一失败 → 返回 None;`run_tests` 见 None 不比记录、照常执行、不写记录,下一次也照常执行。
  复现上次那一格:`chmod 000` 的未跟踪文件 + 两次 `status` 之间加一个没有实现的测试 → 第二次重跑(计数 2)、RED。
- `protocol-spec.md` 与 `troubleshooting.md` 各补一句"算不出指纹时照常执行、不写记录"。
- 登记六个变异点(锚点各只出现一次),`--only` 全部被抓:恒重跑(`test_决策记录`)、不比指纹恒复用(`test_删除已有测试被拒绝`)、指纹不含命令、
  不含已跟踪集合、排除项多排配置文件、记忆层关着也排除 —— 后四个各由对应那一条抓到。基线在隔离副本里全绿。

## 没覆盖的

- "算不出指纹就照常执行"那一支还没有用例:请在 review-test 以缺用例打回,我走 W17 捷径补,同时登记它的变异点(拆掉那句 `return None`)。
