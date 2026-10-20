# W57 review-test(第二次,dev)

裁决: approve

## 我检查了什么

- 补的 `TestFingerprintUnavailable`:未跟踪的 `chmod 000` 文件让 `git add -A` 失败;`status` 一次之后加一个没有实现的测试,第二次 `status` 计数加一、状态 RED。
  Windows 与 root 下 skip(读权限不拦);`addCleanup` 先于临时仓库的清理恢复权限(后注册先执行)。
- 隔离副本里:原样 20 条全绿;把"算不出指纹就返回 None"换成"失败当空串继续" → 只红这一条。登记的第七个变异点「算不出指纹也拿去比」与此一致。
- 前六个变异点(恒重跑、恒复用、不含命令、不含已跟踪集合、多排配置、memory 关着也排记忆层)在 impl 回合与 review-impl 都探过,各被对应用例抓住。
- CI 的 Linux/macOS 跑者不是 root,这条在 CI 上会真跑。

## 未覆盖

- 被 `.gitignore` 忽略的东西、测试环境本身、HEAD 与历史不在指纹里(契约「前提与边界」),靠 `PAIR_FRESH_TESTS=1` 与有改动时的重跑兜。
- 新机制要等本项完成、裁判副本重钉后才生效;完成后我在本仓库数一次真实回合里的运行次数。
