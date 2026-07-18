import textwrap

import pytest

from runbook import parser

def write_md(tmp_path, text):
    p = tmp_path / "proc.md"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_parse_basic(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        title: テスト手順
        vars:
          HOST: web01
        ```

        # テスト手順

        ## ステップA

        ### RB-DESCRIPTION
        説明文です。

        ### RB-CMD
        ```bash
        echo {{HOST}}
        ```

        ### RB-EXPECTED
        ```
        rc == 0 and out("web01")
        ```

        ## ステップB

        ### RB-CMD
        ```bash
        true
        ```
    """)
    proc = parser.parse_file(p)
    assert proc.title == "テスト手順"
    assert len(proc.steps) == 2
    s1, s2 = proc.steps
    assert s1.title == "ステップA"
    assert s1.description == "説明文です。"
    assert s1.command == "echo web01"  # 変数置換済み
    assert 'out("web01")' in s1.criteria
    assert s2.criteria == parser.DEFAULT_CRITERIA  # 基準省略時は rc == 0


def test_runbook_fence_config(tmp_path):
    """前書きの ```runbook フェンスで frontmatter と同じ設定が書ける"""
    p = write_md(tmp_path, """\
        # 手順書タイトル

        前書きの説明文。

        ```runbook
        vars:
          HOST: web01
        share_env: true
        ansible:
          target: all
        ```

        ## S1

        ### RB-CMD
        ```bash
        echo {{HOST}}
        ```
    """)
    proc = parser.parse_file(p)
    assert proc.title == "手順書タイトル"  # タイトルは # 見出しから
    assert proc.vars == {"HOST": "web01"}
    assert proc.share_env is True
    assert proc.steps[0].command == "echo web01"


def test_frontmatter_config_keys_are_rejected(tmp_path):
    """frontmatter は一般メタデータとして無視されるが、runbook の設定キーが
    紛れている場合は「書いたのに効かない」事故防止のためエラーにする"""
    p = write_md(tmp_path, """\
        ---
        vars:
          A: "1"
        ---
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="frontmatter に runbook の設定キー"):
        parser.parse_file(p)


def test_frontmatter_generic_metadata_is_ignored(tmp_path):
    """設定キー以外の frontmatter(一般的な Markdown メタデータ)は無視して通る"""
    p = write_md(tmp_path, """\
        ---
        title: メタデータのタイトル
        author: practi
        tags: [ops, weekly]
        ---
        # 本文のタイトル

        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    proc = parser.parse_file(p)
    # frontmatter の title は解釈されず、本文の # 見出しが使われる
    assert proc.title == "本文のタイトル"
    assert proc.vars == {}


def test_runbook_fence_duplicated_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        share_env: true
        ```
        ```runbook
        share_env: false
        ```

        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="複数"):
        parser.parse_file(p)


def test_runbook_fence_inside_step_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```runbook
        vars:
          A: "1"
        ```
    """)
    with pytest.raises(parser.ParseError, match="前書き"):
        parser.parse_file(p)


def test_runbook_fence_inside_step_sections_is_error(tmp_path):
    """RB-CMD 以外の場所(RB-DESCRIPTION 内や ### より前)に置かれた
    ```runbook フェンスも黙って無視せずエラーにする"""
    p1 = tmp_path / "in_description.md"
    p1.write_text(textwrap.dedent("""\
        ## S1

        ### RB-DESCRIPTION
        説明文
        ```runbook
        vars:
          A: "1"
        ```

        ### RB-CMD
        ```bash
        true
        ```
    """), encoding="utf-8")
    with pytest.raises(parser.ParseError, match="前書き"):
        parser.parse_file(p1)

    p2 = tmp_path / "before_sections.md"
    p2.write_text(textwrap.dedent("""\
        ## S1
        ```runbook
        vars:
          A: "1"
        ```

        ### RB-CMD
        ```bash
        true
        ```
    """), encoding="utf-8")
    with pytest.raises(parser.ParseError, match="前書き"):
        parser.parse_file(p2)


def test_section_heading_inside_fence_not_section(tmp_path):
    """フェンス内の行頭 ### (bash コメント等)はセクション見出しとして扱わない"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        ### 装飾コメント ###
        cat <<'EOF'
        ### RB-EXPECTED
        EOF
        echo done
        ```
    """)
    proc = parser.parse_file(p)
    s = proc.steps[0]
    assert "### 装飾コメント ###" in s.command
    assert "### RB-EXPECTED" in s.command
    assert s.criteria == parser.DEFAULT_CRITERIA  # フェンス内の ### RB-EXPECTED は無効


