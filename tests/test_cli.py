"""cmd_run の機能テスト(手動ステップ / 作業者記録 / 実行前確認 / RB-ONFAIL / 切り戻し)"""

import json
import textwrap

import pytest

from runbook import cli


def write_md(tmp_path, text, name="proc.md"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def feed_input(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda: next(it))


def read_result(log_dir):
    dirs = list(log_dir.iterdir())
    assert len(dirs) == 1
    return dirs[0], json.loads((dirs[0] / "result.json").read_text(encoding="utf-8"))


SIMPLE_MD = """\
    # テスト

    ## S1

    ### RB-CMD
    ```bash
    true
    ```
"""


def test_run_records_operator_and_checker(tmp_path):
    md = write_md(tmp_path, SIMPLE_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田", "--checker", "田中",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    _, result = read_result(tmp_path / "logs")
    assert result["procedure"]["operator"] == "山田"
    assert result["procedure"]["checker"] == "田中"
    assert result["status"] == "completed"


def test_operator_prompted_when_not_given(tmp_path, monkeypatch):
    md = write_md(tmp_path, SIMPLE_MD)
    # 入力順: 作業者名 → 確認者名(スキップ)
    feed_input(monkeypatch, ["鈴木", ""])
    rc = cli.main(["run", str(md), "--yes", "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    _, result = read_result(tmp_path / "logs")
    assert result["procedure"]["operator"] == "鈴木"
    assert result["procedure"]["checker"] == ""


def test_summary_gate_abort(tmp_path, monkeypatch):
    """実行前確認で y 以外を入力すると実行されない(ログも作られない)"""
    md = write_md(tmp_path, SIMPLE_MD)
    feed_input(monkeypatch, ["n"])
    rc = cli.main(["run", str(md), "--operator", "山田", "--log-dir", str(tmp_path / "logs")])
    assert rc == 130
    assert not (tmp_path / "logs").exists()


def test_summary_gate_accept(tmp_path, monkeypatch):
    md = write_md(tmp_path, SIMPLE_MD)
    feed_input(monkeypatch, ["y"])
    rc = cli.main(["run", str(md), "--operator", "山田", "--log-dir", str(tmp_path / "logs")])
    assert rc == 0


MANUAL_MD = """\
    ## 目視確認

    ### RB-DESCRIPTION
    監視画面で異常がないことを確認する。

    ## コマンド

    ### RB-CMD
    ```bash
    echo done
    ```
"""


def test_manual_step_confirmed(tmp_path, monkeypatch):
    md = write_md(tmp_path, MANUAL_MD)
    feed_input(monkeypatch, ["y"])  # 手動ステップの完了確認
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    _, result = read_result(tmp_path / "logs")
    s1 = result["steps"][0]
    assert s1["status"] == "ok"
    assert "完了を確認" in s1["detail"]
    assert s1["finished_at"]  # 確認時刻が記録される


def test_manual_step_quit_aborts(tmp_path, monkeypatch):
    md = write_md(tmp_path, MANUAL_MD)
    feed_input(monkeypatch, ["q"])
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 130
    _, result = read_result(tmp_path / "logs")
    assert result["status"] == "aborted"
    assert len(result["steps"]) == 1  # 後続のコマンドステップは実行されない


ONFAIL_MD = """\
    ## 失敗するステップ

    ### RB-CMD
    ```bash
    false
    ```

    ### RB-ONFAIL
    DB の接続数を確認し、復旧しない場合は佐藤さんへエスカレーション。
"""


def test_onfail_guidance_logged_on_failure(tmp_path):
    md = write_md(tmp_path, ONFAIL_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    log_dir, result = read_result(tmp_path / "logs")
    assert result["status"] == "aborted"
    run_log = (log_dir / "run.log").read_text(encoding="utf-8")
    assert "エスカレーション" in run_log


ROLLBACK_MD = """\
    ## 本作業

    ### RB-CMD
    ```bash
    false
    ```

    # RB-ROLLBACK

    ## 切り戻し

    ### RB-CMD
    ```bash
    echo rolled back
    ```
"""


def test_rollback_hint_on_abort(tmp_path, capsys):
    md = write_md(tmp_path, ROLLBACK_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    log_dir, _ = read_result(tmp_path / "logs")
    run_log = (log_dir / "run.log").read_text(encoding="utf-8")
    assert "--rollback" in run_log  # 切り戻し案内が記録される
    assert "--rollback" in capsys.readouterr().out


def test_rollback_run_executes_rollback_steps(tmp_path):
    md = write_md(tmp_path, ROLLBACK_MD)
    rc = cli.main(["run", "--rollback", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    log_dir, result = read_result(tmp_path / "logs")
    assert log_dir.name.startswith("proc_rollback_")
    assert result["procedure"]["rollback"] is True
    assert [s["title"] for s in result["steps"]] == ["切り戻し"]
    assert result["status"] == "completed"


def test_rollback_flag_without_section_is_error(tmp_path):
    md = write_md(tmp_path, SIMPLE_MD)
    rc = cli.main(["run", "--rollback", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 2


def test_operator_required_without_tty(tmp_path, monkeypatch):
    """非対話環境(入力EOF)で --operator がなければエラー終了"""
    md = write_md(tmp_path, SIMPLE_MD)

    def raise_eof():
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    rc = cli.main(["run", str(md), "--yes", "--log-dir", str(tmp_path / "logs")])
    assert rc == 2
    assert not (tmp_path / "logs").exists()


BREAKDOWN_MD = """\
    ## 複合条件で失敗

    ### RB-CMD
    ```bash
    echo "OK but ERROR"
    ```

    ### RB-EXPECTED
    ```
    rc == 0 and out("OK") and not out("ERROR")
    ```
"""


def test_criteria_breakdown_on_ng(tmp_path):
    """NG時に判定内訳(どの条件で落ちたか)が run.log と result.json に残る"""
    md = write_md(tmp_path, BREAKDOWN_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    log_dir, result = read_result(tmp_path / "logs")
    breakdown = result["steps"][0]["criteria_breakdown"]
    assert {b["expr"]: b["ok"] for b in breakdown} == {
        "rc == 0": True,
        'out("OK")': True,
        'not out("ERROR")': False,
    }
    run_log = (log_dir / "run.log").read_text(encoding="utf-8")
    assert '[NG] not out("ERROR")' in run_log
    assert "[OK] rc == 0" in run_log


def test_criteria_breakdown_absent_for_single_condition(tmp_path):
    """条件が1つだけの基準式では内訳を出さない(基準式そのものと同じ情報)"""
    md = write_md(tmp_path, """\
        ## 失敗

        ### RB-CMD
        ```bash
        false
        ```
    """)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    _, result = read_result(tmp_path / "logs")
    assert result["steps"][0]["criteria_breakdown"] == []


def test_check_warns_missing_inventory_and_playbook(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    md = write_md(tmp_path, """\
        ## ansible ステップ

        ### RB-CMD
        ```ansible
        uptime
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: no_such_inventory.ini
          target: web
        ```

        ## playbook ステップ

        ### RB-CMD
        ```playbook
        -i no_such_inventory2.ini no_such_playbook.yml
        ```
    """)
    rc = cli.main(["check", str(md)])
    assert rc == 0  # パス不存在は警告(実行時と check 時で cwd が違う場合があるため)
    out = capsys.readouterr().out
    assert "no_such_inventory.ini が見つかりません" in out
    assert "no_such_inventory2.ini が見つかりません" in out
    assert "no_such_playbook.yml が見つかりません" in out
    assert "警告 3 件" in out


def test_check_existing_paths_no_warning(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "hosts.ini").write_text("web01 ansible_connection=local\n", encoding="utf-8")
    (tmp_path / "site.yml").write_text("- hosts: all\n  tasks: []\n", encoding="utf-8")
    md = write_md(tmp_path, """\
        ## playbook ステップ

        ### RB-CMD
        ```playbook
        -i hosts.ini site.yml
        ```
    """)
    rc = cli.main(["check", str(md)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "警告" not in out


def test_check_warns_missing_cwd(tmp_path, capsys):
    md = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```

        ### RB-LOCALDEF
        ```yaml
        cwd: /no/such/dir
        ```
    """)
    rc = cli.main(["check", str(md)])
    assert rc == 0
    assert "cwd /no/such/dir が存在しません" in capsys.readouterr().out


def test_check_inline_host_list_not_checked(tmp_path, capsys):
    """カンマ入りインベントリ(インラインホストリスト)はパスとして扱わない"""
    md = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```ansible
        ansible all -i web01,
        uptime
        ```
    """)
    rc = cli.main(["check", str(md)])
    assert rc == 0
    assert "警告" not in capsys.readouterr().out


def test_check_preview_shows_expanded_commands(tmp_path, capsys):
    md = write_md(tmp_path, """\
        ```runbook
        vars:
          HOST: web01
        ```

        ## コマンド

        ### RB-CMD
        ```bash
        echo {{HOST}}
        ```

        ## 目視確認

        ### RB-DESCRIPTION
        画面を確認する。

        # RB-ROLLBACK

        ## 戻し

        ### RB-CMD
        ```bash
        echo rollback
        ```
    """)
    rc = cli.main(["check", "--preview", str(md)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "$ echo web01" in out  # 変数展開後のコマンド
    assert "手動ステップ" in out
    assert "切り戻しセクション" in out
    assert "$ echo rollback" in out


SECRET_MD = """\
    ```runbook
    vars:
      API_TOKEN: s3cret-value-xyz
      HOST: web01
    secrets: [API_TOKEN]
    ```

    ## トークンを使う

    ### RB-CMD
    ```bash
    echo "token={{API_TOKEN}} host={{HOST}}"
    ```

    ### RB-EXPECTED
    ```
    rc == 0 and out("s3cret-value-xyz") and out("web01")
    ```
"""


def test_secret_masked_everywhere(tmp_path, capsys):
    """secrets 宣言した変数の値が画面・run.log・result.json・生出力から消える"""
    md = write_md(tmp_path, SECRET_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0  # 判定は生の出力に対して行われる(マスクは表示・ログのみ)
    out = capsys.readouterr().out
    assert "s3cret-value-xyz" not in out
    assert "*****" in out
    assert "web01" in out  # 非シークレット変数はマスクされない
    log_dir, result = read_result(tmp_path / "logs")
    for f in ("run.log", "result.json", "step01_stdout.txt"):
        content = (log_dir / f).read_text(encoding="utf-8")
        assert "s3cret-value-xyz" not in content, f
    assert result["procedure"]["vars"]["API_TOKEN"] == "*****"
    assert result["procedure"]["vars"]["HOST"] == "web01"
    assert (log_dir / "step01_stdout.txt").read_text(encoding="utf-8") == "token=***** host=web01\n"


def test_secret_masked_in_breakdown(tmp_path, capsys):
    """NG時の判定内訳でも基準式中のシークレット値がマスクされる"""
    md = write_md(tmp_path, """\
        ```runbook
        vars:
          API_TOKEN: s3cret-value-xyz
        secrets: [API_TOKEN]
        ```

        ## 失敗させる

        ### RB-CMD
        ```bash
        echo no-token-here
        ```

        ### RB-EXPECTED
        ```
        rc == 0 and out("{{API_TOKEN}}")
        ```
    """)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "s3cret-value-xyz" not in out
    log_dir, result = read_result(tmp_path / "logs")
    bd = result["steps"][0]["criteria_breakdown"]
    assert any(b["expr"] == 'out("*****")' and not b["ok"] for b in bd)
    assert "s3cret-value-xyz" not in (log_dir / "run.log").read_text(encoding="utf-8")


def test_secret_masked_in_list_and_preview(tmp_path, capsys):
    md = write_md(tmp_path, SECRET_MD)
    assert cli.main(["list", str(md)]) == 0
    assert cli.main(["check", "--preview", str(md)]) == 0
    out = capsys.readouterr().out
    assert "s3cret-value-xyz" not in out
    assert "*****" in out


START_FROM_MD = """\
    ## S1

    ### RB-CMD
    ```bash
    echo step1
    ```

    ## S2

    ### RB-CMD
    ```bash
    echo step2
    ```

    ## S3

    ### RB-CMD
    ```bash
    echo step3
    ```
"""


def test_start_from_runs_to_end(tmp_path):
    md = write_md(tmp_path, START_FROM_MD)
    rc = cli.main(["run", str(md), "--start-from", "2", "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    _, result = read_result(tmp_path / "logs")
    assert result["procedure"]["start_from"] == 2
    assert [s["number"] for s in result["steps"]] == [2, 3]


def test_start_from_conflicts_with_from(tmp_path):
    md = write_md(tmp_path, START_FROM_MD)
    rc = cli.main(["run", str(md), "--start-from", "2", "--from", "1",
                   "--yes", "--operator", "山田", "--log-dir", str(tmp_path / "logs")])
    assert rc == 2


def test_start_from_out_of_range(tmp_path):
    md = write_md(tmp_path, START_FROM_MD)
    rc = cli.main(["run", str(md), "--start-from", "9", "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 2


SHARE_ENV_MD = """\
    ```runbook
    share_env: true
    ```

    ## トークン取得

    ### RB-CMD
    ```bash
    export TOKEN=resumed-token-123
    ```

    ## トークン使用

    ### RB-CMD
    ```bash
    echo "got=$TOKEN"
    ```

    ### RB-EXPECTED
    ```
    out("got=resumed-token-123")
    ```
"""


def test_start_from_restores_shared_env(tmp_path):
    """share_env: true の手順書では --start-from が直近実行の環境変数を復元する"""
    md = write_md(tmp_path, SHARE_ENV_MD)
    logs = str(tmp_path / "logs")
    # 1回目: 全ステップ実行(step1 の export が shared_env.sh に残る)
    assert cli.main(["run", str(md), "--yes", "--operator", "山田", "--log-dir", logs]) == 0
    # 2回目: ステップ2から再開。復元された TOKEN で基準を満たす
    assert cli.main(["run", str(md), "--start-from", "2", "--yes", "--operator", "山田",
                     "--log-dir", logs]) == 0
    latest = sorted((tmp_path / "logs").iterdir())[-1]
    result = json.loads((latest / "result.json").read_text(encoding="utf-8"))
    assert result["procedure"]["start_from"] == 2
    assert result["procedure"]["resumed_env_from"]
    assert result["steps"][0]["status"] == "ok"


def test_start_from_share_env_without_previous_run_is_error(tmp_path):
    md = write_md(tmp_path, SHARE_ENV_MD)
    rc = cli.main(["run", str(md), "--start-from", "2", "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 2
    assert not (tmp_path / "logs").exists()
