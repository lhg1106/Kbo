import copy
import json
import math
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="KBO 감독 시즌 시뮬레이터 v6",
    page_icon="⚾",
    layout="wide",
)

KBO_TEAMS = [
    "KIA 타이거즈",
    "삼성 라이온즈",
    "LG 트윈스",
    "두산 베어스",
    "KT 위즈",
    "SSG 랜더스",
    "롯데 자이언츠",
    "한화 이글스",
    "NC 다이노스",
    "키움 히어로즈",
]

OPENING_MATCHUPS = [
    ("KT 위즈", "LG 트윈스"),
    ("키움 히어로즈", "한화 이글스"),
    ("KIA 타이거즈", "SSG 랜더스"),
    ("롯데 자이언츠", "삼성 라이온즈"),
    ("두산 베어스", "NC 다이노스"),
]

VENUES = {
    "LG 트윈스": "잠실",
    "두산 베어스": "잠실",
    "KT 위즈": "수원",
    "SSG 랜더스": "문학",
    "KIA 타이거즈": "광주",
    "삼성 라이온즈": "대구",
    "롯데 자이언츠": "사직",
    "한화 이글스": "대전",
    "NC 다이노스": "창원",
    "키움 히어로즈": "고척",
}

DEFAULT_TEAM_RATINGS = {
    team: {"offense": 50, "pitching": 50, "defense": 50}
    for team in KBO_TEAMS
}

BASE_DIR = Path(__file__).resolve().parent


