# W30 — review-impl(tester)

结论:**实现通过**;**但登记变异时挖出一个测试侧的漏洞,归我,请 review-test 打回。**

## 实现查过的地方

- `scratch_hint(phase)`:路径 `next(l for l in GITIGNORE_LINES if l.startswith(".pair/scratch"))`,与机制同源,没另写字面;
  `GITIGNORE_LINES` 与「gitignore 不含 scratch」锚点原样。
- `cmd_status` 打完 `PHASE_BRIEF` 后 `phase != "idle"` 才打;评审阶段写"写在里面不算本回合的改动",工作阶段写"不进提交、不算越界",
  都带"能不写文件就不写"。`render_brief`/`BRIEF_REL` 没动。`rules.md` 补的那句照契约。
- 两个锚点字面唯一,已追加登记(「简报不提 scratch」「idle 也提 scratch」)。我在 spec 回合带 `.git` 的副本里探过:
  拆掉红 4 条、idle 也打只红 idle 那条 —— 真能抓。

## 漏洞:W29 我写的用例让 `mutation_check` 对任何新变异都报"抓到"

`--only scratch` 报两条都被 **`test_不在_git_检出里也跳过空目录`** 抓住 —— 与简报毫无关系。原因:
`mutation_check.isolated_copy` 复制仓库时**排除 `.git`**,而 `tests/conformance/test_v1_make_demo_tracked.py:27` 的 `tracked()`
用 `git ls-files ... check=True` 问本仓库 —— 在隔离副本里它必然抛错,那个文件的 6 条用例在**每一个**变异下都 ERROR。
全量回退是 failfast,第一个失败就停,于是任何新变异都被"抓到",而且缓存记下的抓手就是这条无关用例,
今后快路径只跑它、它恒失败 —— **这两条变异在缓存里被永久判成抓到**。基线跑在真实仓库里(有 `.git`),所以看不出来。

影响面:W29 那批用例落地(`02b033d`)之后首次全量判定的变异 —— 目前只有本回合这两条。

**修法(我在打回后的 spec 回合做,只动 tests,走 W17 捷径)**:本仓库不是 git 检出时,那 6 条 `skipTest` 并写明理由
(问不了 git 哪些被跟踪,无从判定;`make-demo.py` 本来就不在 `mutation_check` 范围);删掉缓存里这两条被污染的条目后重跑,
确认抓手是 `test_v1_scratch_brief` 的用例。另加一条防回归:在不含 `.git` 的副本里跑一遍全套应当全绿(或只有 skip)——
这正是 `--no-baseline` 预检的前提,今天它也会被这 6 条弄红。
