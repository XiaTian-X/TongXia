# W54 review-test(dev)

裁决: approve

## 我检查了什么

- `mutation_check.py` 的注释:"必然由变异引起"改成"在测试确定、环境不变的前提下可以归因",并写出为什么不是必然(一次采样、几十个另建副本、运行器并行与串行不同);
  只改注释,代码没动。与路线图第 8 条的分析一致。
- `test_mutation_tooling.TestCacheShape.test_每条缓存的抓手不超过_MAX_CACHED`:读 `load_cache()`,逐条比 `MUT.MAX_CACHED`;没有缓存文件 skip,读出空的红。
- 隔离副本里探形状用例:一条记两个抓手 → 红;同样数据、`MAX_CACHED` 改 2 → 绿(比的是常量,不是写死的 1);catchers 读出空的 → 红;删掉缓存文件 → skip。
- 归一化后的缓存经 impl 回合的默认路径自证(211 个全部抓到)与 review-impl 的逐条比对(210 条是原第一个抓手,1 条失效后被快路径重写)。
- 全套 644 绿。

## 未覆盖

- 没有缓存文件时这条 skip:新克隆的仓库里缓存是被跟踪的,一般都在;真缺了由 `mutation_check` 自己重建。
- 注释的措辞没有用例守。
