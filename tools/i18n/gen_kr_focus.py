"""파이프라인 focus 에 중국어로 직접 적힌 진행 메시지를 한국어 리소스(resource_kr)에서 덮어쓴다.

원본 파이프라인의 focus 중 일부는 "$키" 번역 키가 아니라 중국어 문장이 그대로 들어 있어
UI 언어를 한국어로 해도 중국어로 표시된다. 원본 파일은 건드리지 않고,
assets/resource_kr/pipeline/Focus/ 아래에 같은 노드 이름으로 focus 만 다시 정의한다.
(리소스 번들은 나중에 불러온 쪽의 필드가 앞쪽 노드 필드를 덮어쓴다. focus 는 통째로 바뀌므로
 "$키" 값이나 {"trace": true} 같은 객체도 원본 그대로 함께 옮긴다.)

번역은 tools/i18n/kr_focus_translations.json (중국어 원문 → 한국어) 에서 가져온다.
업스트림을 합친 뒤 다시 실행하면 새로 생긴/바뀐 문구를 알려 준다.

사용법(저장소 루트에서):
    python tools/i18n/gen_kr_focus.py           # 미리보기(번역 누락 목록 출력)
    python tools/i18n/gen_kr_focus.py --write   # Focus 폴더 다시 생성
    pnpm prettier --write assets/resource_kr/pipeline/Focus
"""

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = ROOT / "assets" / "resource" / "pipeline"
KR_DIR = ROOT / "assets" / "resource_kr" / "pipeline"
OUT_DIR = KR_DIR / "Focus"
MAP_FILE = Path(__file__).resolve().parent / "kr_focus_translations.json"

HAN = re.compile(r"[一-鿿]")


def strip_jsonc(text: str) -> str:
    """문자열 안은 건드리지 않고 // 와 /* */ 주석, 뒤쪽 쉼표를 지운다."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(ch)
            i += 1
    cleaned = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", cleaned)


def load_jsonc(path: Path) -> dict:
    return json.loads(strip_jsonc(path.read_text(encoding="utf-8")))


def needs_translation(value: str) -> bool:
    return not value.startswith("$") and bool(HAN.search(value))


def has_literal_cjk(node_focus) -> bool:
    if isinstance(node_focus, str):
        return needs_translation(node_focus)
    if isinstance(node_focus, dict):
        return any(has_literal_cjk(v) for v in node_focus.values())
    if isinstance(node_focus, list):
        return any(has_literal_cjk(v) for v in node_focus)
    return False


def translate(value, table: dict, missing: dict, where: str):
    if isinstance(value, str):
        if needs_translation(value):
            if value in table:
                return table[value]
            missing.setdefault(value, where)
        return value
    if isinstance(value, dict):
        return {k: translate(v, table, missing, where) for k, v in value.items()}
    if isinstance(value, list):
        return [translate(v, table, missing, where) for v in value]
    return value


def hand_written_kr_nodes() -> dict:
    """Focus 폴더 밖 resource_kr 파이프라인에 이미 정의된 노드 → 파일."""
    nodes = {}
    for path in sorted(KR_DIR.rglob("*.json")):
        if OUT_DIR in path.parents:
            continue
        for name in load_jsonc(path):
            nodes[name] = path
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="Focus 폴더를 다시 생성한다")
    args = parser.parse_args()

    table = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    manual = hand_written_kr_nodes()
    missing: dict = {}
    skipped = []
    outputs: dict = {}
    used = set()

    for path in sorted(BASE_DIR.rglob("*.json")):
        data = load_jsonc(path)
        rel = path.relative_to(BASE_DIR)
        for name, node in data.items():
            if not isinstance(node, dict) or "focus" not in node:
                continue
            if not has_literal_cjk(node["focus"]):
                continue
            if name in manual:
                skipped.append(f"{name} ({manual[name].relative_to(ROOT)})")
                continue
            before = len(missing)
            focus = translate(copy.deepcopy(node["focus"]), table, missing, f"{rel}::{name}")
            used.update(v for v in _strings(node["focus"]) if v in table)
            if len(missing) == before:
                outputs.setdefault(rel, {})[name] = {"focus": focus}

    unused = sorted(set(table) - used)
    total = sum(len(v) for v in outputs.values())
    print(f"번역 노드 {total}개 / 파일 {len(outputs)}개")
    if skipped:
        print("resource_kr 에 이미 있는 노드라 건너뜀(직접 focus 를 넣을 것):")
        for item in skipped:
            print("  -", item)
    if missing:
        print(f"번역 누락 {len(missing)}개 (kr_focus_translations.json 에 추가 필요):")
        for text, where in missing.items():
            print(f"  - {where}: {json.dumps(text, ensure_ascii=False)}")
    if unused:
        print(f"더 이상 쓰이지 않는 번역 {len(unused)}개:")
        for text in unused:
            print("  -", json.dumps(text, ensure_ascii=False))

    if args.write:
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        for rel, nodes in outputs.items():
            target = OUT_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(nodes, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
        print(f"{OUT_DIR.relative_to(ROOT)} 에 기록했습니다")
    return 1 if missing else 0


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


if __name__ == "__main__":
    sys.exit(main())
