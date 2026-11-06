# 한국어 포크 업스트림 동기화 절차

원본 `MaaEnd/MaaEnd` 의 `v2` 변경을 포크 `nyaaso/MaaEnd` 에 합치고, 한국어 리소스를 다시 적용한 뒤
빌드해서 사용자 PC(`L:\MaaEnd-win-x86_64`)에 배포하는 절차입니다.

## 원칙

- 작업 브랜치는 `feat/kr-resource`, 배포 브랜치는 포크의 `v2` 입니다(`feat/kr-resource` 를 그대로 `v2` 로 푸시).
- 원본 로직(특히 UID 숨김 MOD 검사 `__SceneImageCheckMod`)은 바꾸지 않습니다. 충돌은 원본 동작을 기준으로 하고 한국어 문구만 살립니다.
- 포크에서 따로 고친 동작은 원본이 같은 곳을 고쳤으면 원본 쪽을 우선하고, 아니면 유지합니다.
  - `Interface/InScene/VisitFriends.json` InFriendsList 두 번째 템플릿(`OnFriendListIcon.png`)
  - `EnvironmentMonitoring/Locations.json` 관측 단말기 탭 Retry/NotSelected 노드
  - `GiftOperator/GiftOperatorNavigation.json` 방향 전환 4개 추가(동북/남/남서/북), `GiftOperatorMain.json` ClearHitCount 목록
  - `SceneManager/SceneMenu.json` 메뉴 닫기 버튼 템플릿 판정, `EnvironmentMonitoring/.../AncientTree.json` 「[웅움]덩이」
  - `VisitFriends/MenuScan.json` 방문한 친구 key 를 `#UID`(4자리)로 저장하고 `match_anywhere` 로 제외(`agent/go-service/common/expendable` 의 `match_anywhere` 옵션)
- UI 한국어 문구는 2026-11-06 전체 다듬기 기준(켜면/끄면, 작업/임무 구분, 「」/' ' 따옴표, 스탯·의뢰 수락·빠른 전송·실시간 어시스트·불러오기 용어)을 따릅니다.
- 한국어 용어 기준: 관리권, 집라인, 4번 협곡, 응접실, 재배실, 선검 연무, 궁극기, 배틀 스킬, 가방, 변동 수요 물자, 배송, 증정, 엔드필드, 기질, 이성, ~하세요 체.

## 준비

```bash
git clone https://github.com/nyaaso/MaaEnd.git maaend && cd maaend
git checkout feat/kr-resource
git submodule update --init --recursive
git remote add upstream https://github.com/MaaEnd/MaaEnd.git
# 게임 언어표(CN/TC/EN/JP/KR + HotFix)만 받기
git clone --depth 1 --filter=blob:none --sparse https://github.com/SusieGlitter/EndFieldTranslationReferrer.git ../eftr
(cd ../eftr && git sparse-checkout set --no-cone /i18n/I18nTextTable_CN.json /i18n/I18nTextTable_TC.json \
  /i18n/I18nTextTable_EN.json /i18n/I18nTextTable_JP.json /i18n/I18nTextTable_KR.json /i18n/I18nHotFix.json)
pnpm install
```

## 1. 병합

```bash
tools/i18n/kr_upstream_sync.sh merge
```

- `STATUS=NO_UPDATE`: 할 일 없음. 다만 PC 설치본 버전이 포크 `v2` 와 다르면 4단계(배포)만 진행합니다.
- `STATUS=CONFLICT`: 남은 충돌 파일을 직접 해결합니다.
  - 파이프라인 JSON: 원본 쪽 구조/동작을 따르고, 우리 쪽에서 추가했던 한국어 expected 항목만 다시 넣습니다(2단계에서 대부분 자동 복구됨).
  - 그 밖의 파일: 원본 쪽을 따릅니다. 위 「포크에서 따로 고친 동작」에 해당하면 의도를 살려 합칩니다.
  - 해결 후 `git add`.
- `STATUS=READY`: 다음 단계로.
- 로케일 보고서(`$TMPDIR/kr_sync/locale_report.json`)의 `manual`(양쪽 모두 바뀐 키, 일단 원본 채택), `new_keys`, `theirs_changed_keys` 문구를 위 용어 기준으로 다듬습니다.

## 2. 한국어 재적용과 점검

```bash
tools/i18n/kr_upstream_sync.sh apply ../eftr/i18n
```

- `append_kr_expected.py`: 언어표로 새 OCR 노드에 한국어 expected 추가, 한국어 항목 공백을 `\s*` 로 보정
- `gen_kr_focus.py`: 중국어로 직접 적힌 focus 를 `resource_kr/pipeline/Focus` 에 한국어로 덮어씀
  - 「번역 누락」이 나오면 `tools/i18n/kr_focus_translations.json` 에 번역을 추가하고 다시 실행
- `audit_kr_expected.py`: 한국어가 없거나 일부 빠진 OCR 노드 보고
  - 게임 한국어 원문(언어표 KR)에 맞춰 expected 에 직접 추가. 의도적 제외면 `IGNORE` 에 등록
- prettier, 스키마 검증, `pnpm check`, (Go 변경 시) `go build`/`go vet` 까지 통과해야 `STATUS=OK`

## 3. 커밋과 푸시

```bash
git commit   # 메시지: merge: upstream/v2 병합 및 한국어 리소스 재적용 (+ 바뀐 내용 요약)
git push origin feat/kr-resource
git push origin feat/kr-resource:v2
```

포크 GitHub Actions(`install`)가 v2 푸시로 빌드를 시작합니다. 정해진 시간마다 도는 워크플로는 꺼 두었습니다(포크 비활성화 방지).

## 4. 배포 (사용자 PC)

1. `install` 실행의 `build_and_install (win, x86_64)` 작업이 끝나면 아티팩트 `MaaEnd-win-x86_64-zip`(없으면 `MaaEnd-win-x86_64-intermediate`)를 받습니다.
   - macOS 러너 부족으로 zip 포장 단계가 건너뛰어질 수 있습니다. 이때는 intermediate 를 쓰고 `agent/cpp-algo.pdb` 는 지웁니다.
   - CI 가 실패했고 `agent/cpp-algo` 변경이 없으면 `uv run -m tools.setup.build_and_install --ci --os win --arch x86_64 --version <ver>` →
     `uv run tools/merge_pipeline.py install` → `uv run tools/fill_interface.py --version <ver> --interface install/interface.json` 로 직접 빌드해도 됩니다
     (이 경우 `maafw`, `MaaEnd.exe`, OCR 기본 모델은 PC 기존 파일을 그대로 씁니다).
2. PC 에서 MaaEnd(`MaaEnd.exe`, `go-service`, `cpp-algo`)가 실행 중이면 배포하지 않고 다음 기회로 미룹니다.
3. `L:\MaaEnd-win-x86_64\config` 를 `L:\MaaEnd-config-backup-<시각>` 으로 백업합니다.
4. 압축을 임시 폴더에 풀고 `robocopy <임시> L:\MaaEnd-win-x86_64 /E /XD config debug cache` 로 덮어씁니다(삭제 없음).
5. 복사한 파일 해시가 모두 같은지, `interface.json` 의 `version` 이 새 버전인지 확인하고 임시 파일을 지웁니다.
