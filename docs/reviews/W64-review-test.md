# W64 review-test(dev)

裁决: changes

## 我检查了什么

- `tests/conformance/test_v1_repo_root_files.py` 8 条与契约「仓库根两个文件的内容校验」对上:
  - `force-include` 节里有协议目录的映射,源路径下真有 `SKILL.md`。
  - 根 `.gitignore` 按整行比,比样板那条的子串比较更严,`.pair/whoami-old` 不再满足 `.pair/whoami`。
  - 读法五格都有用例钉住:节在中间、注释掉的不算、没有这一节、子串不算、行首行尾空白不计。
- 不用 `tomllib` 的理由成立(CI 有 3.9);只认 `"键" = "值"` 一行一条、宁可误红,我同意。
- 笔记里的三个探针放在项目内的 `.pair/scratch/`,用完已删,符合新的临时文件规则。

## 打回原因:映射的目标没钉,改错了 `pair init` 分发的 wheel 照样坏,测试全绿

- 契约背景写的是"`force-include` 那一行决定协议目录进不进 wheel,`pair init` 分发的就是它"。进 wheel 之后,CLI 只在一个固定位置找它:
  `cli/pair_bootstrap/__init__.py:31` 的 `packaged = Path(__file__).resolve().parent / "skill"`。
  装好的包里找不到时会去上级目录找仓库,而在 site-packages 里那里什么都没有,`find_bundled_skill()` 返回 None。
- `tests/conformance/test_v1_repo_root_files.py:68` 只断言目标非空。
- **探针**:在项目内 `.pair/scratch/` 的副本里把目标改成 `"pair_bootstrap/skills"`(多一个 s),`test_v1_repo_root_files` 加 `test_v1_cli` 共 17 条全绿,副本用完已删。
  `test_v1_cli.TestPackagedLayout` 是手工拷到 `pkg / "skill"` 模拟布局的,不读 `pyproject.toml`,同样看不见。

**请补**:断言映射的目标就是 CLI 找它的那个位置。
- 不要在用例里写死 `"pair_bootstrap/skill"` 这个字面量。`find_bundled_skill` 改名或换位置时,两边应该一起红。
- 一种做法:用 `[tool.hatch.build.targets.wheel] packages` 里的包目录名,拼上 `__init__.py` 里 `packaged` 那一行的子目录名。
- 或者在临时目录里按映射目标搭出布局,调用 `find_bundled_skill()`,看它找不找得到,和 `TestPackagedLayout` 同一个手法,只是目标路径从 `pyproject.toml` 读。

## 未覆盖(不阻断)

- TOML 的其他写法(单引号键、行内表)会误红:笔记已记,取舍成立。
- 根 `.gitignore` 里多出来的行不校验:契约只要求"每一行都在"。

## 第二轮(tester 按打回补用例之后)

裁决: approve

- 新补的 `TestWheelLayoutFindsSkill.test_CLI_在_force_include_的目标处找到协议`:
  - 包目录取自 `packages`,入口模块取自 `[project.scripts]`,`SKILL.md` 只放到 `force-include` 的目标处。
  - 在子进程里 `find_bundled_skill()` 要正好返回那个目标。没有写死字面量。
  - 子进程的 cwd 是临时布局,`-c` 下 cwd 排在 `sys.path` 最前,不会误用装在别处的同名包。在包内找不到时,它往上找仓库,临时目录上面没有仓库,所以返回 None。
- 我在项目内 `.pair/scratch/` 的副本里重跑同一个探针(目标多一个 s):这一条红。副本已删。原样 10 条全绿。
- 只动 tests,走 W17 捷径回 review-test,合规。
