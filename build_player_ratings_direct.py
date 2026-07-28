from __future__ import annotations

from pathlib import Path
import math
import re
import sys
from typing import Iterable

import numpy as np
import pandas as pd


BASE = Path(__file__).resolve().parent

ROSTER_FILE = BASE / "roster_positions_2026.csv"
HITTER_2026 = BASE / "hitter_stats_2026.csv"
PITCHER_2026 = BASE / "pitcher_stats_2026.csv"
HITTER_2025 = BASE / "hitter_stats_2025.csv"
PITCHER_2025 = BASE / "pitcher_stats_2025.csv"

OUTPUT_FILE = BASE / "players_2026_direct_stats_positions.csv"
REPORT_FILE = BASE / "direct_stats_build_report.csv"


TEAM_ALIASES = {
    "KIA": "KIA 타이거즈",
    "삼성": "삼성 라이온즈",
    "LG": "LG 트윈스",
    "두산": "두산 베어스",
    "KT": "KT 위즈",
    "SSG": "SSG 랜더스",
    "롯데": "롯데 자이언츠",
    "한화": "한화 이글스",
    "NC": "NC 다이노스",
    "키움": "키움 히어로즈",
}


def norm_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value)).strip().lower()


def norm_name(value: object) -> str:
    text = norm_text(value)
    text = re.sub(r"\(\d+\)$", "", text)
    return text


