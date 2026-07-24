"""
KBO 선수 능력치 재계산 스크립트 v7: 현재 시즌 원자료 우선, 규정 컷 없음.

입력 파일:
  - players_2026_07_23.csv
  - hitter_stats_2026.csv, pitcher_stats_2026.csv
  - hitter_stats_2025.csv, pitcher_stats_2025.csv
  - player_positions_override.csv (선택)

원칙:
  1) 2026 기록이 한 타석/한 타자 상대/0.1이닝이라도 있으면 2026 원자료 그대로 사용
  2) 2026 기록이 아예 없을 때만 2025 기록 사용
  3) 규정타석/규정이닝 기준, 평균회귀, 표본 보정 없음
  4) 실제 기록이 아예 없으면 rating_is_actual=False로 표시하고 누락 리포트에 저장

출력:
  - players_2026_raw_current_positions.csv
  - missing_raw_current_stats_report.csv
"""
from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

ROOT = Path(__file__).resolve().parent

TEAM_ALIASES = {
    "KIA": "KIA 타이거즈", "Kia": "KIA 타이거즈", "KIA Tigers": "KIA 타이거즈",
    "Samsung": "삼성 라이온즈", "SAMSUNG": "삼성 라이온즈", "삼성": "삼성 라이온즈",
    "LG": "LG 트윈스", "LG Twins": "LG 트윈스",
    "Doosan": "두산 베어스", "DOOSAN": "두산 베어스", "두산": "두산 베어스",
    "KT": "KT 위즈", "kt": "KT 위즈", "KT Wiz": "KT 위즈",
    "SSG": "SSG 랜더스", "SSG Landers": "SSG 랜더스",
    "Lotte": "롯데 자이언츠", "LOTTE": "롯데 자이언츠", "롯데": "롯데 자이언츠",
    "Hanwha": "한화 이글스", "HANWHA": "한화 이글스", "한화": "한화 이글스",
    "NC": "NC 다이노스", "NC Dinos": "NC 다이노스",
    "Kiwoom": "키움 히어로즈", "KIWOOM": "키움 히어로즈", "키움": "키움 히어로즈",
}


def read_csv_optional(filename: str) -> pd.DataFrame:
    path = ROOT / filename
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def normalize_name(value: object) -> str:
    text = str(value).strip()
    # 등번호/괄호 구분은 매칭 시 제거: 김태훈(25) -> 김태훈
    text = re.sub(r"\([^)]*\)", "", text)
    return text.replace(" ", "").upper()


def normalize_team(value: object) -> str:
    text = str(value).strip()
    return TEAM_ALIASES.get(text, text)


def to_number(series: pd.Series | object, default=0.0) -> pd.Series:
    if isinstance(series, pd.Series):
        return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(default)
    return pd.Series(dtype=float)


def parse_ip(value: object) -> float:
    """KBO 표기 5 1/3, 2/3, 7.1 등을 실제 이닝 수로 변환."""
    if pd.isna(value):
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if " " in text and "/" in text:
        whole, frac = text.split(" ", 1)
        num, den = frac.split("/", 1)
        return float(whole) + float(num) / float(den)
    if "/" in text:
        num, den = text.split("/", 1)
        return float(num) / float(den)
    if "." in text:
        # 야구식 7.1 = 7과 1/3, 7.2 = 7과 2/3
        whole, frac = text.split(".", 1)
        if frac in {"1", "2"}:
            return float(whole) + int(frac) / 3
    try:
        return float(text)
    except ValueError:
        return 0.0


def pct_rating(values: pd.Series, higher_is_better: bool = True, floor=20, ceiling=90) -> pd.Series:
    v = pd.to_numeric(values, errors="coerce")
    if v.notna().sum() == 0:
        return pd.Series([50] * len(v), index=v.index)
    rank = v.rank(pct=True, ascending=not higher_is_better, method="average")
    return (floor + rank.fillna(0.5) * (ceiling - floor)).round().clip(floor, ceiling)


def first_existing(df: pd.DataFrame, names: list[str], default=0.0) -> pd.Series:
    for name in names:
        if name in df.columns:
            return to_number(df[name], default)
    return pd.Series([default] * len(df), index=df.index)


