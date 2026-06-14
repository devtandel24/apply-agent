import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_personal_paths_are_ignored():
    for p in [
        "profile/profile.yaml",
        "profile/master_resume.md",
        "data/jobs.csv",
        "data/portal_accounts.csv",
        "output/x.png",
    ]:
        r = subprocess.run(
            ["git", "check-ignore", p],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"{p} is NOT gitignored — would leak"


def test_demo_data_is_tracked():
    r = subprocess.run(
        ["git", "check-ignore", "data/demo_jobs.csv"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0, "data/demo_jobs.csv must be tracked (not ignored)"
