# KBO 시즌 시뮬레이터 v8 — 직접 스탯 산출판

## 이번 수정의 핵심

- 규정타석/규정이닝 조건을 사용하지 않습니다.
- 2026년에 1타석 또는 1/3이닝이라도 기록이 있으면 2026 기록을 그대로 사용합니다.
- 2025 기록은 2026 기록이 아예 없는 선수에게만 사용합니다.
- 표본 수에 따른 평균회귀, 출전량 가중치, 임의 50점 보정을 하지 않습니다.
- 실제 기록이 없는 선수는 결측으로 남기고 매칭 리포트에 표시합니다.
- 실제 수비 위치 정보는 `roster_positions_2026.csv`에서 유지합니다.
- 완성 파일 이름은 `players_2026_direct_stats_positions.csv`입니다.

## 필요한 전체 기록 CSV

다음 4개 파일을 같은 폴더에 넣습니다.

- `hitter_stats_2026.csv`
- `pitcher_stats_2026.csv`
- `hitter_stats_2025.csv`
- `pitcher_stats_2025.csv`

2026 파일은 필수이고, 2025 파일은 2026 미출전 선수 보충용입니다.

## 터미널에서 생성

```bash
pip install -r requirements.txt
python build_player_ratings_direct.py
```

## 브라우저에서 생성

```bash
streamlit run stats_builder_app.py
```

화면에서 전체 기록 CSV를 업로드하면 완성 선수 파일과 매칭 리포트를 받을 수 있습니다.

## 능력치 계산

### 타자

- 콘택트: 타율 70% + 삼진율 억제 30%
- 파워: 장타율 45% + ISO 35% + 홈런/타석 20%
- 선구안: 출루율 65% + 볼넷률 35%
- 주력: 도루 수 65% + 도루 성공률 35%

### 투수

- 구위: K/9 42% + H/9 억제 25% + ERA 억제 20% + HR/9 억제 13%
- 제구: BB/9 억제 58% + WHIP 억제 42%
- 체력: 경기당 이닝 70% + 총이닝 30%

각 항목은 실제 2026 기록의 리그 내 백분위를 20~80 점수로 변환합니다.
규정타석·규정이닝이나 표본 크기는 점수 계산에 사용하지 않습니다.

## Streamlit 게임 실행

완성된 `players_2026_direct_stats_positions.csv`를 GitHub 최상단에 올린 뒤:

```bash
streamlit run app.py
```

## 주의

이 패키지는 실제값을 임의로 만들어 넣지 않습니다. 입력한 전체 기록 CSV에서 선수 이름이
매칭되지 않으면 그 선수는 `direct_stats_build_report.csv`에 누락으로 표시됩니다.