def prepare_hitter_stats(df: pd.DataFrame, year: int) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df["name_key"] = df["name"].map(normalize_name) if "name" in df.columns else df["PLAYER"].map(normalize_name)
    team_col = "team" if "team" in df.columns else "TEAM"
    df["team"] = df[team_col].map(normalize_team)
    df["stat_year"] = year

    df["PA"] = first_existing(df, ["PA", "타석"], 0)
    df["AB"] = first_existing(df, ["AB", "타수"], 0)
    df["H"] = first_existing(df, ["H", "안타"], 0)
    df["HR"] = first_existing(df, ["HR", "홈런"], 0)
    df["BB"] = first_existing(df, ["BB", "볼넷"], 0)
    df["SO"] = first_existing(df, ["SO", "K", "삼진"], 0)
    df["SB"] = first_existing(df, ["SB", "도루"], 0)
    df["CS"] = first_existing(df, ["CS", "도실"], 0)
    df["AVG"] = first_existing(df, ["AVG", "타율"], 0)
    df["OBP"] = first_existing(df, ["OBP", "출루율"], 0)
    df["SLG"] = first_existing(df, ["SLG", "장타율"], 0)
    df["OPS"] = first_existing(df, ["OPS"], df["OBP"] + df["SLG"])

    pa = df["PA"].replace(0, pd.NA)
    ab = df["AB"].replace(0, pd.NA)
    sb_attempts = (df["SB"] + df["CS"]).replace(0, pd.NA)

    df["k_rate"] = (df["SO"] / pa).fillna(0)
    df["bb_rate"] = (df["BB"] / pa).fillna(0)
    df["hr_rate"] = (df["HR"] / pa).fillna(0)
    df["iso"] = (df["SLG"] - df["AVG"]).fillna(0)
    df["sb_success"] = (df["SB"] / sb_attempts).fillna(0)

    contact = 0.70 * pct_rating(df["AVG"], True) + 0.30 * pct_rating(df["k_rate"], False)
    power = 0.55 * pct_rating(df["SLG"], True) + 0.30 * pct_rating(df["iso"], True) + 0.15 * pct_rating(df["hr_rate"], True)
    discipline = 0.70 * pct_rating(df["OBP"], True) + 0.30 * pct_rating(df["bb_rate"], True)
    speed = 0.65 * pct_rating(df["SB"], True) + 0.35 * pct_rating(df["sb_success"], True)

    df["contact_rating"] = contact.round().clip(20, 90)
    df["power_rating"] = power.round().clip(20, 90)
    df["discipline_rating"] = discipline.round().clip(20, 90)
    df["speed_rating"] = speed.round().clip(20, 90)
    return df


def prepare_pitcher_stats(df: pd.DataFrame, year: int) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df["name_key"] = df["name"].map(normalize_name) if "name" in df.columns else df["PLAYER"].map(normalize_name)
    team_col = "team" if "team" in df.columns else "TEAM"
    df["team"] = df[team_col].map(normalize_team)
    df["stat_year"] = year

    df["G"] = first_existing(df, ["G", "경기"], 0)
    df["GS"] = first_existing(df, ["GS", "선발"], 0)
    if "IP" in df.columns:
        df["IP"] = df["IP"].map(parse_ip)
    elif "이닝" in df.columns:
        df["IP"] = df["이닝"].map(parse_ip)
    else:
        df["IP"] = 0.0
    df["H"] = first_existing(df, ["H", "피안타"], 0)
    df["BB"] = first_existing(df, ["BB", "볼넷"], 0)
    df["SO"] = first_existing(df, ["SO", "K", "삼진"], 0)
    df["ERA"] = first_existing(df, ["ERA", "평균자책점"], 99)
    df["WHIP"] = first_existing(df, ["WHIP"], 99)
    df["AVG"] = first_existing(df, ["AVG", "피안타율"], 0.350)

    ip = df["IP"].replace(0, pd.NA)
    g = df["G"].replace(0, pd.NA)
    df["k9"] = (df["SO"] * 9 / ip).fillna(0)
    df["bb9"] = (df["BB"] * 9 / ip).fillna(99)
    df["ip_per_g"] = (df["IP"] / g).fillna(0)

    stuff = 0.55 * pct_rating(df["k9"], True) + 0.25 * pct_rating(df["AVG"], False) + 0.20 * pct_rating(df["ERA"], False)
    control = 0.55 * pct_rating(df["bb9"], False) + 0.45 * pct_rating(df["WHIP"], False)
    stamina = 0.70 * pct_rating(df["IP"], True) + 0.30 * pct_rating(df["ip_per_g"], True)

    df["stuff_rating"] = stuff.round().clip(20, 90)
    df["control_rating"] = control.round().clip(20, 90)
    df["stamina_rating"] = stamina.round().clip(20, 90)
    return df


def pick_stats(row: pd.Series, h26, h25, p26, p25):
    name_key = normalize_name(row["name"])
    team = normalize_team(row["team"])
    role = str(row["role"])
    candidates = [(p26, 2026, "pitcher")] if role == "pitcher" else [(h26, 2026, "hitter")]
    candidates += [(p25, 2025, "pitcher")] if role == "pitcher" else [(h25, 2025, "hitter")]

    for df, year, kind in candidates:
        if df.empty:
            continue
        hits = df[df["name_key"] == name_key].copy()
        if hits.empty:
            continue
        # 2026은 규정 이닝/타석과 무관하게 기록이 있으면 무조건 사용.
        if kind == "hitter":
            hits = hits[hits["PA"] > 0]
        else:
            hits = hits[(hits["IP"] > 0) | (hits["G"] > 0)]
        if hits.empty:
            continue
        exact_team = hits[hits["team"] == team]
        selected = exact_team.iloc[0] if not exact_team.empty else hits.iloc[0]
        return selected, year
    return None, None


