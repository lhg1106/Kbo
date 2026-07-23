
"""
선수 능력치 생성기

목적:
- 2026 시즌 성적을 먼저 사용
- 규정타석/규정이닝을 못 채운 선수는 2025 시즌 성적을 참고
- 2026 표본이 조금 있으면 2026과 2025를 가중 평균
- 포지션 정보는 roster 파일에서 유지

입력 파일 예시:
    roster_base.csv
    hitter_stats_2026.csv
    hitter_stats_2025.csv
    pitcher_stats_2026.csv
    pitcher_stats_2025.csv

출력:
    players_2026_2025_weighted_ratings.csv

필수 열:
타자: team,name,PA,AB,H,2B,3B,HR,BB,HBP,SO,SB,CS,OBP,SLG
투수: team,name,G,GS,IP,H,HR,BB,HBP,SO,ERA,WHIP
"""
from __future__ import annotations

from pathlib import Path
import math
import pandas as pd

QUAL_PA = 3.1 * 90       # 7월 중순 기준 대략치. 전체 시즌이면 3.1*144 사용.
QUAL_IP = 1.0 * 90       # 7월 중순 기준 대략치. 전체 시즌이면 144 사용.
MIN_PREV_PA = 80
MIN_PREV_IP = 25

TEAM_ALIASES = {
    "삼성": "삼성 라이온즈", "Samsung": "삼성 라이온즈",
    "KT": "KT 위즈", "kt": "KT 위즈",
    "LG": "LG 트윈스",
    "KIA": "KIA 타이거즈", "Kia": "KIA 타이거즈",
    "두산": "두산 베어스", "Doosan": "두산 베어스",
    "한화": "한화 이글스", "Hanwha": "한화 이글스",
    "NC": "NC 다이노스",
    "롯데": "롯데 자이언츠", "Lotte": "롯데 자이언츠",
    "SSG": "SSG 랜더스",
    "키움": "키움 히어로즈", "Kiwoom": "키움 히어로즈",
}


def norm_team(x: str) -> str:
    x = str(x).strip()
    return TEAM_ALIASES.get(x, x)


def safe_num(x, default=0.0) -> float:
    try:
        if pd.isna(x):
            return default
        if isinstance(x, str):
            x = x.replace(',', '').strip()
            if not x:
                return default
        return float(x)
    except Exception:
        return default


def ip_to_float(x) -> float:
    """KBO식 95 1/3, 95.1, 95.2 표기를 이닝 소수로 변환."""
    if pd.isna(x): return 0.0
    text = str(x).strip()
    if " " in text:
        whole, frac = text.split(" ", 1)
        num, den = frac.split("/")
        return float(whole) + float(num) / float(den)
    if text.endswith(".1"):
        return float(text[:-2]) + 1/3
    if text.endswith(".2"):
        return float(text[:-2]) + 2/3
    return safe_num(text)


def percentile_score(series: pd.Series, value: float, reverse=False) -> int:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 2:
        return 50
    pct = (s <= value).mean()
    if reverse:
        pct = 1 - pct
    return int(max(20, min(90, round(20 + pct * 70))))


