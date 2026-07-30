"""cmd_run の機能テスト(手動ステップ / 作業者記録 / 実行前確認 / RB-ONFAIL / 環境変数引き継ぎ)"""

import json
import os
import signal
import textwrap
import threading

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


def test_rollback_heading_is_parse_error(tmp_path):
    """v0.5.0 で切り戻し機能(# RB-ROLLBACK)は削除され、パースエラーになる"""
    md = write_md(tmp_path, """\
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
    """)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 2
    assert not (tmp_path / "logs").exists()


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


def test_check_preview_shows_two_parts(tmp_path, capsys):
    """check --preview は list と同一の一覧表(第1部)+ run と同一のステップ詳細(第2部)"""
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
    """)
    rc = cli.main(["check", "--preview", str(md)])
    assert rc == 0
    out = capsys.readouterr().out
    # 第1部: 一覧表(list と同形式)
    assert "コマンド" in out and "正常性基準" in out
    # 第2部: ステップ詳細(run と同形式)。手動ステップは未実行である旨の文言。
    assert "$ echo web01" in out  # 変数展開後のコマンド
    assert "作業者の完了確認のみ" in out


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


def test_secrets_summary_note_shown_unconditionally(tmp_path, monkeypatch, capsys):
    """環境変数引き継ぎは常時有効なので、secrets 宣言があれば無条件で注意表示する"""
    md = write_md(tmp_path, SECRET_MD)
    feed_input(monkeypatch, ["n"])  # ゲートで中止(サマリー表示だけ見る)
    rc = cli.main(["run", str(md), "--operator", "山田", "--log-dir", str(tmp_path / "logs")])
    assert rc == 130
    out = capsys.readouterr().out
    assert "env_overlay.sh に平文で残ります" in out


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
    # 1回目: env_overlay.sh を用意するため全ステップ実行しておく
    assert cli.main(["run", str(md), "--yes", "--operator", "山田",
                     "--log-dir", str(tmp_path / "logs")]) == 0
    rc = cli.main(["run", str(md), "--start-from", "2", "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    dirs = sorted((tmp_path / "logs").iterdir())
    result = json.loads((dirs[-1] / "result.json").read_text(encoding="utf-8"))
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


ENV_OVERLAY_MD = """\
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