def first_existing(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    lookup = {norm_text(c): c for c in df.columns}
    for name in names:
        key = norm_text(name)
        if key in lookup:
            return lookup[key]
    return None


def number_series(df: pd.DataFrame, names: Iterable[str], default=np.nan) -> pd.Series:
    col = first_existing(df, names)
    if col is None:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(
        df[col].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )


def text_series(df: pd.DataFrame, names: Iterable[str]) -> pd.Series:
    col = first_existing(df, names)
    if col is None:
        return pd.Series("", index=df.index, dtype="object")
    return df[col].fillna("").astype(str)


def innings_to_float(value: object) -> float:
    if pd.isna(value):
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0

    # KBO-style 12 1/3, 12⅓, 12.1 and decimal inputs supported.
    mixed = re.match(r"^(\d+)\s+([12])/3$", text)
    if mixed:
        return int(mixed.group(1)) + int(mixed.group(2)) / 3

    text = text.replace("⅓", ".1").replace("⅔", ".2")
    try:
        value = float(text)
    except ValueError:
        return 0.0

    whole = int(value)
    frac_digit = round((value - whole) * 10)
    if frac_digit == 1:
        return whole + 1 / 3
    if frac_digit == 2:
        return whole + 2 / 3
    return value


def percentile_rating(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    평균회귀 없이 그 시즌 실제 수치의 리그 내 백분위만 20~80으로 변환합니다.
    출전량 가중치나 규정타석/규정이닝 조건을 적용하지 않습니다.
    """
    values = pd.to_numeric(series, errors="coerce")
    valid = values.notna()
    result = pd.Series(np.nan, index=series.index, dtype="float64")

    if valid.sum() == 0:
        return result

    pct = values[valid].rank(method="average", pct=True)
    if not higher_is_better:
        pct = 1 - pct + (1 / valid.sum())

    result.loc[valid] = 20 + 60 * pct
    return result.clip(20, 80)


def prepare_hitter_file(path: Path, year: int) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    raw = pd.read_csv(path)
    df = pd.DataFrame(index=raw.index)

    df["name"] = text_series(raw, ["선수명", "player", "name", "선수"])
    df["team_raw"] = text_series(raw, ["팀명", "team", "팀"])
    df["name_key"] = df["name"].map(norm_name)
    df["team_key"] = df["team_raw"].map(norm_text)
    df["year"] = year
    df["G"] = number_series(raw, ["G", "경기"])
    df["PA"] = number_series(raw, ["PA", "타석"])
    df["AB"] = number_series(raw, ["AB", "타수"])
    df["H"] = number_series(raw, ["H", "안타"])
    df["2B"] = number_series(raw, ["2B", "2루타"])
    df["3B"] = number_series(raw, ["3B", "3루타"])
    df["HR"] = number_series(raw, ["HR", "홈런"])
    df["BB"] = number_series(raw, ["BB", "볼넷"])
    df["HBP"] = number_series(raw, ["HBP", "사구"])
    df["SO"] = number_series(raw, ["SO", "삼진"])
    df["SB"] = number_series(raw, ["SB", "도루"])
    df["CS"] = number_series(raw, ["CS", "도루실패"])
    df["AVG"] = number_series(raw, ["AVG", "타율"])
    df["OBP"] = number_series(raw, ["OBP", "출루율"])
    df["SLG"] = number_series(raw, ["SLG", "장타율"])

    # Missing rate stats are derived from raw counts without qualification filters.
    df["AVG"] = df["AVG"].where(df["AVG"].notna(), df["H"] / df["AB"].replace(0, np.nan))
    total_bases = df["H"] + df["2B"] + 2 * df["3B"] + 3 * df["HR"]
    df["SLG"] = df["SLG"].where(df["SLG"].notna(), total_bases / df["AB"].replace(0, np.nan))
    obp_den = df["AB"] + df["BB"] + df["HBP"]
    df["OBP"] = df["OBP"].where(
        df["OBP"].notna(),
        (df["H"] + df["BB"] + df["HBP"]) / obp_den.replace(0, np.nan),
    )

    df["BB_rate"] = df["BB"] / df["PA"].replace(0, np.nan)
    df["K_rate"] = df["SO"] / df["PA"].replace(0, np.nan)
    df["HR_rate"] = df["HR"] / df["PA"].replace(0, np.nan)
    df["ISO"] = df["SLG"] - df["AVG"]
    df["SB_success"] = df["SB"] / (df["SB"] + df["CS"]).replace(0, np.nan)

    # A player counts as having current stats with any PA/G/AB record.
    df["has_stats"] = (df["PA"].fillna(0) > 0) | (df["AB"].fillna(0) > 0) | (df["G"].fillna(0) > 0)
    return df[df["name_key"] != ""].copy()


def prepare_pitcher_file(path: Path, year: int) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    raw = pd.read_csv(path)
    df = pd.DataFrame(index=raw.index)

    df["name"] = text_series(raw, ["선수명", "player", "name", "선수"])
    df["team_raw"] = text_series(raw, ["팀명", "team", "팀"])
    df["name_key"] = df["name"].map(norm_name)
    df["team_key"] = df["team_raw"].map(norm_text)
    df["year"] = year
    df["G"] = number_series(raw, ["G", "경기"])
    df["GS"] = number_series(raw, ["GS", "선발"])
    ip_raw = text_series(raw, ["IP", "이닝"])
    df["IP"] = ip_raw.map(innings_to_float)
    df["H"] = number_series(raw, ["H", "피안타"])
    df["HR"] = number_series(raw, ["HR", "피홈런"])
    df["BB"] = number_series(raw, ["BB", "볼넷"])
    df["HBP"] = number_series(raw, ["HBP", "사구"])
    df["SO"] = number_series(raw, ["SO", "탈삼진"])
    df["ER"] = number_series(raw, ["ER", "자책"])
    df["ERA"] = number_series(raw, ["ERA", "평균자책점"])
    df["WHIP"] = number_series(raw, ["WHIP"])

    df["ERA"] = df["ERA"].where(df["ERA"].notna(), 9 * df["ER"] / df["IP"].replace(0, np.nan))
    df["WHIP"] = df["WHIP"].where(
        df["WHIP"].notna(),
        (df["H"] + df["BB"]) / df["IP"].replace(0, np.nan),
    )
    df["K9"] = 9 * df["SO"] / df["IP"].replace(0, np.nan)
    df["BB9"] = 9 * df["BB"] / df["IP"].replace(0, np.nan)
    df["H9"] = 9 * df["H"] / df["IP"].replace(0, np.nan)
    df["HR9"] = 9 * df["HR"] / df["IP"].replace(0, np.nan)
    df["IP_per_G"] = df["IP"] / df["G"].replace(0, np.nan)

    # Any recorded inning or appearance is used directly.
    df["has_stats"] = (df["IP"].fillna(0) > 0) | (df["G"].fillna(0) > 0)
    return df[df["name_key"] != ""].copy()


def build_ratings(hitters: pd.DataFrame, pitchers: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    hitters = hitters.copy()
    pitchers = pitchers.copy()

    if not hitters.empty:
        avg_r = percentile_rating(hitters["AVG"], True)
        obp_r = percentile_rating(hitters["OBP"], True)
        slg_r = percentile_rating(hitters["SLG"], True)
        iso_r = percentile_rating(hitters["ISO"], True)
        bb_r = percentile_rating(hitters["BB_rate"], True)
        k_r = percentile_rating(hitters["K_rate"], False)
        hr_r = percentile_rating(hitters["HR_rate"], True)
        sb_r = percentile_rating(hitters["SB"], True)
        sbp_r = percentile_rating(hitters["SB_success"], True)

        hitters["contact"] = (avg_r * 0.70 + k_r * 0.30).round()
        hitters["power"] = (slg_r * 0.45 + iso_r * 0.35 + hr_r * 0.20).round()
        hitters["discipline"] = (obp_r * 0.65 + bb_r * 0.35).round()
        hitters["speed"] = (sb_r.fillna(20) * 0.65 + sbp_r.fillna(20) * 0.35).round()

    if not pitchers.empty:
        era_r = percentile_rating(pitchers["ERA"], False)
        whip_r = percentile_rating(pitchers["WHIP"], False)
        k9_r = percentile_rating(pitchers["K9"], True)
        bb9_r = percentile_rating(pitchers["BB9"], False)
        h9_r = percentile_rating(pitchers["H9"], False)
        hr9_r = percentile_rating(pitchers["HR9"], False)
        ipg_r = percentile_rating(pitchers["IP_per_G"], True)
        ip_r = percentile_rating(pitchers["IP"], True)

        pitchers["stuff"] = (
            k9_r * 0.42 + h9_r * 0.25 + era_r * 0.20 + hr9_r * 0.13
        ).round()
        pitchers["control"] = (
            bb9_r * 0.58 + whip_r * 0.42
        ).round()
        pitchers["stamina"] = (
            ipg_r * 0.70 + ip_r * 0.30
        ).round()

    return hitters, pitchers


def select_current_or_previous(current: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    """
    Uses 2026 whenever any 2026 record exists.
    2025 is used only when the player has no 2026 PA/G or IP/G at all.
    """
    if current.empty:
        return previous.copy()
    if previous.empty:
        return current.copy()

    current = current[current["has_stats"]].copy()
    previous = previous[previous["has_stats"]].copy()

    current_keys = set(current["name_key"])
    fallback = previous[~previous["name_key"].isin(current_keys)].copy()
    return pd.concat([current, fallback], ignore_index=True)


def main() -> None:
    if not ROSTER_FILE.exists():
        raise FileNotFoundError(f"로스터 파일 없음: {ROSTER_FILE}")

    roster = pd.read_csv(ROSTER_FILE)
    roster["name_key"] = roster["name"].map(norm_name)

    h26 = prepare_hitter_file(HITTER_2026, 2026)
    p26 = prepare_pitcher_file(PITCHER_2026, 2026)
    h25 = prepare_hitter_file(HITTER_2025, 2025)
    p25 = prepare_pitcher_file(PITCHER_2025, 2025)

    hitters = select_current_or_previous(h26, h25)
    pitchers = select_current_or_previous(p26, p25)
    hitters, pitchers = build_ratings(hitters, pitchers)

    hitter_map = hitters.sort_values("year", ascending=False).drop_duplicates("name_key").set_index("name_key")
    pitcher_map = pitchers.sort_values("year", ascending=False).drop_duplicates("name_key").set_index("name_key")

    rows = []
    report = []

    for _, player in roster.iterrows():
        name_key = player["name_key"]
        role = str(player.get("role", "batter"))
        out = player.to_dict()

        if role == "pitcher":
            if name_key in pitcher_map.index:
                stat = pitcher_map.loc[name_key]
                out.update({
                    "stuff": int(stat["stuff"]),
                    "control": int(stat["control"]),
                    "stamina": int(stat["stamina"]),
                    "contact": 20,
                    "power": 20,
                    "discipline": 20,
                    "speed": 20,
                    "stats_year": int(stat["year"]),
                    "rating_source": f"{int(stat['year'])}_direct_pitcher_stats",
                    "rating_is_actual": True,
                    "raw_G": stat.get("G"),
                    "raw_IP": stat.get("IP"),
                    "raw_ERA": stat.get("ERA"),
                    "raw_WHIP": stat.get("WHIP"),
                    "raw_K9": stat.get("K9"),
                    "raw_BB9": stat.get("BB9"),
                })
            else:
                out.update({
                    "stuff": np.nan, "control": np.nan, "stamina": np.nan,
                    "rating_source": "missing_2026_and_2025_pitcher_stats",
                    "rating_is_actual": False,
                })
        else:
            if name_key in hitter_map.index:
                stat = hitter_map.loc[name_key]
                out.update({
                    "contact": int(stat["contact"]),
                    "power": int(stat["power"]),
                    "discipline": int(stat["discipline"]),
                    "speed": int(stat["speed"]),
                    "stuff": 20,
                    "control": 20,
                    "stamina": 20,
                    "stats_year": int(stat["year"]),
                    "rating_source": f"{int(stat['year'])}_direct_hitter_stats",
                    "rating_is_actual": True,
                    "raw_G": stat.get("G"),
                    "raw_PA": stat.get("PA"),
                    "raw_AVG": stat.get("AVG"),
                    "raw_OBP": stat.get("OBP"),
                    "raw_SLG": stat.get("SLG"),
                    "raw_BB_rate": stat.get("BB_rate"),
                    "raw_K_rate": stat.get("K_rate"),
                })
            else:
                out.update({
                    "contact": np.nan, "power": np.nan,
                    "discipline": np.nan, "speed": np.nan,
                    "rating_source": "missing_2026_and_2025_hitter_stats",
                    "rating_is_actual": False,
                })

        rows.append(out)
        report.append({
            "team": player.get("team", ""),
            "name": player.get("name", ""),
            "role": role,
            "matched": bool(out.get("rating_is_actual", False)),
            "stats_year": out.get("stats_year", ""),
            "rating_source": out.get("rating_source", ""),
        })

    output = pd.DataFrame(rows)
    build_report = pd.DataFrame(report)

    # Do not silently replace missing actual stats with 50.
    missing = build_report[~build_report["matched"]]
    if not missing.empty:
        print("\n[주의] 실제 2026/2025 기록을 찾지 못한 선수:")
        print(missing[["team", "name", "role"]].to_string(index=False))

    output.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    build_report.to_csv(REPORT_FILE, index=False, encoding="utf-8-sig")

    print(f"\n완료: {OUTPUT_FILE}")
    print(f"매칭: {build_report['matched'].sum()} / {len(build_report)}")
    print(f"리포트: {REPORT_FILE}")


if __name__ == "__main__":
    main()
