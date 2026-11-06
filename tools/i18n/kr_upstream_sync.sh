#!/usr/bin/env bash
# 원본(MaaEnd/MaaEnd v2) 변경을 한국어 포크(nyaaso/MaaEnd)에 병합하고 한국어 리소스를 다시 적용한다.
# 절차 설명: tools/i18n/KR_SYNC.md
#
# 사용법(저장소 루트, feat/kr-resource 브랜치):
#   tools/i18n/kr_upstream_sync.sh merge             # fetch + 병합 시작 + ko_kr 로케일 자동 병합
#   tools/i18n/kr_upstream_sync.sh apply <i18n-dir>  # 한국어 expected/focus 재적용 + 점검 + 검증
#
# merge 종료 코드: 0=새 변경 없음, 10=병합 준비됨(apply 진행), 20=수동 해결 필요한 충돌 남음
# apply 종료 코드: 0=검증 통과, 30=검증 실패
set -uo pipefail

REPORT_DIR="${KR_SYNC_REPORT_DIR:-${TMPDIR:-/tmp}/kr_sync}"
mkdir -p "$REPORT_DIR"

cmd="${1:-}"
case "$cmd" in
merge)
    git remote get-url upstream >/dev/null 2>&1 || git remote add upstream https://github.com/MaaEnd/MaaEnd.git
    git fetch -q upstream v2 || { echo "STATUS=FETCH_FAILED"; exit 1; }
    if git merge-base --is-ancestor upstream/v2 HEAD; then
        echo "STATUS=NO_UPDATE"
        exit 0
    fi
    base=$(git merge-base HEAD upstream/v2)
    theirs=$(git rev-parse upstream/v2)
    echo "BASE=$base"
    echo "THEIRS=$theirs"
    echo "--- 새 원본 커밋"
    git log --oneline HEAD..upstream/v2
    git merge --no-ff --no-commit upstream/v2 >/dev/null 2>&1
    # ko_kr 로케일은 충돌 여부와 관계없이 3방향 규칙으로 다시 만든다
    python3 tools/i18n/merge_ko_locale.py "$base" "$theirs" "$REPORT_DIR/locale_report.json"
    git add assets/locales/*/ko_kr.json
    conflicts=$(git diff --name-only --diff-filter=U)
    if [ -n "$conflicts" ]; then
        echo "--- 수동 해결이 필요한 충돌"
        echo "$conflicts"
        echo "STATUS=CONFLICT"
        exit 20
    fi
    echo "로케일 수동 판단 목록: $REPORT_DIR/locale_report.json (manual / new_keys / theirs_changed_keys)"
    echo "STATUS=READY"
    exit 10
    ;;
apply)
    i18n="${2:?i18n 디렉터리 경로가 필요합니다}"
    rc=0
    echo "=== 한국어 OCR expected 재적용"
    python3 tools/i18n/append_kr_expected.py --i18n-dir "$i18n" --write | tee "$REPORT_DIR/append.txt" | head -40
    echo "=== 중국어 focus 한국어 덮어쓰기 재생성"
    python3 tools/i18n/gen_kr_focus.py --write | tee "$REPORT_DIR/focus.txt"
    if grep -q "번역 누락" "$REPORT_DIR/focus.txt"; then
        echo "!!! focus 번역 누락: tools/i18n/kr_focus_translations.json 에 추가 후 apply 를 다시 실행"
        rc=30
    fi
    echo "=== 한국어 누락 점검"
    python3 tools/i18n/audit_kr_expected.py --i18n-dir "$i18n" | tee "$REPORT_DIR/audit.txt"
    if ! grep -q "^\[한국어 없음\] 0개" "$REPORT_DIR/audit.txt" || ! grep -q "^\[한국어 일부 누락\] 0개" "$REPORT_DIR/audit.txt"; then
        echo "!!! 한국어 누락 노드 있음: 직접 추가하거나 의도적 제외면 audit_kr_expected.py IGNORE 에 등록"
        rc=30
    fi
    echo "=== 형식/검증"
    changed=$(git diff --name-only HEAD -- '*.json' '*.yml' '*.yaml'; git diff --cached --name-only HEAD -- '*.json' '*.yml' '*.yaml')
    changed=$(echo "$changed" | sort -u | while read -r f; do [ -f "$f" ] && echo "$f"; done)
    if [ -n "$changed" ]; then
        # shellcheck disable=SC2086
        pnpm exec prettier --write $changed >/dev/null || rc=30
    fi
    pnpm exec prettier --write assets/resource_kr/pipeline/Focus >/dev/null || rc=30
    uv run tools/validate_schema.py --resource-dirs assets/resource \
        --overlay-dirs assets/resource_adb/pipeline assets/resource_cloud/pipeline assets/resource_linux/pipeline \
        assets/resource_macos/pipeline assets/resource_kr/pipeline \
        --exclude-dirs assets/resource/gamedata assets/resource/image assets/resource/model \
        --task-dirs assets/tasks 2>&1 | tail -3 || rc=30
    pnpm run check >"$REPORT_DIR/check.txt" 2>&1 || { echo "!!! pnpm check 실패: $REPORT_DIR/check.txt"; rc=30; }
    if git diff --cached --name-only HEAD | grep -q '^agent/go-service/' || git diff --name-only HEAD | grep -q '^agent/go-service/'; then
        (cd agent/go-service && go build ./... && go vet ./...) || { echo "!!! go build/vet 실패"; rc=30; }
    fi
    [ $rc -eq 0 ] && echo "STATUS=OK" || echo "STATUS=NEEDS_FIX"
    exit $rc
    ;;
*)
    sed -n '2,12p' "$0"
    exit 2
    ;;
esac