def test_heading_number_stripped(tmp_path):
    """見出し先頭の連番はステップ名から除去され、heading_number に保持される"""
    p = write_md(tmp_path, """\
        ## 1. 事前確認

        ### RB-CMD
        ```bash
        true
        ```

        ## 3. 番号がズレた見出し

        ### RB-CMD
        ```bash
        true
        ```

        ## 100台対応(番号でない先頭数字は保持)

        ### RB-CMD
        ```bash
        true
        ```
    """)
    s1, s2, s3 = parser.parse_file(p).steps
    assert (s1.title, s1.heading_number) == ("事前確認", 1)
    assert (s2.title, s2.heading_number) == ("番号がズレた見出し", 3)  # 実際の順序は 2
    assert s2.number == 2
    assert (s3.title, s3.heading_number) == ("100台対応(番号でない先頭数字は保持)", None)


def test_share_env_flag(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        share_env: true
        ```
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    assert parser.parse_file(p).share_env is True


def test_share_env_default_false(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    assert parser.parse_file(p).share_env is False


def test_share_env_invalid_type(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        share_env: yes please
        ```
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="share_env"):
        parser.parse_file(p)


def test_ansible_step(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          GROUP: webservers
        ansible:
          target: "{{GROUP}}"
        ```
        ## サービス確認

        ### RB-CMD
        ```ansible
        systemctl status nginx
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.runner == "ansible"
    assert s.remote_command == "systemctl status nginx"
    assert s.command == ("ansible webservers -i hosts.ini "
                         "-e '{\"GROUP\": \"webservers\"}' "
                         "-m shell -a 'systemctl status nginx'")


def test_ansible_fence_is_not_text_substituted(tmp_path):
    """ansible フェンス内は jinja2 の世界: runbook のテキスト置換は行わず、
    変数は -e extra-vars として渡す。jinja2 記法もそのまま通る。"""
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          KEYWORD: hello
        ansible:
          target: all
        ```
        ## S1

        ### RB-CMD
        ```ansible
        echo "{{KEYWORD}} from {{ inventory_hostname }}"
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    # フェンス内容は無加工(未定義の inventory_hostname でもエラーにならない)
    assert s.remote_command == 'echo "{{KEYWORD}} from {{ inventory_hostname }}"'
    # 変数は -e で渡される
    assert "-e" in s.command and '"KEYWORD": "hello"' in s.command
    assert "{{ inventory_hostname }}" in s.command


def test_ansible_step_override_and_extra_args(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          target: all
        ```
        ## DBだけ確認

        ### RB-CMD
        ```ansible
        uptime
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
          target: db01
          extra_args: --become -f 5
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.command == "ansible db01 -i hosts.ini --become -f 5 -m shell -a uptime"


def test_common_config_inventory_is_error(tmp_path):
    """インベントリの共通デフォルトは事故防止のため禁止(毎回個別指定を強制)"""
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          inventory: hosts.ini
          target: all
        ```
        ## S1

        ### RB-CMD
        ```ansible
        uptime
        ```
    """)
    with pytest.raises(parser.ParseError, match="inventory は指定できません"):
        parser.parse_file(p)


def test_ansible_host_matrix_flag(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          target: all
          host_matrix: true
        ```
        ## S1

        ### RB-CMD
        ```ansible
        uptime
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```

        ## S2

        ### RB-CMD
        ```ansible
        uptime
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
          host_matrix: false
        ```
    """)
    s1, s2 = parser.parse_file(p).steps
    assert s1.host_matrix is True   # frontmatter の既定値
    assert s2.host_matrix is False  # ステップで無効化
    # host_matrix は ansible コマンドラインには乗らない
    assert "host_matrix" not in s1.command


def test_ansible_inline_invocation(tmp_path):
    """フェンス1行目の `ansible ...` を起動指定として使う(設定側 target/inventory 不要)"""
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          ENV: prod
        ```
        ## S1

        ### RB-CMD
        ```ansible
        ansible dbservers -i inventories/{{ENV}}/db.ini -f 3
        df -h /
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.remote_command == "df -h /"
    # 起動指定行は {{VAR}} 置換され、-e JSON は起動指定より前(行内 -e が優先になる並び)
    assert s.command == ("ansible -e '{\"ENV\": \"prod\"}' "
                         "dbservers -i inventories/prod/db.ini -f 3 "
                         "-m shell -a 'df -h /'")


def test_ansible_inline_invocation_overrides_config(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          target: all
        ```
        ## S1

        ### RB-CMD
        ```ansible
        ansible web01 -i web.ini
        uptime
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: default.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    # 設定側の default.ini / all は使われない
    assert "default.ini" not in s.command
    assert s.command == "ansible web01 -i web.ini -m shell -a uptime"


def test_ansible_inline_invocation_without_remote_command_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```ansible
        ansible web01 -i web.ini
        ```
    """)
    with pytest.raises(parser.ParseError, match="リモートコマンドがありません"):
        parser.parse_file(p)


def test_playbook_step(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          ENV: prod
        ansible:
          target: webservers
        ```
        ## デプロイ

        ### RB-CMD
        ```playbook
        playbooks/{{ENV}}/deploy.yml
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.runner == "playbook"
    assert s.remote_command == "playbooks/prod/deploy.yml"  # パスは {{VAR}} 置換される
    assert s.command == ("ansible-playbook -i hosts.ini -l webservers "
                         "-e '{\"ENV\": \"prod\"}' playbooks/prod/deploy.yml")


def test_playbook_target_optional_multiple_paths(tmp_path):
    p = write_md(tmp_path, """\
        ## 一括適用

        ### RB-CMD
        ```ansible-playbook
        site.yml
        extra.yml
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.runner == "playbook"
    # target 未指定なら -l は付かず、複数行は && で連結され1行ずつ実行される
    assert s.command == ("ansible-playbook -i hosts.ini site.yml"
                         " && ansible-playbook -i hosts.ini extra.yml")


def test_playbook_inline_options(tmp_path):
    """プレイブックパスの後ろに -e などのオプションをそのまま書ける"""
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          HOGE: FUGA
        ```
        ## S1

        ### RB-CMD
        ```playbook
        deploy.yml -e HOGE=PIYO --check
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    # 行のオプションは自動付与の -e JSON より後ろ → 同名変数は行の値が優先
    assert s.command == ("ansible-playbook -i hosts.ini "
                         "-e '{\"HOGE\": \"FUGA\"}' deploy.yml -e HOGE=PIYO --check")


def test_playbook_inline_inventory(tmp_path):
    """行内の -i が優先され、設定側インベントリは自動付与されない"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```playbook
        -i inventories/web.ini deploy_web.yml
        db_backup.yml -i inventories/db.ini
        site.yml
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: default_hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    cmds = s.command.split(" && ")
    # 1行目・2行目: 行内 -i を使用(位置は前でも後ろでもよい)、自動付与なし
    assert cmds[0] == "ansible-playbook -i inventories/web.ini deploy_web.yml"
    assert cmds[1] == "ansible-playbook db_backup.yml -i inventories/db.ini"
    # 3行目: 行内 -i がないので設定側インベントリを自動付与
    assert cmds[2] == "ansible-playbook -i default_hosts.ini site.yml"


def test_playbook_inline_inventory_without_config(tmp_path):
    """全行が行内 -i を持てば frontmatter の inventory は不要"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```playbook
        --inventory inventories/web.ini deploy.yml
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.command == "ansible-playbook --inventory inventories/web.ini deploy.yml"


def test_playbook_line_without_any_inventory_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```playbook
        -i inventories/web.ini deploy.yml
        site.yml
        ```
    """)
    with pytest.raises(parser.ParseError, match="インベントリが未指定"):
        parser.parse_file(p)


def test_playbook_missing_inventory_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```playbook
        site.yml
        ```
    """)
    with pytest.raises(parser.ParseError, match="inventory"):
        parser.parse_file(p)


def test_playbook_and_ansible_fence_mix_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          target: all
        ```
        ## S1

        ### RB-CMD
        ```ansible
        uptime
        ```
        ```playbook
        site.yml
        ```
    """)
    with pytest.raises(parser.ParseError, match="混在"):
        parser.parse_file(p)


def test_ansible_missing_inventory_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```ansible
        uptime
        ```
    """)
    with pytest.raises(parser.ParseError, match="inventory"):
        parser.parse_file(p)


def test_ansible_mixed_fence_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          target: all
        ```
        ## S1

        ### RB-CMD
        ```ansible
        uptime
        ```
        ```bash
        echo local
        ```
    """)
    with pytest.raises(parser.ParseError, match="混在"):
        parser.parse_file(p)


