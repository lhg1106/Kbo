from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import streamlit as st

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title="KBO 능력치 파일 생성기", page_icon="⚾")
st.title("⚾ KBO 직접 스탯 능력치 생성기")
st.write(
    "규정타석·규정이닝 필터 없이 2026 기록을 그대로 사용합니다. "
    "2026 기록이 아예 없는 선수만 2025 기록을 사용합니다."
)

files = {
    "hitter_stats_2026.csv": st.file_uploader("2026 전체 타자 CSV", type="csv", key="h26"),
    "pitcher_stats_2026.csv": st.file_uploader("2026 전체 투수 CSV", type="csv", key="p26"),
    "hitter_stats_2025.csv": st.file_uploader("2025 전체 타자 CSV", type="csv", key="h25"),
    "pitcher_stats_2025.csv": st.file_uploader("2025 전체 투수 CSV", type="csv", key="p25"),
}

if st.button("능력치 파일 생성", type="primary"):
    required = ["hitter_stats_2026.csv", "pitcher_stats_2026.csv"]
    missing = [name for name in required if files[name] is None]
    if missing:
        st.error("2026 전체 타자·투수 CSV는 필수입니다.")
    else:
        for name, uploaded in files.items():
            if uploaded is not None:
                (BASE / name).write_bytes(uploaded.getvalue())

        result = subprocess.run(
            [sys.executable, str(BASE / "build_player_ratings_direct.py")],
            cwd=BASE,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            st.error(result.stderr or result.stdout)
        else:
            st.success("생성 완료")
            st.code(result.stdout)
            output = BASE / "players_2026_direct_stats_positions.csv"
            report = BASE / "direct_stats_build_report.csv"
            st.download_button(
                "완성 선수 파일 다운로드",
                output.read_bytes(),
                file_name=output.name,
                mime="text/csv",
            )
            st.download_button(
                "매칭 리포트 다운로드",
                report.read_bytes(),
                file_name=report.name,
                mime="text/csv",
            )
