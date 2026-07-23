
# KBO 감독 시즌 시뮬레이터 v5

## 핵심 수정

1. 규정타석/규정이닝 미달 선수는 2025년 데이터를 참고하도록 설계했습니다.
2. 선발 라인업은 이제 단순 능력치 TOP 9가 아니라 포지션별로 구성합니다.
   - 포수 1명
   - 내야수 4명
   - 외야수 3명
   - 지명타자 1명
3. 대타·수비 교체 시에도 해당 수비 슬롯에 맞는 등록 포지션만 기본 허용합니다.
   - C: 포수만
   - 1B/2B/SS/3B: 내야수만
   - LF/CF/RF: 외야수만
   - DH: 모든 야수 가능
4. 선수 파일은 `players_2026_2025_weighted_ratings.csv`를 사용합니다.

## 주의

포지션은 KBO 등록 현황의 큰 분류인 포수/내야수/외야수를 사용합니다.
실제 1루수·2루수·유격수·3루수 또는 좌익수·중견수·우익수 세부 포지션은
공식 등록 현황만으로는 완전히 분리되지 않기 때문에, 앱 내부에서 슬롯을 배정합니다.

## 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 능력치 파일

`players_2026_2025_weighted_ratings.csv`

중요 열:

- `contact`: 컨택
- `power`: 파워
- `discipline`: 선구안
- `speed`: 주력
- `stuff`: 구위
- `control`: 제구
- `stamina`: 체력
- `source_year_used`: 2026 / 2025 / 2026+2025 / missing
- `rating_source`: 어떤 방식으로 능력치를 만들었는지
- `sample_note`: 설명

## 완전 자동 재계산

공식/야구나라/MyKBO 등에서 받은 시즌 기록 CSV를 다음 이름으로 넣으면
능력치를 다시 만들 수 있습니다.

- `hitter_stats_2026.csv`
- `hitter_stats_2025.csv`
- `pitcher_stats_2026.csv`
- `pitcher_stats_2025.csv`

그 뒤 실행:

```bash
python build_player_ratings.py
```

출력:

```text
players_2026_2025_weighted_ratings.csv
```

## 일정

`새 시즌 시작` 시 `schedule_2026_fixed.csv`를 기본으로 읽습니다.
우천 취소/연기/재편성은 반영하지 않고, 개막 전 발표된 정규시즌 편성표 기준으로 고정 진행하는 용도입니다.