def find_data_file(filename: str) -> Optional[Path]:
    """Streamlit Cloud/GitHub 배포 환경에서도 데이터 파일을 안정적으로 찾습니다."""
    candidates = [
        BASE_DIR / filename,
        Path.cwd() / filename,
        BASE_DIR / "data" / filename,
        Path.cwd() / "data" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None



@dataclass
class Player:
    name: str
    team: str
    role: str
    position: str = ""
    lineup_slot: str = ""
    primary_position: str = ""
    secondary_positions: str = ""
    eligible_positions: str = ""
    rating_is_actual: bool = True
    contact: int = 50
    power: int = 50
    discipline: int = 50
    speed: int = 50
    stuff: int = 50
    control: int = 50
    stamina: int = 80

    pa: int = 0
    ab: int = 0
    h: int = 0
    doubles: int = 0
    triples: int = 0
    hr: int = 0
    bb: int = 0
    so: int = 0
    r: int = 0
    rbi: int = 0

    outs_recorded: int = 0
    hits_allowed: int = 0
    walks_allowed: int = 0
    runs_allowed: int = 0
    batters_faced: int = 0

    used: bool = False

    @property
    def avg(self) -> float:
        return self.h / self.ab if self.ab else 0.0

    @property
    def innings(self) -> str:
        return f"{self.outs_recorded // 3}.{self.outs_recorded % 3}"


@dataclass
class TeamGameState:
    name: str
    lineup: List[Player]
    bench: List[Player]
    pitchers: List[Player]
    current_pitcher_index: int = 0
    batting_index: int = 0
    score: int = 0
    inning_runs: List[int] = field(default_factory=list)

    @property
    def pitcher(self) -> Player:
        return self.pitchers[self.current_pitcher_index]


@dataclass
class LiveGame:
    game_id: int
    game_date: str
    away: TeamGameState
    home: TeamGameState
    inning: int = 1
    half: str = "초"
    outs: int = 0
    bases: List[Optional[Player]] = field(
        default_factory=lambda: [None, None, None]
    )
    game_over: bool = False
    finalized: bool = False
    logs: List[str] = field(default_factory=list)


@dataclass
class TeamRecord:
    team: str
    wins: int = 0
    losses: int = 0
    draws: int = 0
    runs_for: int = 0
    runs_against: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def pct(self) -> float:
        decisions = self.wins + self.losses
        return self.wins / decisions if decisions else 0.0


@dataclass
class ScheduledGame:
    game_id: int
    game_date: str
    away: str
    home: str
    venue: str
    played: bool = False
    away_score: Optional[int] = None
    home_score: Optional[int] = None
    user_game: bool = False


@dataclass
class SeasonState:
    selected_team: str
    schedule: List[ScheduledGame]
    records: Dict[str, TeamRecord]
    ratings: Dict[str, Dict[str, int]]
    active_game: Optional[LiveGame] = None
    pending_date_simulation: Optional[str] = None
    last_round_results: List[dict] = field(default_factory=list)
    season_finished: bool = False


LINEUP_SLOTS = ["C", "1B", "2B", "SS", "3B", "LF", "CF", "RF", "DH"]
SLOT_POSITION_RULES = {
    "C": ["C"],
    "1B": ["1B"],
    "2B": ["2B"],
    "SS": ["SS"],
    "3B": ["3B"],
    "LF": ["LF"],
    "CF": ["CF"],
    "RF": ["RF"],
    "DH": ["C", "1B", "2B", "SS", "3B", "LF", "CF", "RF", "DH"],
}

def eligible_set(value: str) -> set:
    return {x.strip() for x in str(value).replace(",", ";").split(";") if x.strip()}


def make_fallback_player_database() -> pd.DataFrame:
    """CSV가 누락되어도 앱이 죽지 않게 만드는 내장 임시 로스터입니다."""
    rows = []
    position_slots = [
        ("포수", 2),
        ("내야수", 6),
        ("외야수", 5),
    ]
    for team in KBO_TEAMS:
        short = team.split()[0]
        for position, count in position_slots:
            for i in range(1, count + 1):
                rows.append({
                    "team": team,
                    "name": f"{short} {position} {i}",
                    "position": position,
                    "role": "batter",
                    "contact": 50,
                    "power": 50,
                    "discipline": 50,
                    "speed": 50,
                    "stuff": 50,
                    "control": 50,
                    "stamina": 0,
                    "rating_source": "fallback_generated",
                })
        for i in range(1, 8):
            rows.append({
                "team": team,
                "name": f"{short} 투수 {i}",
                "position": "투수",
                "role": "pitcher",
                "contact": 50,
                "power": 50,
                "discipline": 50,
                "speed": 50,
                "stuff": 50,
                "control": 50,
                "stamina": 80 if i == 1 else 35,
                "rating_source": "fallback_generated",
            })
    return pd.DataFrame(rows)


def load_player_database() -> pd.DataFrame:
    preferred_files = [
        "players_actual_no_regression_positions.csv",
        "players_2026_2025_weighted_ratings.csv",
        "players_2026_ratings.csv",
        "players_2026_07_23.csv",
    ]

    chosen_path = None
    for filename in preferred_files:
        chosen_path = find_data_file(filename)
        if chosen_path is not None:
            break

    if chosen_path is None:
        st.warning(
            "선수 CSV 파일을 찾지 못해서 임시 로스터로 실행합니다. "
            "GitHub 저장소에 players_2026_2025_weighted_ratings.csv를 함께 올리세요."
        )
        df = make_fallback_player_database()
    else:
        df = pd.read_csv(chosen_path)

    numeric = ["contact", "power", "discipline", "speed", "stuff", "control", "stamina"]
    for column in numeric:
        if column not in df.columns:
            df[column] = 50
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(50).astype(int)

    if "position" not in df.columns:
        df["position"] = ""
    if "role" not in df.columns:
        df["role"] = "batter"
    if "primary_position" not in df.columns:
        df["primary_position"] = df["position"].map({"투수":"P", "포수":"C", "내야수":"IF", "외야수":"OF"}).fillna(df["position"])
    if "eligible_positions" not in df.columns:
        def default_eligible(row):
            pos = str(row.get("primary_position", ""))
            if pos == "P": return "P"
            if pos == "C": return "C;DH"
            if pos == "IF": return "1B;2B;SS;3B;DH"
            if pos == "OF": return "LF;CF;RF;DH"
            return pos or "DH"
        df["eligible_positions"] = df.apply(default_eligible, axis=1)
    if "secondary_positions" not in df.columns:
        df["secondary_positions"] = ""
    if "rating_is_actual" not in df.columns:
        source = df.get("rating_source", pd.Series([""] * len(df))).astype(str).str.lower()
        df["rating_is_actual"] = ~source.str.contains("league_average|fallback|missing|generated", regex=True)

    return df


PLAYER_DATABASE = load_player_database()


def row_to_player(row: pd.Series, lineup_slot: str = "") -> Player:
    return Player(
        name=str(row["name"]),
        team=str(row["team"]),
        role=str(row["role"]),
        position=str(row.get("position", "")),
        lineup_slot=lineup_slot,
        primary_position=str(row.get("primary_position", row.get("position", ""))),
        secondary_positions=str(row.get("secondary_positions", "")),
        eligible_positions=str(row.get("eligible_positions", row.get("primary_position", row.get("position", "")))),
        rating_is_actual=bool(row.get("rating_is_actual", True)),
        contact=int(row["contact"]),
        power=int(row["power"]),
        discipline=int(row["discipline"]),
        speed=int(row["speed"]),
        stuff=int(row["stuff"]),
        control=int(row["control"]),
        stamina=int(row["stamina"]),
    )


def hitter_overall(row: pd.Series) -> float:
    return (
        row["contact"] * 0.35
        + row["power"] * 0.30
        + row["discipline"] * 0.23
        + row["speed"] * 0.12
    )


def pick_best_by_position(
    hitters: pd.DataFrame,
    chosen_indices: set,
    positions: List[str],
) -> Optional[pd.Series]:
    required = set(positions)
    pool = hitters[~hitters.index.isin(chosen_indices)].copy()
    pool = pool[pool["eligible_positions"].apply(lambda value: bool(eligible_set(value) & required))]
    if pool.empty:
        return None

    # 평균회귀 데이터보다 실제 2026/2025 기록 기반 선수 우선.
    if "rating_is_actual" in pool.columns:
        pool = pool.sort_values(
            ["rating_is_actual", "overall", "contact", "power"],
            ascending=[False, False, False, False],
        )
    else:
        pool = pool.sort_values(["overall", "contact", "power"], ascending=False)
    return pool.iloc[0]


def build_position_balanced_lineup(hitters: pd.DataFrame) -> Tuple[List[Player], List[Player]]:
    hitters = hitters.copy()
    hitters["overall"] = hitters.apply(hitter_overall, axis=1)
    chosen_indices = set()
    lineup_rows: List[Tuple[str, pd.Series]] = []

    for slot in LINEUP_SLOTS:
        allowed_positions = SLOT_POSITION_RULES[slot]
        row = pick_best_by_position(hitters, chosen_indices, allowed_positions)
        if row is None:
            raise ValueError(
                f"{slot} 수비위치에 들어갈 실제 포지션 선수가 부족합니다. "
                "players_actual_no_regression_positions.csv의 eligible_positions를 확인하세요."
            )
        chosen_indices.add(row.name)
        lineup_rows.append((slot, row))

    # 실제 타순은 출루/컨택/파워 밸런스 기준으로 재정렬합니다.
    def batting_order_score(item: Tuple[str, pd.Series]) -> float:
        slot, row = item
        if slot in ["C", "1B", "LF", "RF", "DH"]:
            return row["overall"] + row["power"] * 0.08
        return row["overall"] + row["speed"] * 0.05 + row["discipline"] * 0.04

    lineup_rows = sorted(lineup_rows, key=batting_order_score, reverse=True)
    lineup = [row_to_player(row, lineup_slot=slot) for slot, row in lineup_rows]

    bench_pool = hitters[~hitters.index.isin(chosen_indices)].copy()
    bench_pool = bench_pool.sort_values(["overall", "contact"], ascending=False)
    bench = [row_to_player(row) for _, row in bench_pool.head(7).iterrows()]
    return lineup, bench


def create_team_roster(team_name: str) -> TeamGameState:
    team_df = PLAYER_DATABASE[PLAYER_DATABASE["team"] == team_name].copy()
    hitters = team_df[team_df["role"] == "batter"].copy()
    pitchers_df = team_df[team_df["role"] == "pitcher"].copy()

    lineup, bench = build_position_balanced_lineup(hitters)

    pitchers_df["starter_score"] = (
        pitchers_df["stuff"] * 0.42
        + pitchers_df["control"] * 0.33
        + pitchers_df["stamina"] * 0.25
    )
    pitchers_df = pitchers_df.sort_values("starter_score", ascending=False)
    pitchers = [row_to_player(row) for _, row in pitchers_df.head(8).iterrows()]

    if len(lineup) < 9 or len(pitchers) < 2:
        raise ValueError(f"{team_name} 선수 데이터가 부족합니다.")
    pitchers[0].used = True
    return TeamGameState(name=team_name, lineup=lineup, bench=bench, pitchers=pitchers)


def generate_round_robin_pairs(
    teams: List[str],
) -> List[List[Tuple[str, str]]]:
    rotation = teams[:]
    rounds = []

    for round_index in range(len(teams) - 1):
        pairs = []
        for i in range(len(teams) // 2):
            left = rotation[i]
            right = rotation[-(i + 1)]
            if (round_index + i) % 2 == 0:
                pairs.append((left, right))
            else:
                pairs.append((right, left))

        rounds.append(pairs)
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]

    return rounds


def generate_schedule() -> pd.DataFrame:
    rows = []
    game_id = 1

    for offset in (0, 1):
        game_date = date(2026, 3, 28) + timedelta(days=offset)
        for away, home in OPENING_MATCHUPS:
            rows.append({
                "game_id": game_id,
                "date": game_date.isoformat(),
                "away": away,
                "home": home,
                "venue": VENUES[home],
            })
            game_id += 1

    pair_count = {
        tuple(sorted((away, home))): 2
        for away, home in OPENING_MATCHUPS
    }

    for i, team_a in enumerate(KBO_TEAMS):
        for team_b in KBO_TEAMS[i + 1:]:
            pair_count.setdefault(tuple(sorted((team_a, team_b))), 0)

    rounds = generate_round_robin_pairs(KBO_TEAMS)
    current_date = date(2026, 3, 31)
    pointer = 0

    while game_id <= 720:
        if current_date.weekday() == 0:
            current_date += timedelta(days=1)
            continue

        pairs = rounds[pointer % len(rounds)]
        added = 0

        for base_away, base_home in pairs:
            key = tuple(sorted((base_away, base_home)))
            count = pair_count[key]

            if count >= 16:
                continue

            if count % 2 == 0:
                away, home = base_away, base_home
            else:
                away, home = base_home, base_away

            rows.append({
                "game_id": game_id,
                "date": current_date.isoformat(),
                "away": away,
                "home": home,
                "venue": VENUES[home],
            })
            pair_count[key] += 1
            game_id += 1
            added += 1

            if game_id > 720:
                break

        pointer += 1
        current_date += timedelta(days=1)

        if added == 0 and all(value >= 16 for value in pair_count.values()):
            break

    return pd.DataFrame(rows)


def validate_schedule(df: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "away", "home"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "필수 열 누락: " + ", ".join(sorted(missing))
        )

    result = df.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.date.astype(str)

    if "game_id" not in result.columns:
        result.insert(0, "game_id", range(1, len(result) + 1))

    if "venue" not in result.columns:
        result["venue"] = result["home"].map(VENUES).fillna("")

    unknown = (
        set(result["away"]) | set(result["home"])
    ) - set(KBO_TEAMS)

    if unknown:
        raise ValueError(
            "알 수 없는 팀 이름: " + ", ".join(sorted(unknown))
        )

    return result[
        ["game_id", "date", "away", "home", "venue"]
    ].sort_values(["date", "game_id"]).reset_index(drop=True)


def new_season(
    selected_team: str,
    schedule_df: pd.DataFrame,
) -> SeasonState:
    schedule = []

    for _, row in schedule_df.iterrows():
        schedule.append(
            ScheduledGame(
                game_id=int(row["game_id"]),
                game_date=str(row["date"]),
                away=str(row["away"]),
                home=str(row["home"]),
                venue=str(row["venue"]),
                user_game=selected_team in (
                    str(row["away"]),
                    str(row["home"]),
                ),
            )
        )

    return SeasonState(
        selected_team=selected_team,
        schedule=schedule,
        records={
            team: TeamRecord(team=team)
            for team in KBO_TEAMS
        },
        ratings=copy.deepcopy(DEFAULT_TEAM_RATINGS),
    )


def next_user_schedule_game(
    season: SeasonState,
) -> Optional[ScheduledGame]:
    for game in season.schedule:
        if game.user_game and not game.played:
            return game
    return None


def start_next_live_game(season: SeasonState) -> None:
    scheduled = next_user_schedule_game(season)

    if scheduled is None:
        season.season_finished = True
        season.active_game = None
        return

    season.active_game = LiveGame(
        game_id=scheduled.game_id,
        game_date=scheduled.game_date,
        away=create_team_roster(scheduled.away),
        home=create_team_roster(scheduled.home),
    )


def current_teams(
    game: LiveGame,
) -> Tuple[TeamGameState, TeamGameState]:
    if game.half == "초":
        return game.away, game.home
    return game.home, game.away


def ensure_inning(team: TeamGameState, inning: int) -> None:
    while len(team.inning_runs) < inning:
        team.inning_runs.append(0)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def choose_result(batter: Player, pitcher: Player) -> str:
    contact_edge = (batter.contact - pitcher.stuff) / 100
    power_edge = (batter.power - pitcher.stuff) / 100
    discipline_edge = (batter.discipline - pitcher.control) / 100

    weights = {
        "BB": clamp(0.080 + 0.050 * discipline_edge, 0.035, 0.160),
        "SO": clamp(0.190 - 0.080 * contact_edge, 0.080, 0.320),
        "1B": clamp(0.155 + 0.075 * contact_edge, 0.080, 0.240),
        "2B": clamp(0.047 + 0.030 * power_edge, 0.018, 0.090),
        "3B": clamp(0.005 + (batter.speed - 50) * 0.00008, 0.001, 0.015),
        "HR": clamp(0.030 + 0.035 * power_edge, 0.008, 0.085),
    }
    weights["OUT"] = max(0.20, 1 - sum(weights.values()))

    return random.choices(
        list(weights),
        weights=list(weights.values()),
        k=1,
    )[0]


def add_log(game: LiveGame, text: str) -> None:
    game.logs.append(text)
    game.logs = game.logs[-200:]


def score_runner(
    batting_team: TeamGameState,
    pitcher: Player,
    runner: Player,
    batter: Player,
) -> None:
    batting_team.score += 1
    batting_team.inning_runs[-1] += 1
    runner.r += 1
    batter.rbi += 1
    pitcher.runs_allowed += 1


def advance_walk(
    game: LiveGame,
    batting_team: TeamGameState,
    pitcher: Player,
    batter: Player,
) -> int:
    first, second, third = game.bases
    scored = 0

    if first and second and third:
        score_runner(batting_team, pitcher, third, batter)
        scored += 1

    new_third = third
    new_second = second

    if first and second:
        new_third = second

    if first:
        new_second = first

    game.bases = [batter, new_second, new_third]
    return scored


def advance_hit(
    game: LiveGame,
    batting_team: TeamGameState,
    pitcher: Player,
    batter: Player,
    bases_gained: int,
) -> int:
    old_bases = game.bases[:]
    game.bases = [None, None, None]
    scored = 0

    for base_index in range(2, -1, -1):
        runner = old_bases[base_index]
        if runner is None:
            continue

        destination = base_index + bases_gained

        if bases_gained == 1:
            if base_index == 1 and random.random() < 0.60:
                destination = 3
            elif base_index == 0 and random.random() < 0.35:
                destination = 2

        if destination >= 3:
            score_runner(
                batting_team,
                pitcher,
                runner,
                batter,
            )
            scored += 1
        else:
            game.bases[destination] = runner

    if bases_gained == 4:
        score_runner(
            batting_team,
            pitcher,
            batter,
            batter,
        )
        scored += 1
    else:
        game.bases[bases_gained - 1] = batter

    return scored


def check_end_or_change_half(game: LiveGame) -> None:
    if (
        game.inning >= 9
        and game.half == "말"
        and game.home.score > game.away.score
    ):
        game.game_over = True
        add_log(game, "경기 종료: 홈팀 끝내기 승리")
        return

    if game.outs < 3:
        return

    game.outs = 0
    game.bases = [None, None, None]

    if game.half == "초":
        if (
            game.inning >= 9
            and game.home.score > game.away.score
        ):
            game.game_over = True
            add_log(game, "경기 종료: 홈팀 승리")
            return

        game.half = "말"
    else:
        if (
            game.inning >= 9
            and game.home.score != game.away.score
        ):
            game.game_over = True
            add_log(game, "경기 종료")
            return

        game.inning += 1
        game.half = "초"

        if game.inning > 12:
            game.game_over = True
            add_log(game, "12회 종료: 무승부")


def play_plate_appearance(game: LiveGame) -> None:
    if game.game_over:
        return

    batting_team, fielding_team = current_teams(game)
    ensure_inning(batting_team, game.inning)
    ensure_inning(fielding_team, game.inning)

    batter = batting_team.lineup[batting_team.batting_index]
    pitcher = fielding_team.pitcher

    batting_team.batting_index = (
        batting_team.batting_index + 1
    ) % 9

    batter.pa += 1
    pitcher.batters_faced += 1

    result = choose_result(batter, pitcher)
    scored = 0
    result_text = ""

    if result == "BB":
        batter.bb += 1
        pitcher.walks_allowed += 1
        scored = advance_walk(
            game,
            batting_team,
            pitcher,
            batter,
        )
        result_text = "볼넷"

    elif result == "SO":
        batter.ab += 1
        batter.so += 1
        pitcher.so += 1
        pitcher.outs_recorded += 1
        game.outs += 1
        result_text = "삼진"

    elif result == "OUT":
        batter.ab += 1

        if (
            game.bases[0] is not None
            and game.outs < 2
            and random.random() < 0.12
        ):
            game.bases[0] = None
            game.outs += 2
            pitcher.outs_recorded += 2
            result_text = "병살타"
        else:
            game.outs += 1
            pitcher.outs_recorded += 1
            result_text = "범타"

    else:
        batter.ab += 1
        batter.h += 1
        pitcher.hits_allowed += 1

        bases_gained = {
            "1B": 1,
            "2B": 2,
            "3B": 3,
            "HR": 4,
        }[result]

        if result == "2B":
            batter.doubles += 1
        elif result == "3B":
            batter.triples += 1
        elif result == "HR":
            batter.hr += 1

        scored = advance_hit(
            game,
            batting_team,
            pitcher,
            batter,
            bases_gained,
        )

        result_text = {
            "1B": "안타",
            "2B": "2루타",
            "3B": "3루타",
            "HR": "홈런",
        }[result]

    add_log(
        game,
        f"{game.inning}회{game.half} | "
        f"{batter.name}: {result_text}"
        + (f" · {scored}득점" if scored else ""),
    )

    check_end_or_change_half(game)


def play_half_inning(game: LiveGame) -> None:
    inning = game.inning
    half = game.half
    safety = 0

    while (
        not game.game_over
        and game.inning == inning
        and game.half == half
        and safety < 100
    ):
        play_plate_appearance(game)
        safety += 1


def play_full_game(game: LiveGame) -> None:
    safety = 0
    while not game.game_over and safety < 1000:
        play_plate_appearance(game)
        safety += 1


def replace_batter(
    team: TeamGameState,
    lineup_index: int,
    bench_index: int,
) -> str:
    incoming = team.bench.pop(bench_index)
    outgoing = team.lineup[lineup_index]

    incoming.used = True
    incoming.lineup_slot = outgoing.lineup_slot
    team.lineup[lineup_index] = incoming

    return (
        f"대타·수비 교체: {outgoing.name}({outgoing.lineup_slot}) → "
        f"{incoming.name}({incoming.lineup_slot}) "
        f"({lineup_index + 1}번 타순)"
    )


def replace_pitcher(
    team: TeamGameState,
    pitcher_index: int,
) -> str:
    if pitcher_index == team.current_pitcher_index:
        return "현재 투수와 같은 선수입니다."

    incoming = team.pitchers[pitcher_index]

    if incoming.used:
        return "이미 등판한 투수는 다시 투입할 수 없습니다."

    outgoing = team.pitcher
    incoming.used = True
    team.current_pitcher_index = pitcher_index

    return f"투수 교체: {outgoing.name} → {incoming.name}"


def apply_season_result(
    season: SeasonState,
    scheduled: ScheduledGame,
    away_score: int,
    home_score: int,
) -> None:
    if scheduled.played:
        return

    scheduled.played = True
    scheduled.away_score = away_score
    scheduled.home_score = home_score

    away = season.records[scheduled.away]
    home = season.records[scheduled.home]

    away.runs_for += away_score
    away.runs_against += home_score
    home.runs_for += home_score
    home.runs_against += away_score

    if away_score > home_score:
        away.wins += 1
        home.losses += 1
    elif home_score > away_score:
        home.wins += 1
        away.losses += 1
    else:
        away.draws += 1
        home.draws += 1


def finalize_user_game(season: SeasonState) -> None:
    game = season.active_game

    if game is None or not game.game_over or game.finalized:
        return

    scheduled = next(
        item for item in season.schedule
        if item.game_id == game.game_id
    )

    apply_season_result(
        season,
        scheduled,
        game.away.score,
        game.home.score,
    )

    game.finalized = True
    season.pending_date_simulation = game.game_date


def poisson_sample(lam: float, rng: random.Random) -> int:
    limit = math.exp(-lam)
    product = 1.0
    count = 0

    while product > limit:
        count += 1
        product *= rng.random()

    return count - 1


def expected_runs(
    offense: int,
    opponent_pitching: int,
    opponent_defense: int,
    home_bonus: float,
) -> float:
    edge = (
        (offense - opponent_pitching) * 0.035
        + (50 - opponent_defense) * 0.012
    )
    return max(2.2, min(7.5, 4.55 + edge + home_bonus))


def simulate_other_game(
    away: str,
    home: str,
    ratings: Dict[str, Dict[str, int]],
    seed: int,
) -> Tuple[int, int]:
    rng = random.Random(seed)

    away_runs = poisson_sample(
        expected_runs(
            ratings[away]["offense"],
            ratings[home]["pitching"],
            ratings[home]["defense"],
            0.0,
        ),
        rng,
    )

    home_runs = poisson_sample(
        expected_runs(
            ratings[home]["offense"],
            ratings[away]["pitching"],
            ratings[away]["defense"],
            0.18,
        ),
        rng,
    )

    if away_runs == home_runs and rng.random() < 0.70:
        if rng.random() < 0.48:
            away_runs += 1
        else:
            home_runs += 1

    return away_runs, home_runs


def advance_to_next_game(season: SeasonState) -> None:
    target_date = season.pending_date_simulation

    if target_date is None:
        return

    results = []

    for scheduled in season.schedule:
        if scheduled.game_date != target_date:
            continue

        if scheduled.played:
            results.append({
                "날짜": scheduled.game_date,
                "원정": scheduled.away,
                "원정점수": scheduled.away_score,
                "홈점수": scheduled.home_score,
                "홈": scheduled.home,
                "구분": (
                    "플레이어 경기"
                    if scheduled.user_game
                    else "완료"
                ),
            })
            continue

        away_score, home_score = simulate_other_game(
            scheduled.away,
            scheduled.home,
            season.ratings,
            seed=scheduled.game_id * 1009,
        )

        apply_season_result(
            season,
            scheduled,
            away_score,
            home_score,
        )

        results.append({
            "날짜": scheduled.game_date,
            "원정": scheduled.away,
            "원정점수": away_score,
            "홈점수": home_score,
            "홈": scheduled.home,
            "구분": "자동 시뮬레이션",
        })

    season.last_round_results = results
    season.pending_date_simulation = None
    season.active_game = None

    start_next_live_game(season)


def standings_dataframe(season: SeasonState) -> pd.DataFrame:
    records = list(season.records.values())
    records.sort(
        key=lambda item: (
            item.pct,
            item.wins,
            item.runs_for - item.runs_against,
        ),
        reverse=True,
    )

    leader = records[0]
    rows = []

    for rank, record in enumerate(records, start=1):
        games_behind = (
            (
                leader.wins - record.wins
                + record.losses - leader.losses
            )
            / 2
        )

        rows.append({
            "순위": rank,
            "팀": record.team,
            "경기": record.games,
            "승": record.wins,
            "패": record.losses,
            "무": record.draws,
            "승률": f"{record.pct:.3f}",
            "게임차": "-" if rank == 1 else f"{games_behind:.1f}",
            "득점": record.runs_for,
            "실점": record.runs_against,
        })

    return pd.DataFrame(rows)


def scoreboard_dataframe(game: LiveGame) -> pd.DataFrame:
    max_innings = max(
        9,
        game.inning,
        len(game.away.inning_runs),
        len(game.home.inning_runs),
    )

    away_runs = game.away.inning_runs + [""] * (
        max_innings - len(game.away.inning_runs)
    )
    home_runs = game.home.inning_runs + [""] * (
        max_innings - len(game.home.inning_runs)
    )

    data = {"팀": [game.away.name, game.home.name]}

    for index in range(max_innings):
        data[str(index + 1)] = [
            away_runs[index],
            home_runs[index],
        ]

    data["R"] = [game.away.score, game.home.score]
    return pd.DataFrame(data)


def lineup_dataframe(team: TeamGameState) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "타순": index + 1,
            "수비": player.lineup_slot,
            "실제포지션": player.primary_position,
            "가능수비": player.eligible_positions,
            "실제기록": "Y" if player.rating_is_actual else "확인필요",
            "선수": player.name,
            "컨택": player.contact,
            "파워": player.power,
            "선구안": player.discipline,
            "주력": player.speed,
            "타수": player.ab,
            "안타": player.h,
            "홈런": player.hr,
            "볼넷": player.bb,
            "삼진": player.so,
            "타점": player.rbi,
            "타율": f"{player.avg:.3f}",
        }
        for index, player in enumerate(team.lineup)
    ])


