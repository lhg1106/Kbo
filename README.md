# KBO 감독 시즌 시뮬레이터 v6

수정 내용:

- 루 상황을 그래픽 다이아몬드로 표시
- 라인업 자동 선발을 `C, 1B, 2B, SS, 3B, LF, CF, RF, DH` 슬롯 기준으로 변경
- `내야수/외야수` 대분류 대신 `eligible_positions` 열의 실제 수비 위치를 사용
- 평균회귀로 만든 능력치를 실제 기록처럼 취급하지 않도록 `rating_is_actual` 열 추가
- 선수 CSV가 없어도 앱이 터지지 않도록 fallback 유지

## 핵심 파일

- `app.py`: Streamlit 앱
- `schedule_2026_fixed.csv`: 고정 일정
- `players_actual_no_regression_positions.csv`: 현재 앱이 우선 읽는 선수 파일
- `missing_actual_stats_report.csv`: 2026/2025 실제 세부 기록이 아직 없는 선수 목록
- `build_player_ratings_no_regression.py`: 평균회귀 없이 실제 기록 CSV로 능력치 재계산

## 실제 수비 위치

앱은 다음 열을 사용합니다.

```csv
primary_position,secondary_positions,eligible_positions
SS,2B;3B,SS;2B;3B;DH
```

포지션 코드는 `P, C, 1B, 2B, SS, 3B, LF, CF, RF, DH`만 사용합니다.

## 평균회귀 없음 원칙

이 버전은 실제 기록이 없는데 평균 능력치인 것처럼 숨기지 않습니다.

- `rating_is_actual=True`: 2026 또는 2025 실제 기록 기반
- `rating_is_actual=False`: 실제 세부 기록이 없어서 확인 필요

전체 300명을 전부 실제 수치로 채우려면 `hitter_stats_2026.csv`, `hitter_stats_2025.csv`, `pitcher_stats_2026.csv`, `pitcher_stats_2025.csv`를 넣고 아래를 실행하세요.

```bash
python build_player_ratings_no_regression.py
```

## 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```
