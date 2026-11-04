"""OCR 노드 expected 에 한국어(KR) 항목만 추가/보정한다.

sync_ocr_expected.py 는 CN/TC/EN/JP/KR 전체를 다시 정렬·확장하고 roi 까지 조정하므로,
업스트림 동기화와 섞이지 않게 한국어만 다루는 용도로 이 도구를 쓴다.

- sync_ocr_expected.py 의 파서·역색인·정규식 함수를 그대로 사용한다.
- 다른 언어 항목(순서·중복 포함)과 roi 는 건드리지 않는다.
- 언어표의 한국어 원문과 같은 기존 리터럴 중 공백이 있는 것은 \\s* 정규식으로 바꾼다
  (한국어 OCR 이 띄어쓰기를 빠뜨리는 경우 대비, 이미 정규식인 값은 그대로 둔다).
- And/Or(all_of/any_of) 안쪽의 인라인 OCR 도 재귀적으로 처리한다.
- @i18n-skip 배열은 새 문구를 추가하지 않고, 한국어 원문 리터럴의 공백 보정만 한다.
- 주석이 있는 배열은 서식 보존을 위해 문구를 추가하지 않고 목록만 출력한다(공백 보정은 문자열 단위로 적용).

업스트림을 합친 뒤 다시 실행하면 새로 생긴 OCR 노드에도 한국어가 추가된다.

사용법(저장소 루트에서):
    git clone --depth 1 https://github.com/SusieGlitter/EndFieldTranslationReferrer.git <tmp>
    python tools/i18n/append_kr_expected.py --i18n-dir <tmp>/i18n          # 미리보기
    python tools/i18n/append_kr_expected.py --i18n-dir <tmp>/i18n --write  # 실제 반영
    pnpm prettier --write <변경된 파일>
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_ocr_expected as s

HANGUL = re.compile(r"[가-힣]")
CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")


def parse_string_elements(parser: s.JsoncParser, start: int) -> list[tuple[str, int, int]] | None:
    """expected 배열의 문자열 원소를 (값, 시작, 끝) 으로 돌려준다. 문자열이 아닌 원소가 있으면 None."""
    elements: list[tuple[str, int, int]] = []
    i = start + 1
    while True:
        i = parser.skip_ws_comments(i)
        if parser.text[i] == "]":
            return elements
        if parser.text[i] != '"':
            return None
        value, end = parser.parse_string(i)
        elements.append((value, i, end))
        i = parser.skip_ws_comments(end)
        if parser.text[i] == ",":
            i += 1


def iter_array_object_starts(parser: s.JsoncParser, start: int) -> list[int]:
    """배열 원소 중 객체인 것의 시작 위치 목록."""
    starts: list[int] = []
    i = start + 1
    while True:
        i = parser.skip_ws_comments(i)
        if parser.text[i] == "]":
            return starts
        if parser.text[i] == "{":
            starts.append(i)
        i = parser.skip_ws_comments(parser.parse_value_end(i))
        if parser.text[i] == ",":
            i += 1


def ambiguous_shared_kr_texts(
    values: list[str],
    lang_ids: list[str],
    reverse_index: dict[str, set[str]],
    tables: dict[str, dict[str, str]],
) -> list[str]:
    """
    역색인에서 후보 ID 가 여러 개라 해석되지 않은 문구 중, 후보들의 한국어 번역이 하나로 같은 경우
    그 한국어 번역을 돌려준다. 이미 해석된 ID 와 겹치는 문구는 건너뛴다.
    """
    resolved = set(lang_ids)
    shared: list[str] = []
    for value in values:
        candidates = reverse_index.get(s.normalize_text(value), set())
        if len(candidates) <= 1 or candidates & resolved:
            continue
        kr_texts = {tables["KR"].get(lang_id, "") for lang_id in candidates}
        if len(kr_texts) == 1:
            kr_text = next(iter(kr_texts))
            if kr_text and kr_text not in shared:
                shared.append(kr_text)
    return shared


FALLBACK_MAX_LEN = 4  # 버튼·탭 이름 같은 짧은 문구만 (긴 문장은 오매칭 위험)
FALLBACK_MIN_SHARE = 0.2
FALLBACK_MAX_CANDIDATES = 3


def intersected_kr_candidates(
    values: list[str],
    reverse_index: dict[str, set[str]],
    english_reverse_index: dict[str, set[str]],
    tables: dict[str, dict[str, str]],
) -> list[str]:
    """
    한국어가 없고 언어 ID 가 하나로 정해지지 않는 배열에서, 짧은 UI 문구(버튼·탭 이름 등)의 후보 ID 를
    교차(교집합이 비면 합집합)해 한국어 번역 분포를 구하고, 비중이 큰 후보를 돌려준다.
    - 긴 문장·숫자·정규식은 대상에서 뺀다
    - 한 후보가 다른 후보를 포함하면 짧은 쪽만 남긴다(부분 일치이므로 짧은 쪽이 둘 다 맞춘다)
    """
    if any(HANGUL.search(value) for value in values):
        return []
    # 숫자·영문만 있는 배열(「0」「NEW」 등)은 언어 문구가 아니므로 제외
    if not any(CJK.search(value) for value in values):
        return []
    candidate_sets: list[set[str]] = []
    for value in values:
        normalized = s.normalize_text(value)
        if not normalized or len(normalized) > FALLBACK_MAX_LEN * 3:
            continue
        candidates = set(reverse_index.get(normalized, set()))
        if not candidates:
            candidates = set(english_reverse_index.get(s.normalize_english_for_match(value), set()))
        if not candidates:
            continue
        sample = next(iter(candidates))
        if len(s.normalize_text(tables["CN"].get(sample, value))) > FALLBACK_MAX_LEN:
            continue
        candidate_sets.append(candidates)
    if not candidate_sets:
        return []
    pool = set.intersection(*candidate_sets) or set().union(*candidate_sets)
    counts: dict[str, int] = {}
    for lang_id in pool:
        kr_text = s.normalize_text(tables["KR"].get(lang_id, ""))
        if kr_text and HANGUL.search(kr_text):
            counts[kr_text] = counts.get(kr_text, 0) + 1
    total = sum(counts.values())
    if not total:
        return []
    ranked = sorted(counts.items(), key=lambda item: (-item[1], len(item[0])))
    picked = [text for text, count in ranked if count / total >= FALLBACK_MIN_SHARE][:FALLBACK_MAX_CANDIDATES]
    if not picked or counts[ranked[0][0]] / total < 0.5:
        return []
    reduced: list[str] = []
    for text in sorted(picked, key=len):
        if not any(shorter in text for shorter in reduced):
            reduced.append(text)
    return reduced


def collect_ocr_expected_members(parser: s.JsoncParser, obj_start: int) -> list[s.Member]:
    """
    노드(또는 And/Or 내부 인라인 인식) 객체에서 OCR expected 배열을 모두 찾는다.
    v1(recognition: "OCR") / v2(recognition.type == "OCR") 와 all_of / any_of 안쪽을 재귀적으로 본다.
    """
    found: list[s.Member] = []
    members, _ = parser.parse_object_members(obj_start)
    obj_map = s.member_map(members)
    containers = [obj_map]

    rec = obj_map.get("recognition")
    is_ocr = False
    expected_member = None
    if rec is not None:
        if s.get_string_value(parser, rec) == "OCR":
            is_ocr = True
        else:
            rec_members = s.get_object_members(parser, rec)
            if rec_members is not None:
                rec_map = s.member_map(rec_members)
                containers.append(rec_map)
                type_member = rec_map.get("type")
                if type_member and s.get_string_value(parser, type_member) == "OCR":
                    is_ocr = True
                param = rec_map.get("param")
                if param:
                    param_members = s.get_object_members(parser, param)
                    if param_members is not None:
                        param_map = s.member_map(param_members)
                        containers.append(param_map)
                        expected_member = s.get_array_member_if_exists(parser, param_map, "expected")
                if expected_member is None:
                    expected_member = s.get_array_member_if_exists(parser, rec_map, "expected")
    if expected_member is None:
        expected_member = s.get_array_member_if_exists(parser, obj_map, "expected")
    if is_ocr and expected_member is not None:
        found.append(expected_member)

    for container in containers:
        for key in ("all_of", "any_of"):
            array_member = s.get_array_member_if_exists(parser, container, key)
            if array_member is None:
                continue
            for child_start in iter_array_object_starts(parser, array_member.value_start):
                found.extend(collect_ocr_expected_members(parser, child_start))
    return found


def main() -> int:
    argp = argparse.ArgumentParser(description="OCR expected 에 한국어(KR)만 추가/보정 (기본 dry-run)")
    argp.add_argument("--base-dir", type=Path, default=Path.cwd(), help="저장소 루트 (기본: 현재 디렉터리)")
    argp.add_argument("--i18n-dir", type=Path, default=None, help="i18n 디렉터리 (기본: tools/i18n)")
    argp.add_argument("--write", action="store_true", help="실제로 파일에 반영")
    args = argp.parse_args()

    repo_root = args.base_dir.resolve()
    write = args.write
    tables, i18n_dir = s.load_i18n_tables(repo_root, args.i18n_dir)

    s.apply_hotfix_to_tables(tables, i18n_dir)
    reverse_index, english_reverse_index = s.build_reverse_index(tables)

    total_nodes = 0
    added_nodes = 0
    added_strings = 0
    regexified = 0
    no_kr_in_table: list[str] = []
    unresolved: list[str] = []
    fallback_nodes: list[tuple[str, list[str], list[str]]] = []
    comment_arrays: list[str] = []
    touched_files: list[str] = []

    for path in s.iter_pipeline_files(repo_root):
        text = path.read_text(encoding="utf-8")
        parser = s.JsoncParser(text)
        newline = "\r\n" if "\r\n" in text else "\n"
        root_members, _ = parser.parse_object_members(parser.skip_ws_comments(0))
        replacements: list[tuple[int, int, str]] = []

        for node_member in root_members:
            if text[node_member.value_start] != "{":
                continue
            for index, expected_member in enumerate(collect_ocr_expected_members(parser, node_member.value_start)):
                label = f"{path.relative_to(repo_root)}::{node_member.key}"
                if index:
                    label += f" (내부 OCR #{index})"
                total_nodes += 1
                skip_marked = s.has_i18n_skip_marker(text, expected_member)
                elements = parse_string_elements(parser, expected_member.value_start)
                if elements is None:
                    continue
                old_expected = [value for value, _, _ in elements]
                lang_ids, _ = s.resolve_lang_ids(old_expected, reverse_index, english_reverse_index, tables)
                # 여러 ID 로 겹쳐 해석되지 않은 문구라도, 후보 ID 들의 한국어 번역이 모두 같으면 그 번역을 쓴다
                # (예: 「日常」은 ID 가 여럿이지만 한국어는 모두 「일상」)
                ambiguous_kr = ambiguous_shared_kr_texts(old_expected, lang_ids, reverse_index, tables)
                # 그래도 못 찾으면 같은 배열의 짧은 문구(간체/번체/영어 등) 후보 ID 를 교차해 한국어 후보를 고른다
                # (예: 「确认 / 確定 / Confirm」→ 대부분 「확인」)
                if not lang_ids and not ambiguous_kr and not skip_marked:
                    ambiguous_kr = intersected_kr_candidates(old_expected, reverse_index, english_reverse_index, tables)
                    if ambiguous_kr:
                        fallback_nodes.append((label, old_expected, ambiguous_kr))
                if not lang_ids and not ambiguous_kr:
                    if not skip_marked:
                        unresolved.append(label)
                    continue

                # 언어표의 한국어 원문(또는 그 원문으로 만든 옛 정규식)과 같은 값만 새 규칙으로 보정한다
                # (사람이 직접 쓴 다른 정규식은 그대로 둔다)
                kr_sources = [tables["KR"][lang_id] for lang_id in lang_ids if tables["KR"].get(lang_id)] + list(
                    ambiguous_kr
                )
                rewrite_map: dict[str, str] = {}
                for kr_text in kr_sources:
                    new_form = s.build_korean_ocr_regex(kr_text)
                    for old_form in (kr_text, s.build_korean_ocr_regex_legacy(kr_text)):
                        if s.normalize_text(old_form) != s.normalize_text(new_form):
                            rewrite_map[s.normalize_text(old_form)] = new_form
                element_fixes: list[tuple[int, int, str]] = []
                new_expected: list[str] = []
                for value, value_start, value_end in elements:
                    if HANGUL.search(value) and s.normalize_text(value) in rewrite_map:
                        value_regex = rewrite_map[s.normalize_text(value)]
                        if value_regex != value:
                            regexified += 1
                            element_fixes.append((value_start, value_end, json.dumps(value_regex, ensure_ascii=False)))
                            value = value_regex
                    # 기존 항목은 순서·중복까지 그대로 유지한다
                    new_expected.append(value)

                raw_array = text[expected_member.value_start : expected_member.value_end]
                has_comment = "//" in raw_array or "/*" in raw_array

                # @i18n-skip 배열은 수동 관리 대상이므로 새 문구는 추가하지 않고 공백 보정만 한다
                appended = 0
                if not skip_marked:
                    kr_values: list[str] = []
                    for lang_id in lang_ids:
                        kr_text = tables["KR"].get(lang_id, "")
                        if kr_text:
                            kr_values.append(s.build_korean_ocr_regex(kr_text))
                    kr_values.extend(s.build_korean_ocr_regex(kr_text) for kr_text in ambiguous_kr)
                    if not kr_values:
                        no_kr_in_table.append(label)
                    for kr_value in kr_values:
                        if kr_value not in new_expected:
                            new_expected.append(kr_value)
                            appended += 1

                if appended and has_comment:
                    # 주석이 있는 배열은 서식 보존을 위해 추가하지 않고 목록만 남긴다
                    comment_arrays.append(label)
                    appended = 0
                    new_expected = new_expected[: len(old_expected)]

                added_strings += appended
                if appended:
                    added_nodes += 1

                if new_expected == old_expected:
                    continue

                if appended:
                    key_indent = s.detect_line_indent(text, expected_member.key_start)
                    replacements.append(
                        (
                            expected_member.value_start,
                            expected_member.value_end,
                            s.build_expected_array_text(new_expected, key_indent, newline),
                        )
                    )
                else:
                    # 공백 보정만 있으면 해당 문자열만 교체해 주석·서식을 그대로 둔다
                    replacements.extend(element_fixes)

        if replacements:
            touched_files.append(str(path.relative_to(repo_root)))
            new_text = text
            for start, end, replacement in sorted(replacements, reverse=True):
                new_text = new_text[:start] + replacement + new_text[end:]
            if write:
                path.write_text(new_text, encoding="utf-8")

    mode = "WRITE" if write else "DRY-RUN"
    print(
        f"[{mode}] ocr_nodes={total_nodes} kr_added_nodes={added_nodes} "
        f"kr_added_strings={added_strings} kr_regexified={regexified} "
        f"touched_files={len(touched_files)} unresolved_nodes={len(unresolved)} "
        f"no_kr_in_table={len(no_kr_in_table)} skipped_comment_arrays={len(comment_arrays)}"
    )
    for title, items in (
        ("comment arrays (수동 처리 필요)", comment_arrays),
        ("no KR text in table", no_kr_in_table),
        ("unresolved (언어표에 없음)", unresolved),
    ):
        print(f"---- {title}: {len(items)}")
        for item in items:
            print(f"  {item}")
    print(f"---- cross-language fallback (교차 추정, 검토 권장): {len(fallback_nodes)}")
    for label, values, kr_texts in fallback_nodes:
        print(f"  {label}: {values[:4]} -> {kr_texts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
