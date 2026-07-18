import json
from datetime import datetime

import pytest

from runbook import artifacts as artifacts_mod
from runbook.artifacts import RunArtifacts, atomic_write_text
from runbook.executor import StepRecord


def make_record(**kwargs) -> StepRecord:
    defaults = dict(
        number=1,
        title="タイトル",
        command="echo hi",
        criteria="rc == 0",
        status="ok",
        rc=0,
        duration=0.123,
        started_at="2024-01-01T00:00:00",
        finished_at="2024-01-01T00:00:01",
        detail="",
        stdout="out\n",
        stderr="",
    )
    defaults.update(kwargs)
    return StepRecord(**defaults)


# ---- atomic_write_text ------------------------------------------------------

def test_atomic_write_text_writes_content(tmp_path):
    target = tmp_path / "f.txt"
    atomic_write_text(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_no_leftover_tmp_file(tmp_path):
    target = tmp_path / "f.txt"
    atomic_write_text(target, "hello\n")
    remaining = list(tmp_path.iterdir())
    assert remaining == [target]


def test_atomic_write_text_overwrites_existing_file(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("old content", encoding="utf-8")
    atomic_write_text(target, "new content")
    assert target.read_text(encoding="utf-8") == "new content"
    remaining = list(tmp_path.iterdir())
    assert remaining == [target]


# ---- mkdir 衝突(EEXIST ループ) ---------------------------------------------

def test_mkdir_collision_appends_suffix(tmp_path, monkeypatch):
    fixed = datetime(2024, 1, 1, 12, 0, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(artifacts_mod, "datetime", FixedDateTime)

    # 先に同名ディレクトリを衝突させておく
    (tmp_path / "proc_20240101_120000").mkdir()

    art = RunArtifacts("proc", base_dir=tmp_path)
    assert art.dir.name == "proc_20240101_120000_2"
    assert art.dir.exists()


def test_mkdir_collision_multiple_appends_suffix(tmp_path, monkeypatch):
    fixed = datetime(2024, 1, 1, 12, 0, 0)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(artifacts_mod, "datetime", FixedDateTime)

    (tmp_path / "proc_20240101_120000").mkdir()
    (tmp_path / "proc_20240101_120000_2").mkdir()

    art = RunArtifacts("proc", base_dir=tmp_path)
    assert art.dir.name == "proc_20240101_120000_3"


# ---- save_result / add_record / finalize ------------------------------------

def test_add_record_writes_running_result_json(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    art.meta = {"file": "x.md", "title": "テスト手順"}
    art.add_record(make_record())

    data = json.loads((art.dir / "result.json").read_text(encoding="utf-8"))
    assert data["status"] == "running"
    assert data["procedure"] == {"file": "x.md", "title": "テスト手順"}
    assert len(data["steps"]) == 1
    assert data["steps"][0]["number"] == 1
    # 生の出力は別ファイル管理のため result.json には含まれない
    assert "stdout" not in data["steps"][0]
    assert "stderr" not in data["steps"][0]


def test_finalize_updates_status_and_closes_log(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    art.add_record(make_record())
    returned_dir = art.finalize("completed")

    assert returned_dir == art.dir
    data = json.loads((art.dir / "result.json").read_text(encoding="utf-8"))
    assert data["status"] == "completed"

    log_text = (art.dir / "run.log").read_text(encoding="utf-8")
    assert "実行終了: completed" in log_text


def test_finalize_aborted_status(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    art.finalize("aborted")
    data = json.loads((art.dir / "result.json").read_text(encoding="utf-8"))
    assert data["status"] == "aborted"


def test_result_json_is_well_formed_after_each_add_record(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    for i in range(1, 4):
        art.add_record(make_record(number=i))
        # 各ステップ終了直後の時点で読んでも整形式 JSON であること
        data = json.loads((art.dir / "result.json").read_text(encoding="utf-8"))
        assert data["status"] == "running"
        assert len(data["steps"]) == i


# ---- StepFiles --------------------------------------------------------------

def test_step_files_readable_before_close_flush_check(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    files = art.open_step_files(1)
    files.write("out line 1\n", is_stderr=False)
    files.write("err line 1\n", is_stderr=True)

    # close() 前でも flush 済みのため読める
    assert (art.dir / "step01_stdout.txt").read_text(encoding="utf-8") == "out line 1\n"
    assert (art.dir / "step01_stderr.txt").read_text(encoding="utf-8") == "err line 1\n"

    files.write("out line 2\n", is_stderr=False)
    assert (art.dir / "step01_stdout.txt").read_text(encoding="utf-8") == (
        "out line 1\nout line 2\n"
    )

    files.close()


def test_step_files_number_zero_padded(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    files = art.open_step_files(7)
    files.write("x\n")
    files.close()
    assert (art.dir / "step07_stdout.txt").exists()
    assert (art.dir / "step07_stderr.txt").exists()


# ---- env_overlay.sh -----------------------------------------------------------

def test_write_env_overlay_creates_file_atomically(tmp_path):
    art = RunArtifacts("proc", base_dir=tmp_path)
    art.write_env_overlay("export FOO=bar\n")
    assert (art.dir / "env_overlay.sh").read_text(encoding="utf-8") == "export FOO=bar\n"


# ---- マスク適用 ----------------------------------------------------------------

def test_mask_applied_to_log_result_json_and_step_files(tmp_path):
    def mask(text: str) -> str:
        return text.replace("SECRET", "*****")

    art = RunArtifacts("proc", base_dir=tmp_path, mask=mask)
    art.log("token=SECRET")

    files = art.open_step_files(1)
    files.write(mask("value=SECRET\n"))
    files.close()

    art.add_record(make_record(detail="漏洩注意 SECRET を含む"))
    art.finalize("completed")

    log_text = (art.dir / "run.log").read_text(encoding="utf-8")
    assert "SECRET" not in log_text
    assert "*****" in log_text

    result_text = (art.dir / "result.json").read_text(encoding="utf-8")
    assert "SECRET" not in result_text
    assert "*****" in result_text

    step_text = (art.dir / "step01_stdout.txt").read_text(encoding="utf-8")
    assert "SECRET" not in step_text
    assert "*****" in step_text


def test_mask_not_applied_to_env_overlay(tmp_path):
    def mask(text: str) -> str:
        return text.replace("SECRET", "*****")

    art = RunArtifacts("proc", base_dir=tmp_path, mask=mask)
    art.write_env_overlay("export TOKEN=SECRET\n")
    content = (art.dir / "env_overlay.sh").read_text(encoding="utf-8")
    assert content == "export TOKEN=SECRET\n"
