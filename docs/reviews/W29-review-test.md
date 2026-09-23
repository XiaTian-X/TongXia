# W29 — review-test(dev 审 tester 的测试)

裁决: changes

## 问题

**契约点名的"上级是别的 git 仓库"那一支,没有任何用例接得住。**

`docs/pair-run/CONTRACT.md:1393`(你在 spec 回合带声明补的那段)写:`examples/` 的上级若是**别的** git 仓库
(zip 解压进了用户自己的项目),也按"不是本仓库的检出"处理 —— 否则 `ls-files` 在那个仓库里一个都列不出来,
生成出一个空项目。实现里对应的是 `examples/make-demo.py` 的 `if Path(top…).resolve() != REPO: return None`。

隔离克隆(`.pair/scratch/w29`,用完删掉)里把这两行删掉,`test_v1_make_demo_tracked` + `test_v1_shipped` **全绿**。
原因:`TestNotAGitCheckout`(`tests/conformance/test_v1_make_demo_tracked.py:120`)的 `source(git=False)` 放在
系统临时目录里,上级不是任何 git 仓库,`rev-parse` 直接失败 —— 走不到那个判断。

我另外实跑了这个变异的后果:把被跟踪的样板、技能目录与改坏的 `make-demo.py` 放进一个**外层 git 仓库**的子目录里运行,
**退出码 0,生成的项目里一个样板文件都没有**(没有 `docs/`、没有 `src/`)—— 正是契约那段描述的失败,而且是静默的。

**候选形状**:`source(git=False)` 之外再给一个"放进外层 git 仓库"的变体(在临时目录里 `git init` 一个外层仓库,
把 mini TongXia 放进它的子目录、不提交),断言生成的项目里有 `docs/PLAN.md` 与 `src/`。正确实现绿、去掉那两行红。

## 查过、没问题的

| 注入 | 红 |
|---|---|
| 退回 `shutil.copytree` 整目录复制 | `test_未跟踪文件不带出去`、`test_空目录不带出去`、`test_不在_git_检出里也跳过空目录` |
| 非 git 时连空目录一起建 | `test_不在_git_检出里也跳过空目录` |
| 干净 | 无 |

- **判据能区分"只删这一个目录"与"只发被跟踪的"**:`plant()` 在临时检出里造了一个未跟踪文件和一个空目录,
  整目录复制的修法在前者上一定红。
- **对照组**:被跟踪的样板文件一个不少、技能目录与软链接都在 —— "什么都不复制"过不了。
- `test_本仓库样板生成的项目里没有空目录` 在克隆里没随整目录复制变红:克隆不带空目录,这是克隆的性质,
  在本仓库的真实工作区里它就是今天红的那一条,不算问题。
- 不碰本仓库真实的样板目录,临时目录都 `addCleanup`。