def test_ansible_remote_command_quoting(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        ansible:
          target: web
        ```
        ## S1

        ### RB-CMD
        ```ansible
        grep -c "error" /var/log/app.log && echo 'done'
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts.ini
        ```
    """)
    s = parser.parse_file(p).steps[0]
    # リモートコマンド全体が 1 引数として安全にクォートされている
    import shlex
    argv = shlex.split(s.command)
    assert argv[:3] == ["ansible", "web", "-i"]
    assert argv[-1] == 'grep -c "error" /var/log/app.log && echo \'done\''


def test_undefined_var_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        echo {{NOT_DEFINED}}
        ```
    """)
    with pytest.raises(parser.ParseError, match="NOT_DEFINED"):
        parser.parse_file(p)


def test_extra_vars_override(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          HOST: default
        ```
        ## S1

        ### RB-CMD
        ```bash
        echo {{HOST}}
        ```
    """)
    proc = parser.parse_file(p, {"HOST": "override"})
    assert proc.steps[0].command == "echo override"


def test_manual_step(tmp_path):
    """RB-CMD のないステップは手動ステップ(runner=manual)として許容される"""
    p = write_md(tmp_path, """\
        ## VPN に接続する

        ### RB-DESCRIPTION
        社内 VPN に接続し、接続済みアイコンを目視確認する。

        ## コマンドステップ

        ### RB-CMD
        ```bash
        true
        ```
    """)
    s1, s2 = parser.parse_file(p).steps
    assert s1.runner == "manual"
    assert s1.command == ""
    assert s1.criteria == ""
    assert "目視確認" in s1.description
    assert s2.runner == "shell"