def apply_positions(players: pd.DataFrame) -> pd.DataFrame:
    override = read_csv_optional("player_positions_override.csv")
    players = players.copy()
    pos_map = {}
    if not override.empty:
        override = override.copy()
        override["name_key"] = override["name"].map(normalize_name)
        override["team"] = override["team"].map(normalize_team)
        pos_map = override.set_index(["team", "name_key"])["eligible_positions"].to_dict()

    primary, secondary, eligible, source = [], [], [], []
    for _, row in players.iterrows():
        key = (normalize_team(row["team"]), normalize_name(row["name"]))
        value = pos_map.get(key)
        if not value:
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
            source.append("exact_position_override")
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
    players["team"] = players["team"].map(normalize_team)

    h26 = prepare_hitter_stats(read_csv_optional("hitter_stats_2026.csv"), 2026)
    h25 = prepare_hitter_stats(read_csv_optional("hitter_stats_2025.csv"), 2025)
    p26 = prepare_pitcher_stats(read_csv_optional("pitcher_stats_2026.csv"), 2026)
    p25 = prepare_pitcher_stats(read_csv_optional("pitcher_stats_2025.csv"), 2025)

    rows = []
    for _, row in players.iterrows():
        out = row.to_dict()
        stat, year = pick_stats(row, h26, h25, p26, p25)
        if stat is None:
            # 실제 기록이 없으면 계산하지 않았다고 표시. 게임 실행을 위해 최저 기본값만 둡니다.
            out.update({
                "rating_is_actual": False,
                "source_year_used": "missing",
                "rating_source": "no_2026_or_2025_stat_row_found",
                "contact": 20 if row["role"] != "pitcher" else 0,
                "power": 20 if row["role"] != "pitcher" else 0,
                "discipline": 20 if row["role"] != "pitcher" else 0,
                "speed": 20 if row["role"] != "pitcher" else 0,
                "stuff": 20 if row["role"] == "pitcher" else 0,
                "control": 20 if row["role"] == "pitcher" else 0,
                "stamina": 20 if row["role"] == "pitcher" else 0,
                "stat_PA": 0, "stat_AB": 0, "stat_IP": 0, "stat_G": 0,
                "raw_stat_policy": "no_regression_no_qualification_cut_missing_stats",
            })
        elif row["role"] == "pitcher":
            out.update({
                "rating_is_actual": True,
                "source_year_used": int(year),
                "rating_source": f"{year}_raw_pitcher_stats_no_qualification_cut",
                "contact": 0, "power": 0, "discipline": 0, "speed": 0,
                "stuff": int(stat["stuff_rating"]),
                "control": int(stat["control_rating"]),
                "stamina": int(stat["stamina_rating"]),
                "stat_IP": float(stat.get("IP", 0)),
                "stat_G": int(stat.get("G", 0)),
                "stat_ERA": float(stat.get("ERA", 0)),
                "stat_WHIP": float(stat.get("WHIP", 0)),
                "stat_SO": int(stat.get("SO", 0)),
                "stat_BB": int(stat.get("BB", 0)),
                "raw_stat_policy": "2026_first_even_if_non_qualified_else_2025",
            })
        else:
            out.update({
                "rating_is_actual": True,
                "source_year_used": int(year),
                "rating_source": f"{year}_raw_hitter_stats_no_qualification_cut",
                "contact": int(stat["contact_rating"]),
                "power": int(stat["power_rating"]),
                "discipline": int(stat["discipline_rating"]),
                "speed": int(stat["speed_rating"]),
                "stuff": 0, "control": 0, "stamina": 0,
                "stat_PA": int(stat.get("PA", 0)),
                "stat_AB": int(stat.get("AB", 0)),
                "stat_AVG": float(stat.get("AVG", 0)),
                "stat_OBP": float(stat.get("OBP", 0)),
                "stat_SLG": float(stat.get("SLG", 0)),
                "stat_HR": int(stat.get("HR", 0)),
                "stat_SB": int(stat.get("SB", 0)),
                "raw_stat_policy": "2026_first_even_if_non_qualified_else_2025",
            })
        rows.append(out)

    output = apply_positions(pd.DataFrame(rows))
    output.to_csv(ROOT / "players_2026_raw_current_positions.csv", index=False, encoding="utf-8-sig")
    output[~output["rating_is_actual"].astype(bool)].to_csv(ROOT / "missing_raw_current_stats_report.csv", index=False, encoding="utf-8-sig")
    print("created players_2026_raw_current_positions.csv")
    print("actual ratings:", int(output["rating_is_actual"].sum()), "/", len(output))


if __name__ == "__main__":
    build()
