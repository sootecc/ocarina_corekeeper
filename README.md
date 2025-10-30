
# Core Keeper 오카리나 자동 연주 스크립트

## 폴더
`/mnt/data/core_keeper_ocarina`

## 파일
- `ocarina_player.py` — 실행 스크립트
- `mapping.json` — 노트(C4~C5) → 키보드 키(예: 숫자 1~8) 매핑
- `song.txt` — 예시 악보 (간단한 토큰 형식)

## 설치
1) Python 3.10+ 설치
2) 커맨드라인에서:
```
pip install pyautogui
```
- macOS의 경우 "손쉬운 사용(입력 제어)" 권한을 터미널/IDE에 허용해야 합니다.
- Windows에서는 관리자 권한이 필요할 수 있습니다.

## 사용법
1) `mapping.json`을 실제 게임 내 오카리나 키에 맞게 수정하세요. (예: 숫자키 1~8, 혹은 QWERTY 등)
2) `song.txt` 첫 줄의 BPM을 조정하고, 아래와 같은 형식으로 음표를 적습니다.
   - 토큰: `NOTE:DEN` (예: `C4:4` = 4분음표, `E4:8` = 8분음표)
   - 쉼표: `R:DEN`
   - 마디 구분은 `|` 기호(선택사항)
3) 게임을 실행하고 오카리나를 장착/연주 가능한 상태로 둡니다.
4) 터미널에서:
```
python ocarina_player.py --song song.txt --map mapping.json --countdown 4
```
5) 카운트다운 동안 게임 창으로 전환하면 자동으로 연주됩니다. (중지: 콘솔에서 Ctrl+C)

## 주의
- 멀티플레이/공용 서버에서는 매크로로 간주될 수 있습니다. 서버 규칙과 게임 약관을 준수하세요.
- 이 스크립트는 교육/개인 사용을 위한 예제입니다.

## 확장 매핑 사용법 (이미지 레이아웃 대응)
`mapping_extended.json`은 아래 키들을 저음→고음 순의 **예시**로 매핑했습니다:

Z X C V B N M | S D G H J | Q W E R T Y U | 2 3 5 6 7  (총 24키)

