# W57 review-test(dev)

裁决: changes

## 问题

1. **"算不出指纹就照常执行"那一支没有用例** —— `.agents/skills/pair-protocol/scripts/pair.py:783` 的
   `if added.returncode != 0 or listed.returncode != 0 or tracked_raw is None: return None` 换成"失败也当空串继续",
   隔离副本里 `tests/conformance/test_v1_test_reuse.py` 19 条全绿。这是你在 review-impl 挑出的那个洞(读不了的文件让 `add -A` 失败、改了实现也复用旧 GREEN),
   修法已落地,但没有用例守,一次重构就能退回去。按你在 review-impl 里给的形状补:未跟踪的 `chmod 000` 文件 + 两次 `status` 之间加一个没有实现的测试 →
   第二次重跑、RED;root 下读权限不生效时 skip。只动 tests,走 W17 捷径回 review-test。

## 其余查过

- 你在 review-impl 登记的六个变异点,我在 impl 回合的克隆里也逐个探过(恒重跑红 11、恒复用红 7、其余各红 1),与你 `--only` 的结果一致。
- 19 条用例的计数法(仓库外计数脚本 + 原判定)、排除项五格、对照组八格都对契约与补充。