def test_manual_step_requires_description(tmp_path):
    """RB-CMD も RB-DESCRIPTION もないステップは書き忘れとしてエラー"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-ONFAIL
        説明なし
    """)
    with pytest.raises(parser.ParseError, match="RB-DESCRIPTION"):
        parser.parse_file(p)


def test_manual_step_with_expected_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-DESCRIPTION
        手動作業

        ### RB-EXPECTED
        ```
        rc == 0
        ```
    """)
    with pytest.raises(parser.ParseError, match="RB-EXPECTED は書けません"):
        parser.parse_file(p)


def test_manual_step_with_localdef_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-DESCRIPTION
        手動作業

        ### RB-LOCALDEF
        ```yaml
        timeout: 10
        ```
    """)
    with pytest.raises(parser.ParseError, match="RB-LOCALDEF は書けません"):
        parser.parse_file(p)


def test_empty_command_section_is_error(tmp_path):
    """RB-CMD セクションはあるが中身が空の場合は従来どおりエラー(手動ステップにならない)"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-DESCRIPTION
        説明

        ### RB-CMD
        ```bash
        ```
    """)
    with pytest.raises(parser.ParseError, match="コマンドがありません"):
        parser.parse_file(p)


def test_onfail_section(tmp_path):
    """RB-ONFAIL は失敗時ガイダンスとして保持される(変数置換はされない自由記述)"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```

        ### RB-ONFAIL
        DB の接続数を確認し、復旧しない場合は佐藤さんへエスカレーション。
    """)
    s = parser.parse_file(p).steps[0]
    assert "エスカレーション" in s.onfail


def test_rollback_section(tmp_path):
    """# RB-ROLLBACK 以降のステップは rollback_steps に分離され、番号も独立"""
    p = write_md(tmp_path, """\
        # 手順書

        ## 通常1

        ### RB-CMD
        ```bash
        true
        ```

        ## 通常2

        ### RB-CMD
        ```bash
        true
        ```

        # RB-ROLLBACK

        ## 戻し1

        ### RB-DESCRIPTION
        手動で切り戻す

        ## 戻し2

        ### RB-CMD
        ```bash
        echo rollback
        ```
    """)
    proc = parser.parse_file(p)
    assert proc.title == "手順書"
    assert [s.title for s in proc.steps] == ["通常1", "通常2"]
    assert [s.title for s in proc.rollback_steps] == ["戻し1", "戻し2"]
    assert [s.number for s in proc.rollback_steps] == [1, 2]  # 独立採番
    assert proc.rollback_steps[0].runner == "manual"


