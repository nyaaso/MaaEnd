"""OCR 노드 expected 에 한국어(KR) 항목만 추가/보정한다.

sync_ocr_expected.py 는 CN/TC/EN/JP/KR 전체를 다시 정렬·확장하고 roi 까지 조정하므로,
업스트림 동기화와 섞이지 않게 한국어만 다루는 용도로 이 도구를 쓴다.

- sync_ocr_expected.py 의 파서·역색인·정규식 함수를 그대로 사용한다.
- 다른 언어 항목(순서·중복 포함)과 roi 는 건드리지 않는다.
- 언어표의 한국어 원문과 같은 기존 리터럴 중 공백이 있는 것은 \\s* 정규식으로 바꾼다
  (한국어 OCR 이 띄어쓰기를 빠뜨리는 경우 대비, 이미 정규식인 값은 그대로 둔다).
- expected 배열 안에 주석이 있는 노드는 서식 보존을 위해 건너뛰고 목록만 출력한다.

업스트림을 합친 뒤 다시 실행하면 새로 생긴 OCR 노드에도 한국어가 추가된다.

사용법(저장소 루트에서):
    git clone --depth 1 https://github.com/SusieGlitter/EndFieldTranslationReferrer.git <tmp>
    python tools/i18n/append_kr_expected.py --i18n-dir <tmp>/i18n          # 미리보기
    python tools/i18n/append_kr_expected.py --i18n-dir <tmp>/i18n --write  # 실제 반영
    pnpm prettier --write <변경된 파일>
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_ocr_expected as s

HANGUL = re.compile(r"[가-힣]")


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
            node_members, _ = parser.parse_object_members(node_member.value_start)
            node_map = s.member_map(node_members)
            is_ocr = False
            expected_member = None
            rec = node_map.get("recognition")
            if rec:
                if s.get_string_value(parser, rec) == "OCR":
                    is_ocr = True
                else:
                    rec_members = s.get_object_members(parser, rec)
                    if rec_members is not None:
                        rec_map = s.member_map(rec_members)
                        type_member = rec_map.get("type")
                        if type_member and s.get_string_value(parser, type_member) == "OCR":
                            is_ocr = True
                        param = rec_map.get("param")
                        if param:
                            param_members = s.get_object_members(parser, param)
                            if param_members is not None:
                                expected_member = s.get_array_member_if_exists(
                                    parser, s.member_map(param_members), "expected"
                                )
                        if expected_member is None:
                            expected_member = s.get_array_member_if_exists(parser, rec_map, "expected")
            if expected_member is None:
                expected_member = s.get_array_member_if_exists(parser, node_map, "expected")
            if not (is_ocr and expected_member):
                continue
            if s.has_i18n_skip_marker(text, expected_member):
                continue

            total_nodes += 1
            label = f"{path.relative_to(repo_root)}::{node_member.key}"
            old_expected, _ = parser.parse_array_string_values(expected_member.value_start)
            lang_ids, _ = s.resolve_lang_ids(old_expected, reverse_index, english_reverse_index, tables)
            if not lang_ids:
                unresolved.append(label)
                continue

            # 언어표의 한국어 원문과 정확히 같은 리터럴만 공백 보정한다
            # (이미 정규식으로 작성된 한국어 값은 그대로 둔다)
            kr_literals = {s.normalize_text(tables["KR"][lang_id]) for lang_id in lang_ids if tables["KR"].get(lang_id)}
            new_expected: list[str] = []
            for value in old_expected:
                if HANGUL.search(value) and " " in s.normalize_text(value) and s.normalize_text(value) in kr_literals:
                    value_regex = s.build_korean_ocr_regex(value)
                    if value_regex != value:
                        regexified += 1
                        value = value_regex
                # 기존 항목은 순서·중복까지 그대로 유지한다
                new_expected.append(value)

            kr_values: list[str] = []
            for lang_id in lang_ids:
                kr_text = tables["KR"].get(lang_id, "")
                if kr_text:
                    kr_values.append(s.build_korean_ocr_regex(kr_text))
            if not kr_values:
                no_kr_in_table.append(label)

            appended = 0
            for kr_value in kr_values:
                if kr_value not in new_expected:
                    new_expected.append(kr_value)
                    appended += 1
            added_strings += appended
            if appended:
                added_nodes += 1

            if new_expected == old_expected:
                continue

            raw_array = text[expected_member.value_start : expected_member.value_end]
            if "//" in raw_array or "/*" in raw_array:
                comment_arrays.append(label)
                continue

            key_indent = s.detect_line_indent(text, expected_member.key_start)
            replacements.append(
                (
                    expected_member.value_start,
                    expected_member.value_end,
                    s.build_expected_array_text(new_expected, key_indent, newline),
                )
            )

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