노트 범위: C4 ~ B5 (반음 포함, C#, D#, F#, G#, A#).  
원하는 키 순서/음역으로 자유롭게 바꾸세요.

### 샤프/플랫 표기
- 샤프: `C#4`
- 플랫: `Db4`처럼 적어도 자동으로 `C#4`로 인식합니다.

### 트랜스포즈
악보 음역이 매핑과 안 맞으면 반음 단위로 이동:
```
python ocarina_player.py --transpose 2
```


---
## 새 악보 형식 (2옥타브 + 박자 헬퍼)
헤더:
- `BPM=120` (또는 `TEMPO=120`): 템포
- `UNIT=8`: 기본 음표 길이(8분음표). 표기 생략 시 이 단위를 사용

바디(토큰):
- `LOW:` / `HIGH:` 로 현재 옥타브 레인을 전환 (LOW=C4~B4, HIGH=C5~B5)
- 음표: `C`, `F#`, `Db`, `R`(쉼). 옥타브 숫자를 붙이면 강제: `C5`
- 길이: `:4`, `:8+16` (합산), 점음표는 `.`(하나당 ×1.5) 예: `C:4.`, `G:16..`
- 마디 구분은 `|` (선택)
- 어디서든 `TEMPO=xxx`, `UNIT=xx`로 변경 가능

예시:
```
BPM=118
UNIT=8
LOW:  C D E F# | G A B C.
HIGH: C D E F# | G:4 R:8 G:16. A:16 B:8
TEMPO=140
LOW:  E D C R:8 C:8
```

---
## 화음/홀드/스트럼/반복/모드 표기
- 화음: `C+E+G:4` (노트 사이 `+`)
- 길이: `:4`, `:8+16`, 점음표 `.`
- 속성(괄호): `(h0.15,st0.01,rep3,mode=sim)`
  - `h` = hold(초), `st` = chord stagger/strum, `rep` = 반복 횟수, `mode` = `sim`(동시에 눌러 연주) / `strum`(기본, 순차로 눌러 아르페지오 느낌)
- 헤더 기본값: `HOLD=0.12`, `STAGGER=0.008`, `REP=1`, `MODE=STRUM` (본문 어디서나 변경 가능)
- 헤더/속성에서 `MODE=SIM` 또는 `(sim)`을 지정하면 해당 구간 화음이 완전 동시 입력으로 연주됩니다.

예시:
```
BPM=96
UNIT=8
HOLD=0.12
STAGGER=0.010
MODE=SIM
LOW: C+E+G:4
LOW: G+B+D:8(rep3)
```

---
## 기존 악보(PDF/이미지) → 스크립트 변환 안내
1. **이미지/PDF → MusicXML**
   - 프로젝트에는 OMR 엔진이 포함되어 있지 않습니다. 따라서 PDF/이미지를 바로 변환하려면 별도의 OMR 도구가 필요합니다.
   - **오픈소스 Audiveris**: [공식 저장소](https://github.com/Audiveris/audiveris)의 릴리스를 직접 설치하거나 Docker가 있다면 다음처럼 실행할 수 있습니다.
     ```bash
     docker run --rm -v "$PWD:/scores" audiveris/audiveris \
       -batch -export -output /scores/out /scores/input_score.pdf
     ```
     위 명령은 `out/` 폴더에 MusicXML(`.mxl`)을 생성합니다. JDK 설치가 가능하다면 저장소를 클론한 뒤 `./gradlew installDist`로 CLI를 직접 빌드할 수도 있습니다.
   - **대체 도구**: MuseScore 4(파일 → PDF 가져오기), ScanScore, PlayScore 2, NotateMe 등 상용/체험판 OMR도 MusicXML/MIDI로 내보낼 수 있습니다. 이런 프로그램으로 PDF/이미지를 MusicXML이나 MIDI로 저장한 뒤 다음 단계를 진행하세요.
   - **수동 입력**: 짧은 악보라면 MuseScore, Flat.io 같은 편집기에 직접 입력한 뒤 MusicXML로 내보내는 방법이 가장 확실합니다.
2. **MusicXML/MIDI → 스크립트**: `music21` 패키지를 설치한 뒤 변환 스크립트를 사용하세요. (`musicxml_to_song.py`는 MusicXML, MIDI, MuseScore(`.mscz`) 등 `music21`이 읽을 수 있는 포맷이면 그대로 처리합니다.)

```bash
pip install music21
python musicxml_to_song.py input_score.musicxml output_song.txt
```

- 스크립트와 같은 폴더에 있는 `mapping.json`을 기본으로 읽어 자동으로 반음 이동(Transpose)을 적용합니다. (직접 다른 매핑을 쓰려면 `--map 다른매핑.json`)
- 원본 음역을 그대로 확인하고 싶다면 `--no-map` 옵션을 주면 됩니다. (이 경우 옥타브 조정/자동 transpose가 비활성화)
- 특정 음역으로 강제 이동하고 싶다면 `--transpose -12`처럼 직접 지정할 수도 있습니다.
- 변환기는 모든 음을 샤프 표기(`D#4`)로 정규화하므로 기본 매핑 예시와 바로 호환됩니다.
- 매핑 범위를 넘어가는 음은 자동으로 옥타브를 올리거나 내려서(12음 단위) 맞춰 줍니다. 이때 조정된 음 개수는 변환 결과에 표시되므로, 필요하면 OMR 결과를 손으로 정리해 주세요.

변환된 `output_song.txt`는 `ocarina_player.py --song output_song.txt`로 바로 연주할 수 있습니다. (필요하면 매핑/옥타브 등을 추가로 조정하세요.)
