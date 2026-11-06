"""OCR expected 의 한국어 누락 점검.

1) 중국어/일본어 문구는 있는데 한국어 항목이 하나도 없는 OCR 배열
2) 한국어가 일부만 있는 배열: 게임 언어표(CN→KR)로 해석되는 중국어 문구 중
   대응 한국어 텍스트와 일치하는 한국어 항목이 없는 것

사용법(저장소 루트):
    python tools/i18n/audit_kr_expected.py --i18n-dir <EndFieldTranslationReferrer>/i18n
결과를 보고 필요한 한국어 expected 를 직접 추가한다(언어 감지 등 의도적으로 제외한 노드는 IGNORE).
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contextlib

import append_kr_expected as a
import sync_ocr_expected as s

HANGUL = re.compile(r"[가-힣]")
HAN = re.compile(r"[一-鿿]")
KANA = re.compile(r"[぀-ヿ]")

# 한국어를 넣지 않는 것이 맞는 노드(언어 감지·중국 전용·실행 중 주입 등)
IGNORE = {
    "__SceneImageCheckLanguageSuccess",
    "__EssenceFilterDetectLangCN",
    "__EssenceFilterDetectLangTC",
    "__EssenceFilterDetectLangJP",
    "AutoMissionDialogRecognition",
    "AutoMissionInteractRecognition",
    "AutoMissionTrackTargetRecognition",
    "CloudEndfieldCheckInGame",
    "CloudEndfieldGameCard",
    "CloudEndfieldStartGame",
    "MapNavigatorZiplineOnTowerHintAdb",
    "MapNavigatorZiplineCheckHintAdb",
    "AutoMissionNpcProxyActionInteractRecognition",
    "AutoMissionEntityActionInteractRecognition",
    "CloudEndfieldWaitStartGame",
    "CloudEndfieldRetryText",
    "CloudEndfieldRetryButton",
    # 상점 「更新」=새로고침(언어표의 「업데이트」와 뜻이 다름)
    "RefreshText",
    # 계정 번호(숫자) 패턴뿐이라 언어와 무관
    "__AccountSwitchClickDropdown",
    "__AccountSwitchOCRSelectAccount",
    "__AccountSwitchCheckAccount",
    "__AccountSwitchVerifySelected",
}


def core(value: str) -> str:
    text = re.sub(r"\(\?i\)", "", value).strip("^$")
    return text.replace("\\s*", "").replace(".*", "").replace(".?", "")


def array_values(parser, text, member) -> list[str]:
    elements = a.parse_string_elements(parser, member.value_start)
    if elements is not None:
        return [v for v, _, _ in elements]
    raw = re.sub(r"//[^\n]*", "", text[member.value_start : member.value_end])
    return [json.loads('"' + x + '"') for x in re.findall(r'"((?:[^"\\]|\\.)*)"', raw)]


def main() -> int:
    argp = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    argp.add_argument("--base-dir", type=Path, default=Path.cwd())
    argp.add_argument("--i18n-dir", type=Path, required=True)
    args = argp.parse_args()

    cn = json.loads((args.i18n_dir / "I18nTextTable_CN.json").read_text(encoding="utf-8"))
    kr = json.loads((args.i18n_dir / "I18nTextTable_KR.json").read_text(encoding="utf-8"))
    index: dict[str, set[str]] = defaultdict(set)
    for key, value in cn.items():
        if isinstance(value, str) and kr.get(key):
            index[value.strip()].add(kr[key].strip())

    missing_all, partial = [], []
    for path in s.iter_pipeline_files(args.base_dir):
        if "resource/pipeline" not in path.as_posix() or "resource_" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        parser = s.JsoncParser(text)
        root, _ = parser.parse_object_members(parser.skip_ws_comments(0))
        for member in root:
            if text[member.value_start] != "{" or member.key in IGNORE:
                continue
            for idx, em in enumerate(a.collect_ocr_expected_members(parser, member.value_start)):
                values = array_values(parser, text, em)
                label = f"{path.relative_to(args.base_dir).as_posix()}::{member.key}#{idx}"
                korean = [v for v in values if HANGUL.search(v)]
                if not korean:
                    if any(HAN.search(v) or KANA.search(v) for v in values):
                        missing_all.append((label, values[:4]))
                    continue
                patterns = []
                for v in korean:
                    with contextlib.suppress(re.error):
                        patterns.append(re.compile(v))
                gaps = []
                for v in values:
                    if not HAN.search(v) or KANA.search(v):
                        continue
                    c = core(v)
                    if re.search(r"[\[\]()|\\+{}]", c) or c not in index:
                        continue
                    targets = index[c]
                    if not any(p.search(t) for p in patterns for t in targets):
                        gaps.append((v, sorted(targets)[:2]))
                if gaps:
                    partial.append((label, gaps[:4]))

    print(f"[한국어 없음] {len(missing_all)}개")
    for label, values in missing_all:
        print(f"  - {label} | {json.dumps(values, ensure_ascii=False)}")
    print(f"[한국어 일부 누락] {len(partial)}개")
    for label, gaps in partial:
        print(f"  - {label} | {json.dumps(gaps, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
