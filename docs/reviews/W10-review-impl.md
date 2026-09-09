# W10 review-impl（tester）

裁决: changes

实现的形状是对的,契约那几条逐条对上了,11 条用例全绿(312/312)。
**但重钉那条路径上有两处缺陷,而且我的用例一条都抓不到 —— 后者是我的问题。**

## 我检查了什么

- `judge_pair` 走 `PROG_HINT` 固定路径而不是 `__file__` —— 这是我在 spec 回合
  补第 11 条用例专门盯的那个恒真陷阱,实现正面挡住了,注释也把理由写下来了
- `judge_in_sync` 用 `read_bytes()` 比,不是 `strip()`、不是注册表 —— 逐字节
- `cmd_claim` 里校验的位置:在 `require_setup_verification` 之后、`parse_plan`
  之前,拒绝文案同时给出两个路径和 `cp` 命令
- `repin_judge` 的调用点:`save_state` 之后、`git add -A` 之前,只在
  `target == "DONE" and green` 时触发
- 副本不存在时 `judge_pair` 返回 `(None, None)`,两条都不触发
- 全套 312 条绿;我在 spec 回合注入过的五个错误实现,这份实现一个都不属于

## 问题

### ① `pair.py:507` 返回的 sha 没 `strip()`，提交正文被打断成两行

`git()` 返回的是 `proc.stdout.decode(...)` **原样**,带结尾换行(`pair.py:256`)。
于是提交正文变成:

```
 4|裁判副本已重钉: .agents/…/pair.py -> .pair/enforcer.py (780d7a07fba…
 5|)
```

这是我在临时仓库里跑到 DONE 之后 `git log -1 --format=%b` 的**实际输出**,
不是推断。行尾断开、右括号单独一行。

**同一个文件里已经有正确写法**:`blob_sha` 在 `pair.py:675` 写的是
`return out.strip() if out else None`。改法就是照它:

```python
out = git("hash-object", PROG_HINT, cwd=root, check=False)
return out.strip() if out else None
```

契约对这条的要求是"把新 sha **写进提交正文**",而这行正文是重钉唯一的纸面
记录 —— 它长成什么样不是纯风格问题。

### ② `pair.py:507` 用了 `check=False`，失败时副本已经改了、正文却什么都不说

`git(..., check=False)` 失败返回 `None` → `repinned` 为假 →
`pair.py:1900` 那个 `if repinned:` 不成立 → 提交正文里没有任何一行提到重钉。
**而 `copy.write_bytes()` 在 `pair.py:506` 已经执行过了。**

也就是说:裁判被换掉了,提交记录里一个字都没有。

概率低(`hash-object` 是本地 plumbing),但这正是 W10 存在的理由那一类失效
——**副本悄悄变了而没人知道**。上一轮那次漂移之所以整轮没被发现,就是因为
它不让任何东西变红。

两条出路,选哪条我不指定:让 `hash-object` 走 `check=True`(取不到 sha 就
让整次交接失败,重钉本来就该是全有或全无);或者取不到时往正文里写一行
"已重钉,sha 取失败"。**不能是现在这样:动作发生了,记录没有。**

## 未覆盖

**我的 `test_重钉的_sha_进提交正文` 断言的是 `sha[:7] in body` —— 上面两条它
一条都抓不到。** ① 里 sha 仍然完整出现在正文中,② 里正文没有那行、
但断言只在重钉成功时才会被检查到……不,② 的情况下断言会红。所以准确说:
**① 抓不到,② 抓得到。**

① 抓不到是我的用例太松:我当时刻意避开断言措辞(怕撞规则 4),结果连
"这一行是完整的一行"都没守住。正确的判据不是措辞,是**结构**——
正文里存在一行同时含 `JUDGE_REL` 与完整 sha,而不是"整份正文里含 sha 的前 7 位"。

`review-impl → changes` 会回到 `impl`,我这一轮拿不到能写 `tests/` 的回合。
**所以:如果修完之后你认为这条断言仍然太松,请在 `review-test` 回合打回我。**
那是协议里唯一能让我回到 `spec` 去收紧它的路径,我不认为那是浪费一次打回。

另外还没覆盖、这次不要求你做的:`PROG_HINT` 不存在而副本存在时
(`judge_pair` 返回 `(None, None)`)校验会**静默失效**。契约只说"副本存在时
必须相等",没说正本缺失怎么办,所以这不算偏离契约 —— 记在这里,不作为打回理由。
