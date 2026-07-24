# KBO 시즌 시뮬레이터 v7 — 현재 시즌 원자료 우선 버전

## 핵심 변경

이 버전의 능력치 계산은 규정타석/규정이닝을 기준으로 선수 데이터를 버리지 않습니다.

1. 2026 기록이 있으면 1타석, 1경기, 1/3이닝이라도 2026 스탯 그대로 능력치 식에 넣습니다.
2. 2026 기록이 아예 없을 때만 2025 기록을 사용합니다.
3. 평균회귀, 표본 보정, 규정타석/규정이닝 컷을 적용하지 않습니다.
4. 실제 기록 행이 없으면 `rating_is_actual=False`로 표시하고 `missing_raw_current_stats_report.csv`에 따로 저장합니다.

## 주요 파일

- `app.py`: Streamlit 앱
- `players_2026_raw_current_positions.csv`: 앱이 가장 먼저 읽는 선수 능력치 파일
- `build_player_ratings_raw_current.py`: 원자료 기반 능력치 재계산 스크립트
- `hitter_stats_template.csv`: 타자 기록 CSV 형식
- `pitcher_stats_template.csv`: 투수 기록 CSV 형식
- `schedule_2026_fixed.csv`: 시즌 시작 당시 고정 일정

## 실제 전체 스탯을 반영하는 방법

Yagoonara 또는 KBO에서 2026/2025 타자·투수 전체 선수 CSV를 내려받아 아래 이름으로 저장합니다.

```text
hitter_stats_2026.csv
pitcher_stats_2026.csv
hitter_stats_2025.csv
pitcher_stats_2025.csv
```

그 다음 실행합니다.

```bash
python build_player_ratings_raw_current.py
```

그러면 `players_2026_raw_current_positions.csv`가 다시 생성되고, 앱은 이 파일을 자동으로 먼저 읽습니다.

## 능력치 식

### 타자

- contact = 타율 백분위 70% + 삼진율 역백분위 30%
- power = 장타율 백분위 55% + ISO 백분위 30% + HR/PA 백분위 15%
- discipline = 출루율 백분위 70% + 볼넷률 백분위 30%
- speed = 도루 수 백분위 65% + 도루 성공률 백분위 35%

### 투수

- stuff = K/9 백분위 55% + 피안타율 역백분위 25% + ERA 역백분위 20%
- control = BB/9 역백분위 55% + WHIP 역백분위 45%
- stamina = 이닝 백분위 70% + 경기당 이닝 백분위 30%

## 배포 주의

GitHub 저장소 최상단에 최소한 아래 파일이 있어야 합니다.

```text
app.py
requirements.txt
schedule_2026_fixed.csv
players_2026_raw_current_positions.csv
```
