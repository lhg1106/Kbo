"""
KBO 선수 능력치 재계산 스크립트: 평균회귀 없음 버전.

입력 파일:
  - players_2026_07_23.csv              현재 로스터
  - hitter_stats_2026.csv, hitter_stats_2025.csv
  - pitcher_stats_2026.csv, pitcher_stats_2025.csv
  - player_positions_override.csv       실제 수비 위치(C/1B/2B/SS/3B/LF/CF/RF/DH/P)

원칙:
  1) 2026 기록이 있으면 2026 기록 사용
  2) 2026 기록이 없거나 거의 없으면 2025 기록 사용
  3) 둘 다 없으면 평균회귀를 하지 않고 rating_is_actual=False로 표시

출력:
  - players_actual_no_regression_positions.csv
  - missing_actual_stats_report.csv
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent


def read_csv_optional(filename: str) -> pd.DataFrame:
    path = ROOT / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def pct_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    ranks = values.rank(pct=True, ascending=not higher_is_better)
    return (20 + ranks.fillna(0) * 70).round().clip(20, 90)


def normalize_name(value: object) -> str:
    return str(value).strip().replace(" ", "")


def prepare_stats(df: pd.DataFrame, year: int, kind: str) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["name_key"] = df["name"].map(normalize_name)
    df["team"] = df["team"].astype(str)
    df["stat_year"] = year
    df["stat_kind"] = kind
    return df


def pick_stats_for_player(row: pd.Series, h26, h25, p26, p25):
    name_key = normalize_name(row["name"])
    team = str(row["team"])
    is_pitcher = str(row["role"]) == "pitcher"
    candidates = [(p26, 2026), (p25, 2025)] if is_pitcher else [(h26, 2026), (h25, 2025)]
    for df, year in candidates:
        if df.empty:
            continue
        # 팀 이적 가능성을 고려해 이름 우선, 같은 팀이면 더 우선
        hits = df[df["name_key"] == name_key].copy()
        if hits.empty:
            continue
        exact_team = hits[hits["team"] == team]
        selected = exact_team.iloc[0] if not exact_team.empty else hits.iloc[0]
        return selected, year
    return None, None


def apply_positions(players: pd.DataFrame) -> pd.DataFrame:
    override = read_csv_optional("player_positions_override.csv")
    players = players.copy()
    if not override.empty:
        override["name_key"] = override["name"].map(normalize_name)
        pos_map = override.set_index(["team", "name_key"])["eligible_positions"].to_dict()
    else:
        pos_map = {}

    primary, secondary, eligible, source = [], [], [], []
    for _, row in players.iterrows():
        key = (row["team"], normalize_name(row["name"]))
        value = pos_map.get(key)
        if not value:
            # 평균 능력치가 아니라 수비위치만 등록 대분류로 최소 변환합니다.
            broad = str(row.get("position", ""))
            if str(row.get("role", "")) == "pitcher" or broad == "투수":
                value = "P"
            elif broad == "포수":
                value = "C;DH"
            elif broad == "내야수":
                value = "1B;2B;SS;3B;DH"
            elif broad == "외야수":
                value = "LF;CF;RF;DH"
            else:
                value = "DH"
            source.append("registered_group_position_only")
        else:
            source.append("manual_or_namuwiki_position_override")
        parts = [x.strip() for x in str(value).replace(",", ";").split(";") if x.strip()]
        primary.append(parts[0] if parts else "")
        secondary.append(";".join(parts[1:]))
        eligible.append(";".join(parts))
    players["primary_position"] = primary
    players["secondary_positions"] = secondary
    players["eligible_positions"] = eligible
    players["position_source"] = source
    return players


def build() -> None:
    players = pd.read_csv(ROOT / "players_2026_07_23.csv")
    h26 = prepare_stats(read_csv_optional("hitter_stats_2026.csv"), 2026, "hitter")
    h25 = prepare_stats(read_csv_optional("hitter_stats_2025.csv"), 2025, "hitter")
    p26 = prepare_stats(read_csv_optional("pitcher_stats_2026.csv"), 2026, "pitcher")
    p25 = prepare_stats(read_csv_optional("pitcher_stats_2025.csv"), 2025, "pitcher")

    # percentile columns inside each stats table
    for df in [h26, h25]:
        if df.empty:
            continue
        for col in ["AVG", "OBP", "SLG", "OPS", "SB"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["contact_rating"] = pct_rank(df.get("AVG", 0), True)
        df["power_rating"] = pct_rank(df.get("SLG", df.get("OPS", 0)), True)
        df["discipline_rating"] = pct_rank(df.get("OBP", 0), True)
        df["speed_rating"] = pct_rank(df.get("SB", 0), True)
    for df in [p26, p25]:
        if df.empty:
            continue
        for col in ["ERA", "WHIP", "SO", "BB", "IP"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["stuff_rating"] = pct_rank(df.get("SO", 0), True)
        df["control_rating"] = (0.55 * pct_rank(df.get("WHIP", 0), False) + 0.45 * pct_rank(df.get("BB", 0), False)).round().clip(20, 90)
        df["stamina_rating"] = pct_rank(df.get("IP", 0), True)

    rows = []
    for _, row in players.iterrows():
        out = row.to_dict()
        stat, year = pick_stats_for_player(row, h26, h25, p26, p25)
        if stat is None:
            out.update({
                "rating_is_actual": False,
                "source_year_used": "missing",
                "rating_source": "actual_stats_missing_no_regression",
                "contact": 0, "power": 0, "discipline": 0, "speed": 0,
                "stuff": 0, "control": 0, "stamina": 0,
            })
        elif str(row["role"]) == "pitcher":
            out.update({
                "rating_is_actual": True,
                "source_year_used": year,
                "rating_source": f"{year}_actual_pitcher_stats_no_regression",
                "contact": 0, "power": 0, "discipline": 0, "speed": 0,
                "stuff": int(stat["stuff_rating"]),
                "control": int(stat["control_rating"]),
                "stamina": int(stat["stamina_rating"]),
            })
        else:
            out.update({
                "rating_is_actual": True,
                "source_year_used": year,
                "rating_source": f"{year}_actual_hitter_stats_no_regression",
                "contact": int(stat["contact_rating"]),
                "power": int(stat["power_rating"]),
                "discipline": int(stat["discipline_rating"]),
                "speed": int(stat["speed_rating"]),
                "stuff": 0, "control": 0, "stamina": 0,
            })
        rows.append(out)

    output = apply_positions(pd.DataFrame(rows))
    output.to_csv(ROOT / "players_actual_no_regression_positions.csv", index=False, encoding="utf-8-sig")
    output[~output["rating_is_actual"]].to_csv(ROOT / "missing_actual_stats_report.csv", index=False, encoding="utf-8-sig")
    print("created players_actual_no_regression_positions.csv")
    print("actual ratings:", int(output["rating_is_actual"].sum()), "/", len(output))


if __name__ == "__main__":
    build()
