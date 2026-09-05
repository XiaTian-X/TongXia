# W3 实现评审(tester → dev)

**裁决:approve**

实现在 `e742a67`(异议那次带过来的),本回合 `3bb7193` 未再动实现。

---

## 逐条对契约「简报的降级与忽略」,十条全过

| 契约条款 | 实现 | 判定 |
|---|---|---|
| 不许因为写简报失败而让 `status` 失败 | `try` / `except OSError`,不 `return` | ✓ |
| 抛 `OSError` 时 `status` 继续正常执行 | 同上 | ✓ |
| 标准输出多出**恰好一行**,以 `[简报]` 开头 | 一句 `print`,且 `str(exc).replace("\n", " ")` | ✓ |
| 退出码与不写简报时完全相同 | `except` 后不改控制流 | ✓ |
| 其余输出不受影响(头部/阶段简报/记忆注入) | `try` **只裹住 `write_brief` 一句** | ✓ |
| **只兜 `OSError`** | `except OSError`,不是 `except Exception` | ✓ |
| `init` 之后 `.gitignore` 含该行 | `GITIGNORE_LINES` 加 `BRIEF_REL` | ✓ |
| 幂等 | 沿用既有的 `ln not in have` 子串判重,未新增分支 | ✓ |
| 只管 `init` 铺的新项目 | 只动 `GITIGNORE_LINES` | ✓ |
| **不做**:不因该行缺失而拒绝任何操作 | 没有新增任何检查 | ✓ |

两处值得点名:

- **`str(exc).replace("\n", " ")`。** 契约要求"恰好一行",而 `OSError` 的
  消息含换行就会破掉它。这是我写用例时没想到、实现主动补上的防御。
- **`GITIGNORE_LINES` 用的是 `BRIEF_REL` 常量,不是字面量。** 单一真源,
  路径将来改名不会漏掉这一处。

无硬编码、无针对测试输入的特判。

## 我跑了两个变异确认拦截力

不是读出来的:

| 变异 | 变红的用例 |
|---|---|
| `except OSError` → `except ZeroDivisionError` | `test_写失败时退出码不变…`、`test_写失败时不影响记忆注入` |
| 从 `GITIGNORE_LINES` 拿掉 `BRIEF_REL` | `test_init_之后_gitignore_含简报`、`test_重复跑_init_不重复追加` |

四条用例各司其职,没有一条是恒真的。

---

## 一处缺口:W3 的两条防护**没有变异点**,而补它是我的活

`mutation_check.py` 现在 71 个变异点,**没有一个针对 W3**(全仓 grep
"简报" 只命中 W2 那个「拆掉简报的提前收尾守卫」)。按 `contributing.md`
的五步纪律,新增防护要补变异点。

**这不构成打回:** 缺的这一步在 `tests/conformance/**`,是 **tester 的活**,
不是你的。为我自己没做的事打回你,方向不对。而且上面两个手工变异已经
证明**拦截力确实在** —— 缺的是把这个事实固化,不是防护本身。

**但它和我上一轮被你打回的形状同源**(防护有效 ≠ 有东西持续守着它),
所以我不把它埋进「未覆盖」了事。锚点我验过唯一命中、拦截力也验过:

```python
    ("拆掉简报写入失败的降级",
     "        except OSError as exc:",
     "        except ZeroDivisionError as exc:"),

    ("拆掉简报进 GITIGNORE_LINES",
     '".pair/whoami", ".pair/turns/", BRIEF_REL,',
     '".pair/whoami", ".pair/turns/",'),
```

补它需要一个 `spec` 回合(只读评审回合写不了 `mutation_check.py`)。
**建议归进人类要开的那个 `[cover]` 工作项**,和 W2 遗留的截断路径一起补 ——
两件都是纯测试侧、当前行为已正确、`cover` 全程 GREEN 的形态正好合适。
我已把这条写进 W3 笔记,你在完成回合会撞上 note-promotion,那时可以决定
晋升成决策还是 `--no-decision`。

---

## 未覆盖(记录在案,不是打回理由)

- **非 `OSError` 异常**:契约「边界」有意留白,实现与契约一致,双方都没测。
- **警告行的位置**没有断言,契约也没规定 —— 这是刻意的,不是遗漏。
- W2 遗留的**截断路径**仍然零测试;当前实现下结构性成立(简报与终端同一个
  字符串),不是缺陷。
