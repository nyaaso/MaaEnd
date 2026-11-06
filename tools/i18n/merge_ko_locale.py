"""로케일 3방향 병합 (업스트림 병합 충돌 해결용, ko_kr 및 다른 언어 파일 모두).

base = 공통 조상, ours = 한국어 점검본(HEAD), theirs = 원본(upstream/v2)
- 키 구성은 theirs 를 따르고 키는 정렬한다(sortLocaleKeys)
- 한쪽만 바꾼 키는 바뀐 쪽을 쓴다
- 둘 다 바꾼 키:
  * theirs 가 base 에서 아이콘 마크다운(![](...))만 뺀 경우 → ours 에서도 같은 마크다운을 빼서 쓴다
  * 그 밖의 경우 → 일단 theirs 를 쓰고 수동 판단 목록(report)에 남긴다
- ours 에만 새로 생긴 키(base·theirs 에 없음)는 유지, 원본이 지운 키는 버린다

사용법(저장소 루트, 병합 진행 중 상태에서):
    python tools/i18n/merge_ko_locale.py <base_rev> <theirs_rev> <report.json>
결과 파일을 확인한 뒤 git add 한다.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

DOMAINS = ("interface", "go-service", "cpp-algo")
LANGS = ("ko_kr", "zh_cn", "zh_tw", "en_us", "ja_jp")
MD_ICON = re.compile(r"!\[[^\]]*\]\([^)]*\)\s*")


def show(rev: str, path: str) -> dict:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout) if out.returncode == 0 else {}


def strip_md(text: str) -> str:
    return MD_ICON.sub("", text)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    base_rev, theirs_rev, report_path = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    report = {}
    for domain, lang in ((d, lang) for d in DOMAINS for lang in LANGS):
        path = f"assets/locales/{domain}/{lang}.json"
        if not Path(path).exists():
            continue
        base, theirs, ours = show(base_rev, path), show(theirs_rev, path), show("HEAD", path)
        merged: dict = {}
        stats = {"theirs_only_change": 0, "ours_only_change": 0, "md_strip_auto": 0, "manual": 0, "new_keys": 0}
        manual = []
        for key, tv in theirs.items():
            if key not in ours:
                merged[key] = tv
                stats["new_keys"] += 1
                continue
            ov, bv = ours[key], base.get(key)
            if ov in (tv, bv):
                merged[key] = tv
                if ov != tv:
                    stats["theirs_only_change"] += 1
            elif tv == bv:
                merged[key] = ov
                stats["ours_only_change"] += 1
            elif isinstance(bv, str) and isinstance(ov, str) and tv == strip_md(bv):
                merged[key] = strip_md(ov)
                stats["md_strip_auto"] += 1
            else:
                merged[key] = tv
                stats["manual"] += 1
                manual.append({"key": key, "base": bv, "ours": ov, "theirs": tv})
        for key, ov in ours.items():
            if key not in theirs and key not in base:
                merged[key] = ov
                stats["kept_ours_added"] = stats.get("kept_ours_added", 0) + 1
        stats["dropped"] = len([k for k in ours if k not in theirs and k in base])
        merged = {k: merged[k] for k in sorted(merged)}
        Path(path).write_text(json.dumps(merged, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
        report[f"{domain}/{lang}"] = {
            "stats": stats,
            "manual": manual,
            "new_keys": [k for k in theirs if k not in ours],
            "theirs_changed_keys": [k for k in theirs if k in ours and ours[k] == base.get(k) and theirs[k] != ours[k]],
        }
        print(f"{domain}/{lang}", stats)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