def load_optional(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    if "team" in df.columns:
        df["team"] = df["team"].map(norm_team)
    return df


def pick_stats(row, current, previous, is_pitcher=False):
    name, team = row["name"], row["team"]
    cur = current[(current["team"].eq(team)) & (current["name"].eq(name))]
    prev = previous[(previous["team"].eq(team)) & (previous["name"].eq(name))]
    threshold = QUAL_IP if is_pitcher else QUAL_PA
    sample_col = "IP" if is_pitcher else "PA"
    prev_min = MIN_PREV_IP if is_pitcher else MIN_PREV_PA

    cur_row = cur.iloc[0] if not cur.empty else None
    prev_row = prev.iloc[0] if not prev.empty else None
    cur_sample = ip_to_float(cur_row[sample_col]) if (cur_row is not None and is_pitcher) else safe_num(cur_row[sample_col]) if cur_row is not None else 0
    prev_sample = ip_to_float(prev_row[sample_col]) if (prev_row is not None and is_pitcher) else safe_num(prev_row[sample_col]) if prev_row is not None else 0

    if cur_row is not None and cur_sample >= threshold:
        return cur_row, "2026", "2026_regulation"
    if cur_row is not None and prev_row is not None and prev_sample >= prev_min:
        # 표본이 애매하면 2026을 0~70%, 2025를 나머지로 반영
        w = min(0.70, max(0.20, cur_sample / threshold)) if cur_sample > 0 else 0.0
        blended = prev_row.copy()
        for col in set(cur_row.index) & set(prev_row.index):
            if col in ["team", "name"]:
                continue
            a, b = safe_num(cur_row[col], None), safe_num(prev_row[col], None)
            if a is not None and b is not None:
                blended[col] = a * w + b * (1 - w)
        return blended, "2026+2025", f"under_regulation_blend_{w:.2f}_2026"
    if prev_row is not None and prev_sample >= prev_min:
        return prev_row, "2025", "2025_previous_season_fallback"
    if cur_row is not None:
        return cur_row, "2026_small_sample", "small_sample_current"
    return None, "missing", "league_average"


def build():
    roster = pd.read_csv("players_2026_07_23.csv")
    roster["team"] = roster["team"].map(norm_team)
    h26 = load_optional("hitter_stats_2026.csv")
    h25 = load_optional("hitter_stats_2025.csv")
    p26 = load_optional("pitcher_stats_2026.csv")
    p25 = load_optional("pitcher_stats_2025.csv")

    out = []
    # 비교 분포는 두 시즌 합쳐서 만든다.
    hitter_dist = pd.concat([h26, h25], ignore_index=True) if not h25.empty else h26
    pitcher_dist = pd.concat([p26, p25], ignore_index=True) if not p25.empty else p26

    for _, r in roster.iterrows():
        row = r.to_dict()
        if row["role"] == "batter":
            stat, year, method = pick_stats(row, h26, h25, is_pitcher=False)
            if stat is None:
                contact = power = discipline = 50
                speed = 45 if row["position"] == "포수" else 50
            else:
                ab = max(1, safe_num(stat.get("AB")))
                pa = max(1, safe_num(stat.get("PA")))
                avg = safe_num(stat.get("AVG"), safe_num(stat.get("H")) / ab)
                slg = safe_num(stat.get("SLG"), safe_num(stat.get("TB")) / ab)
                obp = safe_num(stat.get("OBP"), (safe_num(stat.get("H")) + safe_num(stat.get("BB")) + safe_num(stat.get("HBP"))) / pa)
                so_rate = safe_num(stat.get("SO")) / pa
                sb = safe_num(stat.get("SB"))
                cs = safe_num(stat.get("CS"))
                sb_eff = sb / max(1, sb + cs)
                contact = round(0.70 * percentile_score(hitter_dist.get("AVG", pd.Series([avg])), avg) + 0.30 * percentile_score(hitter_dist.get("SO", pd.Series([so_rate])), so_rate, reverse=True))
                power = percentile_score(hitter_dist.get("SLG", pd.Series([slg])), slg)
                discipline = percentile_score(hitter_dist.get("OBP", pd.Series([obp])), obp)
                speed = round(0.60 * percentile_score(hitter_dist.get("SB", pd.Series([sb])), sb) + 0.40 * percentile_score(pd.Series([0.5, 0.7, 0.85, 1.0]), sb_eff))
            row.update(contact=contact, power=power, discipline=discipline, speed=speed, stuff=50, control=50, stamina=0, source_year_used=year, rating_source=method)
        else:
            stat, year, method = pick_stats(row, p26, p25, is_pitcher=True)
            if stat is None:
                stuff = control = 50
                stamina = 55
            else:
                ip = max(1, ip_to_float(stat.get("IP")))
                k9 = safe_num(stat.get("SO")) * 9 / ip
                bb9 = safe_num(stat.get("BB")) * 9 / ip
                era = safe_num(stat.get("ERA"), 4.50)
                whip = safe_num(stat.get("WHIP"), 1.45)
                gs = safe_num(stat.get("GS"), 0)
                g = max(1, safe_num(stat.get("G"), 1))
                stuff = round(0.60 * percentile_score(pd.Series(pitcher_dist.get("SO", [])) / pitcher_dist.get("IP", pd.Series([1])).map(ip_to_float).replace(0, 1) * 9 if not pitcher_dist.empty else pd.Series([k9]), k9) + 0.40 * percentile_score(pitcher_dist.get("ERA", pd.Series([era])), era, reverse=True))
                control = round(0.55 * percentile_score(pd.Series([1.0,1.2,1.4,1.6,1.8]), whip, reverse=True) + 0.45 * percentile_score(pd.Series([1.5,2.5,3.5,4.5,5.5]), bb9, reverse=True))
                starter_ratio = gs / g
                stamina = int(max(35, min(88, round(40 + min(1.0, ip / max(1, g) / 6.0) * 35 + starter_ratio * 13))))
            row.update(contact=0, power=0, discipline=0, speed=0, stuff=stuff, control=control, stamina=stamina, source_year_used=year, rating_source=method)
        out.append(row)
    result = pd.DataFrame(out)
    result.to_csv("players_2026_2025_weighted_ratings.csv", index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    build()