def test_env_overlay_carries_export_to_next_step(tmp_path):
    """ステップ間の環境変数引き継ぎは常時有効(設定不要)。export した値が次ステップに見える"""
    md = write_md(tmp_path, ENV_OVERLAY_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    log_dir, result = read_result(tmp_path / "logs")
    assert result["steps"][1]["status"] == "ok"
    overlay = (log_dir / "env_overlay.sh").read_text(encoding="utf-8")
    assert "TOKEN" in overlay


UNSET_MD = """\
    ```runbook
    vars:
      DUMMY: x
    ```

    ## unset する

    ### RB-CMD
    ```bash
    unset DUMMY_ENV_VAR_FOR_TEST || true
    export DUMMY_ENV_VAR_FOR_TEST=seen
    ```

    ## 消えていることを確認

    ### RB-CMD
    ```bash
    unset DUMMY_ENV_VAR_FOR_TEST
    ```

    ## 3度目、tombstone が効いていること

    ### RB-CMD
    ```bash
    echo "value=${DUMMY_ENV_VAR_FOR_TEST:-gone}"
    ```

    ### RB-EXPECTED
    ```
    out("value=gone")
    ```
"""


def test_env_overlay_unset_tombstone_persists(tmp_path):
    """あるステップで unset した変数は、以降のステップにも unset のまま引き継がれる(tombstone)"""
    md = write_md(tmp_path, UNSET_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    _, result = read_result(tmp_path / "logs")
    assert result["steps"][-1]["status"] == "ok"


def test_start_from_restores_env_overlay(tmp_path):
    """--start-from が直近実行の env_overlay.sh(export/unset の差分)を復元する"""
    md = write_md(tmp_path, ENV_OVERLAY_MD)
    logs = str(tmp_path / "logs")
    # 1回目: 全ステップ実行(step1 の export が env_overlay.sh に残る)
    assert cli.main(["run", str(md), "--yes", "--operator", "山田", "--log-dir", logs]) == 0
    # 2回目: ステップ2から再開。復元された TOKEN で基準を満たす
    assert cli.main(["run", str(md), "--start-from", "2", "--yes", "--operator", "山田",
                     "--log-dir", logs]) == 0
    latest = sorted((tmp_path / "logs").iterdir())[-1]
    result = json.loads((latest / "result.json").read_text(encoding="utf-8"))
    assert result["procedure"]["start_from"] == 2
    assert result["procedure"]["resumed_env_from"]
    assert result["steps"][0]["status"] == "ok"
    assert "rollback" not in result["procedure"]
    assert "share_env" not in result["procedure"]


def test_start_from_without_previous_run_is_error(tmp_path):
    """環境変数引き継ぎは常時有効なので、過去実行がなければ --start-from は無条件でエラー"""
    md = write_md(tmp_path, ENV_OVERLAY_MD)
    rc = cli.main(["run", str(md), "--start-from", "2", "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 2
    assert not (tmp_path / "logs").exists()


def test_result_json_has_no_rollback_or_share_env_keys(tmp_path):
    md = write_md(tmp_path, SIMPLE_MD)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 0
    _, result = read_result(tmp_path / "logs")
    assert "rollback" not in result["procedure"]
    assert "share_env" not in result["procedure"]


SLEEP_MD = """\
    ## 長いステップ

    ### RB-CMD
    ```bash
    sleep 5
    ```
"""


def test_sigterm_during_step_aborts_with_143_and_finalizes(tmp_path):
    """ステップ実行中に SIGTERM を受信すると、証跡を確定した上で 128+15=143 で終了する"""
    md = write_md(tmp_path, SLEEP_MD)
    timer = threading.Timer(0.5, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.daemon = True
    timer.start()
    try:
        rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                       "--log-dir", str(tmp_path / "logs")])
    finally:
        timer.cancel()
    assert rc == 143
    log_dir, result = read_result(tmp_path / "logs")
    assert result["status"] == "aborted"
    assert result["steps"][0]["status"] == "error"
    assert "SIGTERM" in result["steps"][0]["detail"]


def test_check_warns_fenced_onfail_is_empty(tmp_path, capsys):
    """案R9: RB-ONFAIL をコードフェンスで囲むと内容が捨てられるため警告する。
    失敗して中断した瞬間にしか表示されないので、check で気付けないと事実上気付けない。"""
    md = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```

        ### RB-ONFAIL
        ```
        フェンス内なので捨てられる
        ```
    """)
    rc = cli.main(["check", str(md)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RB-ONFAIL の内容が空です" in out
    assert "警告 1 件" in out


def test_check_no_warning_for_unfenced_onfail(tmp_path, capsys):
    md = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```

        ### RB-ONFAIL
        担当へ連絡する。
    """)
    rc = cli.main(["check", str(md)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "内容が空です" not in out


def test_result_summary_names_failed_step(tmp_path, capsys):
    """案R1: 最終サマリーが「どのステップで落ちたか」を示し、未実行を明示する"""
    md = write_md(tmp_path, """\
        ## 成功する

        ### RB-CMD
        ```bash
        true
        ```

        ## 失敗する

        ### RB-CMD
        ```bash
        echo out; false
        ```

        ## 到達しない

        ### RB-CMD
        ```bash
        true
        ```
    """)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    out = capsys.readouterr().out
    assert rc == 1
    assert "ステップ 2「失敗する」で失敗" in out
    assert "未実行" in out       # 3番目は中断で到達しない
    assert "← 中断" in out


def test_criteria_breakdown_records_evidence(tmp_path):
    """案R6: 判定内訳に「実際の出力はどうだったか」が result.json / run.log に残る"""
    md = write_md(tmp_path, """\
        ## 失敗

        ### RB-CMD
        ```bash
        echo OK
        echo ERROR
        ```

        ### RB-EXPECTED
        ```
        rc == 0 and out("OK") and not out("ERROR")
        ```
    """)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    log_dir, result = read_result(tmp_path / "logs")
    evid = {b["expr"]: b["evidence"] for b in result["steps"][0]["criteria_breakdown"]}
    assert "実際 rc=0" in evid["rc == 0"]
    assert "初出 L2" in evid['not out("ERROR")']
    assert "→" in (log_dir / "run.log").read_text(encoding="utf-8")


def test_secret_masked_in_breakdown_evidence(tmp_path, capsys):
    """案R6: 内訳の「実際の出力」にはコマンド出力の本文が入るため、
    そこに現れたシークレット値もマスクされること"""
    md = write_md(tmp_path, """\
        ```runbook
        vars:
          API_TOKEN: s3cret-value-xyz
        secrets: [API_TOKEN]
        ```

        ## 出力にトークンが混ざる

        ### RB-CMD
        ```bash
        echo "token is {{API_TOKEN}}"
        ```

        ### RB-EXPECTED
        ```
        rc == 0 and out("token is") and out("ABSENT")
        ```
    """)
    rc = cli.main(["run", str(md), "--yes", "--operator", "山田",
                   "--log-dir", str(tmp_path / "logs")])
    assert rc == 1
    out = capsys.readouterr().out
    assert "s3cret-value-xyz" not in out
    log_dir, result = read_result(tmp_path / "logs")
    evid = {b["expr"]: b["evidence"] for b in result["steps"][0]["criteria_breakdown"]}
    # マッチした行が証跡に載るが、値はマスクされている
    assert "初出 L1" in evid['out("token is")']
    assert "*****" in evid['out("token is")']
    assert "s3cret-value-xyz" not in json.dumps(result, ensure_ascii=False)
    assert "s3cret-value-xyz" not in (log_dir / "run.log").read_text(encoding="utf-8")


def test_breakdown_arrows_aligned_with_fullwidth_chars(tmp_path, capsys):
    """案R6: 全角文字を含む条件式でも → の位置が揃う(len ではなく表示幅で計算)"""
    md = write_md(tmp_path, """\
        ## 失敗

        ### RB-CMD
        ```bash
        echo hello
        ```

        ### RB-EXPECTED
        ```
        rc == 0 and out("日本語パターン") and out("x")
        ```
    """)
    cli.main(["run", str(md), "--yes", "--operator", "山田",
              "--log-dir", str(tmp_path / "logs")])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "→" in ln and "[" in ln]
    assert len(lines) == 3
    columns = {cli.cell_len(ln.split("→")[0]) for ln in lines}
    assert len(columns) == 1, f"→ の位置が揃っていない: {columns}"


def test_sample_output_demo_runs_and_demonstrates_readability(tmp_path, capsys):
    """samples/output_demo.md が意図どおり途中で失敗し、可読性改善の表示を一通り出す。
    デモ手順書が改修で壊れていないことを固定する。"""
    rc = cli.main(["run", "samples/output_demo.md", "--yes", "--operator", "デモ",
                   "--log-dir", str(tmp_path / "logs")])
    out = capsys.readouterr().out
    assert rc == 1, "output_demo.md は意図的に失敗する手順書"
    assert "ステップ 5「意図的に失敗するステップ" in out  # 案R1: 失敗ステップ名
    # 案R1: リザルト一覧でステップ6・7が未実行。手順書の説明文にも「未実行」の語が
    # 出てくるため、一覧表の行(先頭が行番号)だけを数える
    summary = out.split("・ 実行結果:")[-1]
    assert len([ln for ln in summary.splitlines() if "未実行" in ln]) == 2
    assert "← 中断" in out
    assert "db01=O" in out                                 # 案R2: ホスト別結果の1行表示
    assert out.count("O=成功") == 2                        # 案R3: 凡例は初回 + 最終マトリックス
    assert "3行がマッチ" in out                            # 案R6: 判定内訳の実態
    assert "失敗時ガイダンス" in out                       # RB-ONFAIL
    assert "終了 " in out                                  # 案R4: 結果行に終了時刻


def test_sample_output_demo_check_warning_file_warns(tmp_path, capsys):
    """samples/output_demo_check_warning.md は案R9 の警告デモなので警告が出ること"""
    rc = cli.main(["check", "samples/output_demo_check_warning.md"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "RB-ONFAIL の内容が空です" in out
    assert "警告 1 件" in out


def test_list_table_has_no_truncated_command(tmp_path, capsys):
    """一覧表はコマンド列を持たない(60文字切り捨てによる情報の破棄をなくす)"""
    long_cmd = "echo " + "x" * 200
    md = write_md(tmp_path, f"""\
        ## 長いコマンドのステップ

        ### RB-CMD
        ```bash
        {long_cmd}
        ```
    """)
    assert cli.main(["list", str(md)]) == 0
    out = capsys.readouterr().out
    assert "..." not in out, "切り捨てが残っている"
    assert "種別" in out and "bash" in out
    assert "長いコマンドのステップ" in out


def test_list_detail_shows_full_command(tmp_path, capsys):
    """--detail は変数展開後のコマンドを全文表示する(list 単体で全文が読める)"""
    long_cmd = "echo " + "y" * 150
    md = write_md(tmp_path, f"""\
        ```runbook
        vars:
          HOST: web01
        ```

        ## ステップ

        ### RB-CMD
        ```bash
        {long_cmd} {{{{HOST}}}}
        ```
    """)
    assert cli.main(["list", "--detail", str(md)]) == 0
    out = capsys.readouterr().out
    assert "y" * 150 in out          # 全文が出る
    assert f"{'y' * 150} web01" in out  # 変数展開後


def test_list_without_detail_omits_command_body(tmp_path, capsys):
    md = write_md(tmp_path, """\
        ## ステップ

        ### RB-CMD
        ```bash
        echo UNIQUE_MARKER_ZZZ
        ```
    """)
    assert cli.main(["list", str(md)]) == 0
    assert "UNIQUE_MARKER_ZZZ" not in capsys.readouterr().out


def test_check_warns_unknown_common_config_key(tmp_path, capsys):
    """共通設定の未知キーは黙って無視されるため check で警告する"""
    md = write_md(tmp_path, """\
        ```runbook
        vars:
          A: b
        foo: 1
        ```

        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    assert cli.main(["check", str(md)]) == 0
    out = capsys.readouterr().out
    assert "「foo」は解釈されません" in out


def test_check_warns_timeout_in_common_config(tmp_path, capsys):
    """共通設定の timeout は効かず既定は無制限待ち。事故になるので具体的に案内する"""
    md = write_md(tmp_path, """\
        ```runbook
        timeout: 5
        ```

        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    assert cli.main(["check", str(md)]) == 0
    out = capsys.readouterr().out
    assert "「timeout」は解釈されません" in out
    assert "RB-LOCALDEF" in out
    assert "無制限" in out


def test_check_no_warning_for_known_common_config_keys(tmp_path, capsys):
    md = write_md(tmp_path, """\
        ```runbook
        title: タイトル
        vars:
          A: b
        secrets: [A]
        ansible:
          host_matrix: true
        ```

        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    assert cli.main(["check", str(md)]) == 0
    assert "解釈されません" not in capsys.readouterr().out