def bases_text(bases: List[Optional[Player]]) -> str:
    occupied = []

    if bases[0]:
        occupied.append("1루")
    if bases[1]:
        occupied.append("2루")
    if bases[2]:
        occupied.append("3루")

    return " · ".join(occupied) if occupied else "주자 없음"


def render_base_diamond(bases: List[Optional[Player]]) -> None:
    def cls(index: int) -> str:
        return "base occupied" if bases[index] is not None else "base empty"

    def label(index: int, text: str) -> str:
        runner = bases[index].name if bases[index] is not None else text
        return runner

    html = f"""
    <style>
    .field-wrap {{ width: 230px; height: 170px; position: relative; margin: 4px 0 16px 0; }}
    .base {{ position:absolute; width:54px; height:54px; transform:rotate(45deg);
             border:2px solid #ddd; border-radius:6px; display:flex; align-items:center; justify-content:center;
             font-weight:700; background:#272b30; }}
    .base span {{ transform:rotate(-45deg); font-size:11px; text-align:center; line-height:1.05; max-width:72px; }}
    .occupied {{ background:#ff4b4b; color:white; border-color:#ffb3b3; }}
    .empty {{ color:#d7d7d7; }}
    .b1 {{ left:145px; top:75px; }}
    .b2 {{ left:88px; top:18px; }}
    .b3 {{ left:31px; top:75px; }}
    .home {{ position:absolute; left:88px; top:132px; width:54px; height:20px; text-align:center; color:#aaa; font-size:12px; }}
    .line {{ position:absolute; left:54px; top:52px; width:122px; height:122px; border:1px dashed #555; transform:rotate(45deg); }}
    </style>
    <div class="field-wrap">
      <div class="line"></div>
      <div class="base b2 {cls(1)}"><span>{label(1, '2루')}</span></div>
      <div class="base b1 {cls(0)}"><span>{label(0, '1루')}</span></div>
      <div class="base b3 {cls(2)}"><span>{label(2, '3루')}</span></div>
      <div class="home">HOME</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def season_to_json(season: SeasonState) -> str:
    return json.dumps(
        asdict(season),
        ensure_ascii=False,
        indent=2,
    )


def season_from_json(text: str) -> SeasonState:
    raw = json.loads(text)

    schedule = [
        ScheduledGame(**item)
        for item in raw["schedule"]
    ]

    records = {
        team: TeamRecord(**record)
        for team, record in raw["records"].items()
    }

    active_raw = raw.get("active_game")
    active_game = None

    if active_raw:
        def load_player(item):
            return Player(**item)

        def load_team(item):
            return TeamGameState(
                name=item["name"],
                lineup=[load_player(p) for p in item["lineup"]],
                bench=[load_player(p) for p in item["bench"]],
                pitchers=[load_player(p) for p in item["pitchers"]],
                current_pitcher_index=item["current_pitcher_index"],
                batting_index=item["batting_index"],
                score=item["score"],
                inning_runs=item["inning_runs"],
            )

        active_game = LiveGame(
            game_id=active_raw["game_id"],
            game_date=active_raw["game_date"],
            away=load_team(active_raw["away"]),
            home=load_team(active_raw["home"]),
            inning=active_raw["inning"],
            half=active_raw["half"],
            outs=active_raw["outs"],
            bases=[
                load_player(p) if p else None
                for p in active_raw["bases"]
            ],
            game_over=active_raw["game_over"],
            finalized=active_raw["finalized"],
            logs=active_raw["logs"],
        )

    return SeasonState(
        selected_team=raw["selected_team"],
        schedule=schedule,
        records=records,
        ratings=raw["ratings"],
        active_game=active_game,
        pending_date_simulation=raw.get(
            "pending_date_simulation"
        ),
        last_round_results=raw.get(
            "last_round_results", []
        ),
        season_finished=raw.get(
            "season_finished", False
        ),
    )


if "schedule_df" not in st.session_state:
    schedule_path = find_data_file("schedule_2026_fixed.csv")
    if schedule_path is not None:
        st.session_state.schedule_df = pd.read_csv(schedule_path)
    else:
        st.warning(
            "schedule_2026_fixed.csv 파일을 찾지 못해서 내장 대체 일정을 사용합니다. "
            "GitHub 저장소에 schedule_2026_fixed.csv를 함께 올리면 실제 고정 일정이 적용됩니다."
        )
        st.session_state.schedule_df = generate_schedule()

if "season" not in st.session_state:
    st.session_state.season = None


st.title("⚾ KBO 감독 시즌 시뮬레이터 v6")
st.caption(
    "사용자 팀 경기는 포지션별 선발 라인업으로 직접 진행하고 선수 교체를 지시합니다. "
    "같은 날짜의 다른 경기들은 다음 경기로 넘어갈 때 계산됩니다."
)

with st.sidebar:
    st.header("시즌 설정")

    uploaded_schedule = st.file_uploader(
        "일정 CSV",
        type=["csv"],
        help="필수 열: date, away, home",
    )

    if uploaded_schedule is not None:
        try:
            st.session_state.schedule_df = validate_schedule(
                pd.read_csv(uploaded_schedule)
            )
            st.success("일정을 불러왔습니다.")
        except Exception as exc:
            st.error(str(exc))

    selected_team = st.selectbox(
        "플레이할 팀",
        KBO_TEAMS,
        index=3,
    )

    if st.button("새 시즌 시작", use_container_width=True):
        season = new_season(
            selected_team,
            validate_schedule(st.session_state.schedule_df),
        )
        start_next_live_game(season)
        st.session_state.season = season
        st.rerun()

    season = st.session_state.season

    if season is not None:
        st.divider()
        st.download_button(
            "시즌 저장",
            data=season_to_json(season),
            file_name="kbo_season_save.json",
            mime="application/json",
            use_container_width=True,
        )

    uploaded_save = st.file_uploader(
        "시즌 불러오기",
        type=["json"],
        key="save_upload",
    )

    if uploaded_save is not None:
        try:
            st.session_state.season = season_from_json(
                uploaded_save.read().decode("utf-8")
            )
            st.success("시즌을 불러왔습니다.")
        except Exception as exc:
            st.error(f"저장 파일 오류: {exc}")


if st.session_state.season is None:
    st.info("왼쪽에서 팀을 선택하고 새 시즌을 시작하세요.")
    st.stop()


season: SeasonState = st.session_state.season
game = season.active_game

record = season.records[season.selected_team]

top1, top2, top3 = st.columns(3)
top1.metric("내 팀", season.selected_team)
top2.metric(
    "전적",
    f"{record.wins}승 {record.losses}패 {record.draws}무",
)
top3.metric("승률", f"{record.pct:.3f}")


game_tab, standings_tab, results_tab, roster_tab = st.tabs(
    ["내 경기", "순위표", "직전 경기일 결과", "선수 능력치"]
)

with game_tab:
    if season.season_finished:
        st.success("정규시즌 일정을 모두 마쳤습니다.")
    elif game is None:
        st.warning("진행할 경기를 불러오지 못했습니다.")
    else:
        st.subheader(
            f"{game.game_date} · {game.away.name} vs {game.home.name}"
        )

        st.dataframe(
            scoreboard_dataframe(game),
            hide_index=True,
            use_container_width=True,
        )

        info1, info2, info3, info4 = st.columns(4)
        info1.metric("이닝", f"{game.inning}회 {game.half}")
        info2.metric("아웃", game.outs)
        info3.metric("주자", bases_text(game.bases))
        info4.metric(
            "점수",
            f"{game.away.score}:{game.home.score}",
        )

        render_base_diamond(game.bases)

        batting_team, fielding_team = current_teams(game)
        current_batter = batting_team.lineup[
            batting_team.batting_index
        ]

        st.info(
            f"타자: **{current_batter.name}** ({current_batter.lineup_slot})　|　"
            f"투수: **{fielding_team.pitcher.name}**"
        )

        if not game.game_over:
            button1, button2, button3 = st.columns(3)

            with button1:
                if st.button(
                    "한 타석 진행",
                    use_container_width=True,
                ):
                    play_plate_appearance(game)
                    st.rerun()

            with button2:
                if st.button(
                    "반 이닝 진행",
                    use_container_width=True,
                ):
                    play_half_inning(game)
                    st.rerun()

            with button3:
                if st.button(
                    "경기 끝까지 진행",
                    use_container_width=True,
                ):
                    play_full_game(game)
                    st.rerun()

            st.divider()
            st.subheader("선수 교체")

            user_team = (
                game.away
                if game.away.name == season.selected_team
                else game.home
            )

            pinch_tab, pitcher_tab = st.tabs(
                ["대타 교체", "투수 교체"]
            )

            with pinch_tab:
                if user_team.bench:
                    lineup_options = {
                        f"{i + 1}번 {player.name}": i
                        for i, player in enumerate(user_team.lineup)
                    }
                    selected_lineup = st.selectbox(
                        "교체할 타순",
                        list(lineup_options),
                    )
                    target_index = lineup_options[selected_lineup]
                    target_slot = user_team.lineup[target_index].lineup_slot
                    allowed = set(SLOT_POSITION_RULES.get(target_slot, LINEUP_SLOTS))
                    filtered_bench = {
                        f"{player.name} ({player.primary_position}/{player.eligible_positions})": i
                        for i, player in enumerate(user_team.bench)
                        if eligible_set(player.eligible_positions) & allowed
                    }
                    if not filtered_bench:
                        st.warning(
                            f"{target_slot} 자리에 들어갈 수 있는 벤치 선수가 없습니다. "
                            "eligible_positions 열에 해당 수비위치가 있는 선수만 투입됩니다."
                        )
                    else:
                        selected_bench = st.selectbox(
                            "투입할 벤치 선수",
                            list(filtered_bench),
                        )

                        if st.button("대타·수비 교체 확정"):
                            message = replace_batter(
                                user_team,
                                target_index,
                                filtered_bench[selected_bench],
                            )
                            add_log(game, message)
                            st.rerun()
                else:
                    st.write("사용 가능한 벤치 타자가 없습니다.")

            with pitcher_tab:
                available_pitchers = {
                    player.name: index
                    for index, player in enumerate(user_team.pitchers)
                    if not player.used
                }

                if available_pitchers:
                    selected_pitcher = st.selectbox(
                        "등판할 투수",
                        list(available_pitchers),
                    )

                    if st.button("투수 교체 확정"):
                        message = replace_pitcher(
                            user_team,
                            available_pitchers[selected_pitcher],
                        )
                        add_log(game, message)
                        st.rerun()
                else:
                    st.write("사용 가능한 투수가 없습니다.")

        if game.game_over:
            finalize_user_game(season)

            if game.away.score > game.home.score:
                winner = game.away.name
            elif game.home.score > game.away.score:
                winner = game.home.name
            else:
                winner = "무승부"

            st.success(
                f"경기 종료 · {winner} · "
                f"{game.away.score}:{game.home.score}"
            )

            st.warning(
                "아직 다른 구장의 경기는 진행되지 않았습니다. "
                "아래 버튼을 누르면 같은 날짜의 나머지 경기들을 "
                "시뮬레이션하고 다음 내 경기로 넘어갑니다."
            )

            if st.button(
                "다른 경기 시뮬레이션 후 다음 경기로",
                type="primary",
                use_container_width=True,
            ):
                advance_to_next_game(season)
                st.rerun()

        detail1, detail2, detail3 = st.tabs(
            ["중계 기록", "원정팀 기록", "홈팀 기록"]
        )

        with detail1:
            for line in reversed(game.logs[-40:]):
                st.write(line)

        with detail2:
            st.dataframe(
                lineup_dataframe(game.away),
                hide_index=True,
                use_container_width=True,
            )
            st.write(
                f"현재 투수: {game.away.pitcher.name} · "
                f"{game.away.pitcher.innings}이닝 · "
                f"{game.away.pitcher.so}K · "
                f"{game.away.pitcher.runs_allowed}실점"
            )

        with detail3:
            st.dataframe(
                lineup_dataframe(game.home),
                hide_index=True,
                use_container_width=True,
            )
            st.write(
                f"현재 투수: {game.home.pitcher.name} · "
                f"{game.home.pitcher.innings}이닝 · "
                f"{game.home.pitcher.so}K · "
                f"{game.home.pitcher.runs_allowed}실점"
            )


with standings_tab:
    st.dataframe(
        standings_dataframe(season),
        hide_index=True,
        use_container_width=True,
    )


with results_tab:
    if season.last_round_results:
        st.dataframe(
            pd.DataFrame(season.last_round_results),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.write(
            "첫 경기 종료 후 다음 경기로 넘어가면 "
            "해당 날짜의 전체 결과가 표시됩니다."
        )


with roster_tab:
    st.subheader(f"{season.selected_team} 선수 능력치")
    display_cols = ["name", "position", "role", "contact", "power", "discipline", "speed", "stuff", "control", "stamina", "rating_source"]
    team_ratings = PLAYER_DATABASE[PLAYER_DATABASE["team"] == season.selected_team][display_cols].copy()
    team_ratings.columns = ["선수", "포지션", "역할", "컨택", "파워", "선구안", "주력", "구위", "제구", "체력", "산정 방식"]
    st.dataframe(team_ratings, hide_index=True, use_container_width=True)
    st.caption("규정 타석·규정 이닝권 선수는 2026 성적 기반, 그 외 선수는 리그 평균 회귀값입니다.")
