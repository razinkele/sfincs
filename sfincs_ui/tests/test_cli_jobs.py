import os
import signal
import subprocess
import sys

from sfincs_ui import __main__ as cli
from sfincs_ui.models import Job, Run
from sfincs_ui.services.procs import is_alive, proc_starttime
from tests.runner_helpers import make_run, run_row


def _job(db, run_id, pid, st, stage="simulate"):
    s = db()
    try:
        s.get(Run, run_id).status = "running"
        s.add(Job(run_id=run_id, stage=stage, status="running", pid=pid, proc_starttime=st, log_path=""))
        s.commit()
    finally:
        s.close()


def test_active_jobs_exit_codes(db, tmp_path, capsys):
    assert cli.main(["active-jobs"]) == 0
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.5})
    _job(db, run_id, 2**22 - 2, 123)  # dead pid
    assert cli.main(["active-jobs"]) == 2
    assert "alive=no" in capsys.readouterr().out
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        _job(db, run_id, proc.pid, proc_starttime(proc.pid))
        assert cli.main(["active-jobs"]) == 1
        out = capsys.readouterr().out
        assert f"pid={proc.pid}" in out and "alive=yes" in out and "simulate" in out
    finally:
        os.killpg(proc.pid, signal.SIGKILL); proc.wait()


def test_kill_jobs_terminates_and_cancels(db, tmp_path, capsys):
    run_id = make_run(db, tmp_path, "fake", {"alpha": 0.5})
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        st = proc_starttime(proc.pid)
        _job(db, run_id, proc.pid, st)
        assert cli.main(["kill-jobs"]) == 0
        proc.wait(timeout=5)
        assert not is_alive(proc.pid, st)
        row = run_row(db, run_id)
        assert row["status"] == "cancelled" and row["jobs"][-1]["status"] == "cancelled"
        assert f"{proc.pid}" in capsys.readouterr().out
        assert cli.main(["active-jobs"]) == 0
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL); proc.wait()
