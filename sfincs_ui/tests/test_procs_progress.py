import os
import signal
import subprocess
import sys
import time

import pytest

from sfincs_ui.services.procs import is_alive, killpg_graceful, proc_starttime
from sfincs_ui.services.progress import FINISHED_LINE, parse_progress, tail_lines


@pytest.fixture
def sleeper():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    yield proc
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def test_proc_starttime_and_is_alive(sleeper):
    st = proc_starttime(sleeper.pid)
    assert isinstance(st, int) and st > 0
    assert is_alive(sleeper.pid, st)
    assert not is_alive(sleeper.pid, st + 1)
    assert proc_starttime(2**22 - 1) is None and not is_alive(2**22 - 1, 1)


def test_proc_starttime_parses_comm_with_spaces_and_parens():
    # /proc/self/stat for a process named "a b) c" still parses: split after the LAST ')'
    st = proc_starttime(os.getpid())
    stat = open(f"/proc/{os.getpid()}/stat").read()
    assert st == int(stat.rsplit(")", 1)[1].split()[19])


def test_killpg_graceful_terminates_then_kills(sleeper):
    # the child ignores SIGTERM, so the helper must escalate to SIGKILL
    stubborn = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"],
                                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.5)
        assert killpg_graceful(sleeper.pid, grace_s=5) == "terminated"
        assert killpg_graceful(stubborn.pid, grace_s=1) == "killed"
        stubborn.wait()  # reap: a zombie still answers killpg, so "gone" needs the exit collected
        assert killpg_graceful(stubborn.pid, grace_s=1) == "gone"
    finally:
        for p in (sleeper, stubborn):
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGKILL)
            p.wait()


def test_parse_progress():
    assert parse_progress("") is None
    assert parse_progress("   0% complete,       - s remaining ...\n") == {"percent": 0, "remaining_s": None}
    text = "  15% complete,  1188.8 s remaining ...\n  20% complete,  1100.0 s remaining ...\n"
    assert parse_progress(text) == {"percent": 20, "remaining_s": 1100.0}
    assert FINISHED_LINE == "---------- Simulation finished -----------"


def test_tail_lines(tmp_path):
    assert tail_lines(tmp_path / "missing.log", 5) == ""
    p = tmp_path / "x.log"
    p.write_text("".join(f"line {i}\n" for i in range(1000)))
    out = tail_lines(p, 3)
    assert out == "line 997\nline 998\nline 999\n"
    assert tail_lines(p, 5000).startswith("line 0\n")