def test_rollback_duplicated_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```

        # RB-ROLLBACK

        ## 戻し

        ### RB-CMD
        ```bash
        true
        ```

        # RB-ROLLBACK

        ## 戻し2

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="RB-ROLLBACK.*複数"):
        parser.parse_file(p)


def test_rollback_without_steps_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        true
        ```

        # RB-ROLLBACK
    """)
    with pytest.raises(parser.ParseError, match="RB-ROLLBACK の後にステップ"):
        parser.parse_file(p)


def test_rollback_heading_inside_fence_ignored(tmp_path):
    """フェンス内の # RB-ROLLBACK 行は区切りとして扱わない"""
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        cat <<'EOF'
        # RB-ROLLBACK
        EOF
        ```
    """)
    proc = parser.parse_file(p)
    assert len(proc.steps) == 1
    assert proc.rollback_steps == []


def test_ansible_inventories_collected(tmp_path):
    """実行前サマリー用に、各ステップの使用インベントリが収集される"""
    p = write_md(tmp_path, """\
        ## ad-hoc 設定指定

        ### RB-CMD
        ```ansible
        uptime
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts_a.ini
          target: web
        ```

        ## ad-hoc 行内指定

        ### RB-CMD
        ```ansible
        ansible db -i hosts_b.ini
        uptime
        ```

        ## playbook 行内と設定の混在

        ### RB-CMD
        ```playbook
        -i hosts_c.ini deploy.yml
        site.yml
        ```

        ### RB-LOCALDEF
        ```yaml
        ansible:
          inventory: hosts_d.ini
        ```
    """)
    s1, s2, s3 = parser.parse_file(p).steps
    assert s1.inventories == ["hosts_a.ini"]
    assert s2.inventories == ["hosts_b.ini"]
    assert s3.inventories == ["hosts_c.ini", "hosts_d.ini"]


def test_options_timeout(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        sleep 1
        ```

        ### RB-LOCALDEF
        ```yaml
        timeout: 5
        cwd: /tmp
        ```
    """)
    s = parser.parse_file(p).steps[0]
    assert s.timeout == 5.0
    assert s.cwd == "/tmp"


def test_heading_inside_fence_not_step(tmp_path):
    p = write_md(tmp_path, """\
        ## S1

        ### RB-CMD
        ```bash
        cat <<'EOF'
        ## これはステップ見出しではない
        EOF
        ```
    """)
    proc = parser.parse_file(p)
    assert len(proc.steps) == 1
    assert "## これは" in proc.steps[0].command


def test_secrets_declared(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          DB_PASS: s3cret
          HOST: web01
        secrets: [DB_PASS]
        ```
        ## S1

        ### RB-CMD
        ```bash
        echo {{DB_PASS}}
        ```
    """)
    proc = parser.parse_file(p)
    assert proc.secrets == ["DB_PASS"]


def test_secrets_undefined_var_is_error(tmp_path):
    """宣言した変数が未定義なら fail-loud でエラー(書いたのに効かない事故防止)"""
    p = write_md(tmp_path, """\
        ```runbook
        secrets: [NO_SUCH_VAR]
        ```
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="NO_SUCH_VAR"):
        parser.parse_file(p)


def test_secrets_defined_by_cli_var_is_ok(tmp_path):
    """secrets の変数は --var(extra_vars)での定義でもよい"""
    p = write_md(tmp_path, """\
        ```runbook
        secrets: [API_TOKEN]
        ```
        ## S1

        ### RB-CMD
        ```bash
        echo {{API_TOKEN}}
        ```
    """)
    proc = parser.parse_file(p, {"API_TOKEN": "tok"})
    assert proc.secrets == ["API_TOKEN"]


def test_secrets_not_a_list_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ```runbook
        vars:
          DB_PASS: x
        secrets: DB_PASS
        ```
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="secrets は変数名のリスト"):
        parser.parse_file(p)


def test_secrets_in_frontmatter_is_error(tmp_path):
    p = write_md(tmp_path, """\
        ---
        secrets: [DB_PASS]
        ---
        ## S1

        ### RB-CMD
        ```bash
        true
        ```
    """)
    with pytest.raises(parser.ParseError, match="frontmatter に runbook の設定キー"):
        parser.parse_file(p)
