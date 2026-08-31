# 公共函数,被其他脚本 source。不要直接执行。
set -euo pipefail

# 定位项目根:skill 可以被装在任何地方,项目状态永远在 git 根的 .pair/ 下
PAIR_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf '\n[结对协议] 这里不是 git 仓库。结对协议依赖 git 做交接。\n\n' >&2; exit 1; }
cd "$PAIR_ROOT"
[ -f .pair/config ] || {
  printf '\n[结对协议] 找不到 .pair/config。本仓库尚未初始化结对协议。\n\n' >&2; exit 1; }
. .pair/config

STATE=".pair/STATE.md"

# --- 状态读写 ---------------------------------------------------------------
sget() { sed -n "s/^$1:[[:space:]]*//p" "$STATE" | head -1; }
sset() {
  local k="$1" v="$2" tmp
  tmp="$(mktemp)"
  if grep -q "^$k:" "$STATE"; then
    sed "s|^$k:.*|$k: $v|" "$STATE" > "$tmp"
  else
    cp "$STATE" "$tmp"; printf '%s: %s\n' "$k" "$v" >> "$tmp"
  fi
  mv "$tmp" "$STATE"
}

# --- 角色 -------------------------------------------------------------------
# 唯一来源:PAIR_ROLE 环境变量。所有 harness 都继承环境变量,这是最大公约数。
role() {
  case "${PAIR_ROLE:-}" in
    tester|dev) printf '%s' "$PAIR_ROLE" ;;
    "") die "PAIR_ROLE 未设置。请停止工作,让人类用 PAIR_ROLE=tester 或 PAIR_ROLE=dev 重启你。" ;;
    *)  die "PAIR_ROLE='$PAIR_ROLE' 无效,只能是 tester 或 dev。" ;;
  esac
}

# 每个阶段的负责人。回合严格按 spec -> impl -> review-impl -> review-test 轮转。
owner_of() {
  case "$1" in
    spec|review-impl) printf 'tester' ;;
    impl|review-test) printf 'dev' ;;
    *) die "STATE.md 里的 phase='$1' 非法" ;;
  esac
}

allowed_paths() {
  case "$1" in
    tester) printf '%s %s' "$TESTER_PATHS" "$SHARED_PATHS" ;;
    dev)    printf '%s %s' "$DEV_PATHS"    "$SHARED_PATHS" ;;
  esac
}

# --- 测试 -------------------------------------------------------------------
# 返回 0=绿 1=红。测试输出写到 .pair/.last-test.log
run_tests() {
  [ -n "${TEST_CMD:-}" ] || die "未配置 TEST_CMD。请编辑 .pair/config 填入本项目的测试命令。"
  if eval "$TEST_CMD" > .pair/.last-test.log 2>&1; then return 0; else return 1; fi
}

die() { printf '\n[结对协议] %s\n\n' "$*" >&2; exit 1; }
