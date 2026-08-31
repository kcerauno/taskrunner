# 06. 実行例集

本書は runbook **v0.5.0** の実際の実行出力を採取したもの(採取日 2026-08-31)。

採取環境:

- 作業ディレクトリ: `/home/practi/wk_tool`
- runbook バイナリ: `.venv/bin/runbook`(バージョン 0.5.0)
- OS: Linux practicus 6.8.0-138-generic
- 端末幅: `COLUMNS=100`(表の折り返し位置は端末幅に依存する)

以降のコマンド例で `<LOGDIR>` はログ出力先の一時ディレクトリ、
`<DEMO_DIR>` は 5〜6 節のデモ手順書(`fail_demo.md` / `secrets_demo.md`)を
配置した一時ディレクトリを指す(実運用では既定の `./logs` などを使う)。
出力中のこの2つのパスのみを可読性のため置換しており、それ以外は実際の出力をそのまま掲載している。

---

## 1. バージョン・ヘルプ表示

### 1.1 `--version`

```
$ .venv/bin/runbook --version
```

```
runbook 0.5.0
exit=0
```

### 1.2 `--help`(メインコマンド)

```
$ .venv/bin/runbook --help
```

```
usage: runbook [-h] [--version] {run,list,check,renumber} ...

Markdown手順書 自動実行フレームワーク

positional arguments:
  {run,list,check,renumber}
    run                 手順書を実行する
    list                ステップ一覧を表示する
    check               手順書の書式・基準式・参照パス(インベントリ/playbook/cwd)を検証する(実行しない)
    renumber            ## 見出しに実行順の連番(1. 2. ...)を付与/振り直す

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
exit=0
```

### 1.3 `run --help`

```
$ .venv/bin/runbook run --help
```

```
usage: runbook run [-h] [--var KEY=VALUE] [-i] [--only SPEC] [--from N] [--to N] [--start-from N]
                   [-y] [--operator NAME] [--checker NAME] [--log-dir LOG_DIR]
                   file

positional arguments:
  file               手順書 Markdown ファイル

options:
  -h, --help         show this help message and exit
  --var KEY=VALUE    変数の指定/上書き(複数可)
  -i, --interactive  各ステップ実行前に確認する(逐次インタラクティブ実行)
  --only SPEC        実行するステップ番号(例: 1,3-5)
  --from N           開始ステップ番号
  --to N             終了ステップ番号
  --start-from N     ステップ N から最後まで再開実行する。直近実行の環境変数(env_overlay.sh)を復元する(見つからなければエラー)
  -y, --yes          実行前サマリーの確認をスキップする(非対話実行用)
  --operator NAME    作業者名(省略時は実行開始時に入力を求める)
  --checker NAME     確認者名(任意。--operator 指定時は省略可)
  --log-dir LOG_DIR  ログ保存先ディレクトリ(既定: ./logs)
exit=0
```

### 1.4 `check --help`

```
$ .venv/bin/runbook check --help
```

```
usage: runbook check [-h] [--var KEY=VALUE] [--json] [--preview] file

positional arguments:
  file             手順書 Markdown ファイル

options:
  -h, --help       show this help message and exit
  --var KEY=VALUE  変数の指定/上書き(複数可)
  --json           検証結果を行番号付きの JSON で出力する(エディタ統合用)
  --preview        変数展開・ansibleコマンド組み立て後の実行コマンドを全文表示する
exit=0
```

### 1.5 `list --help`

```
$ .venv/bin/runbook list --help
```

```
usage: runbook list [-h] [--var KEY=VALUE] [--detail] file

positional arguments:
  file             手順書 Markdown ファイル

options:
  -h, --help       show this help message and exit
  --var KEY=VALUE  変数の指定/上書き(複数可)
  --detail         一覧に加えて、変数展開後の実行コマンドを全文表示する
exit=0
```

### 1.6 `renumber --help`

```
$ .venv/bin/runbook renumber --help
```

```
usage: runbook renumber [-h] [--var KEY=VALUE] file

positional arguments:
  file             手順書 Markdown ファイル

options:
  -h, --help       show this help message and exit
  --var KEY=VALUE  変数の指定/上書き(複数可)
exit=0
```

---

## 2. テストスイート実行結果

実行場所: `/home/practi/wk_tool`

```
$ .venv/bin/python -m pytest tests/ -q
```

終了コード: 0

```
............................................................................................ [ 47%]
............................................................................................ [ 95%]
........                                                                                     [100%]
192 passed in 6.95s
```

192 件全てパス、失敗・エラーなし。

---

## 3. 事前検証と一覧表示

対象手順書: `samples/local_test/feature_test.md`(ad-hoc / playbook / bash が混在する機能テスト手順、ansible 疑似6ホスト構成を利用)

### 3.1 `check`(書式・基準式・参照パスの検証)

```
$ .venv/bin/runbook check samples/local_test/feature_test.md
```

終了コード: 0

```
OK samples/local_test/feature_test.md: 6 ステップ、書式・基準式に問題ありません
exit=0
```

### 3.2 `list`(ステップ一覧)

```
$ .venv/bin/runbook list samples/local_test/feature_test.md
```

終了コード: 0

```
機能テスト手順(共通設定なし・全ステップ個別定義スタイル) (samples/local_test/feature_test.md)
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ No. ┃ ステップ                               ┃ 種別     ┃ 正常性基準                             ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│   1 │ ad-hoc: 行内指定で全6ホストの疎通確認  │ ansible  │ rc == 0 and                            │
│     │                                        │          │ out("機能テスト: host=web01") and      │
│     │                                        │          │ out("機能テスト: host=web02") and      │
│     │                                        │          │ out("機能テスト: host=web03") and      │
│     │                                        │          │ out("機能テスト: host=db01") and       │
│     │                                        │          │ out("機能テスト: host=db02") and       │
│     │                                        │          │ out("機能テスト: host=mon01") and      │
│     │                                        │          │ not out("UNREACHABLE|FAILED")          │
│   2 │ ad-hoc: RB-LOCALDEF で定義するスタイル │ ansible  │ rc == 0 and out("web01") and           │
│     │                                        │          │ out("web02") and out("web03") and      │
│     │                                        │          │ not out("db01|db02|mon01") and not     │
│     │                                        │          │ out("UNREACHABLE|FAILED")              │
│   3 │ playbook: 行内 -i と -e(実行時上書き)  │ playbook │ rc == 0 and out("HOGE=PIYO") and not   │
│     │                                        │          │ out("HOGE=FUGA") and                   │
│     │                                        │          │ not                                    │
│     │                                        │          │ out("failed=[1-9]|unreachable=[1-9]")  │
│   4 │ playbook: 行ごとのインベントリ切替     │ playbook │ rc == 0 and                            │
│     │                                        │          │ out("HOGE=FUGA \(host=web01\)") and    │
│     │                                        │          │ out("HOGE=FUGA \(host=web03\)") and    │
│     │                                        │          │ out("HOGE=DB_RUN \(host=db01\)") and   │
│     │                                        │          │ out("HOGE=DB_RUN \(host=db02\)") and   │
│     │                                        │          │ not                                    │
│     │                                        │          │ out("failed=[1-9]|unreachable=[1-9]")  │
│   5 │ ad-hoc: 行内指定 + 行内 -e の優先確認  │ ansible  │ rc == 0 and                            │
│     │                                        │          │ out("HOGE=ADHOC on db01") and          │
│     │                                        │          │ out("HOGE=ADHOC on db02") and          │
│     │                                        │          │ not out("HOGE=FUGA") and not           │
│     │                                        │          │ out("web01|web02|web03|mon01") and     │
│     │                                        │          │ not out("UNREACHABLE|FAILED")          │
│   6 │ bash: ローカルステップとの混在確認     │ bash     │ rc == 0 and "local step on" in stdout  │
│     │                                        │          │ and out("Linux")                       │
└─────┴────────────────────────────────────────┴──────────┴────────────────────────────────────────┘
exit=0
```

一覧表はコマンドを列に持たない(どの列も切り詰めないため)。
種別欄でランナー(`bash` / `ansible` / `playbook` / `手動`)が判別できる。

### 3.3 `list --detail`(実行コマンドを全文表示)

一覧表に続けて、変数展開後の実行コマンドを省略なしで表示する。
以下はステップ1・2の抜粋(表部分は 3.2 と同一のため省略)。

```
$ .venv/bin/runbook list --detail samples/local_test/feature_test.md
```

```
・ ステップ 1/6: ad-hoc: 行内指定で全6ホストの疎通確認
  ├ 説明: フェンス1行目の「ansible ターゲット -i インベントリ」が起動指定として使われる。
  │   期待結果: 6ホスト全てが CHANGED、ホスト別結果マトリックスに O が6つ並ぶ。
  ├ 対象: all @ samples/local_test/inventory.ini (最初の実行対象)
  ├ コマンド (ansible ad-hoc / shellモジュール)
  │   $ echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"
  ├ 実行コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' all -i samples/local_test/inventory.ini -m shell -a 'echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"'
  ├ 正常性基準: rc == 0 and
  │   out("機能テスト: host=web01") and out("機能テスト: host=web02") and
  │   out("機能テスト: host=web03") and out("機能テスト: host=db01") and
  │   out("機能テスト: host=db02") and out("機能テスト: host=mon01") and
  │   not out("UNREACHABLE|FAILED")

・ ステップ 2/6: ad-hoc: RB-LOCALDEF で定義するスタイル
  ├ 説明: 行内指定の代わりに、ステップの RB-LOCALDEF で inventory / target を定義する書き方。
  │   期待結果: web系3ホストのみで実行される。
  ├ 対象: web @ samples/local_test/inventory_web.ini ⇄ 前ステップから変更
  ├ コマンド (ansible ad-hoc / shellモジュール)
  │   $ uptime
  ├ 実行コマンド: ansible web -i samples/local_test/inventory_web.ini -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -m shell -a uptime
  ├ 正常性基準: rc == 0 and out("web01") and out("web02") and out("web03") and
  │   not out("db01|db02|mon01") and not out("UNREACHABLE|FAILED")
```

### 3.4 `check --preview`(検証 + 実行コマンド全文)

`check` の検証結果に続けて、3.3 と同じ詳細表示を行う。
以下は末尾(ステップ5・6)の抜粋。

```
$ .venv/bin/runbook check --preview samples/local_test/feature_test.md
```

```
・ ステップ 5/6: ad-hoc: 行内指定 + 行内 -e の優先確認
  ├ 説明: 起動指定行に -e HOGE=ADHOC を書くと、自動付与の手順書変数(HOGE=FUGA)より優先される。
  │   2行目以降のリモートコマンドでは jinja2({{ HOGE }} や {{ inventory_hostname }})が使える。
  │   期待結果: db系2ホストのみで実行され、出力が HOGE=ADHOC になる。
  ├ 対象: db @ samples/local_test/inventory_db.ini ⇄ 前ステップから変更
  ├ コマンド (ansible ad-hoc / shellモジュール)
  │   $ echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"
  ├ 実行コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"'
  ├ 正常性基準: rc == 0 and
  │   out("HOGE=ADHOC on db01") and out("HOGE=ADHOC on db02") and
  │   not out("HOGE=FUGA") and not out("web01|web02|web03|mon01") and
  │   not out("UNREACHABLE|FAILED")

・ ステップ 6/6: bash: ローカルステップとの混在確認
  ├ 説明: 同じ手順書内に bash ステップも混在できることの確認。ansible の設定は一切不要。
  │   期待結果: OK。このステップは ansible ではないためホスト別結果は表示されない。
  ├ コマンド (bash)
  │   $ echo "local step on $(hostname)"
  │   $ uname -a
  ├ 正常性基準: rc == 0 and "local step on" in stdout and out("Linux")
exit=0
```

---

## 4. 成功実行の例

対象: `samples/local_test/feature_test.md`(全6ステップ)

```
$ .venv/bin/runbook run samples/local_test/feature_test.md --yes --operator 仕様採取 --checker 確認者 --log-dir <LOGDIR>
```

終了コード: 0

出力全文:

```
・ 実行前確認
  ├ 手順書: 機能テスト手順(共通設定なし・全ステップ個別定義スタイル) (samples/local_test/feature_test.md)
  ├ モード: 一括
  ├ 実行対象: 6/6 ステップ
  │   1. ad-hoc: 行内指定で全6ホストの疎通確認
  │   2. ad-hoc: RB-LOCALDEF で定義するスタイル
  │   3. playbook: 行内 -i と -e(実行時上書き)
  │   4. playbook: 行ごとのインベントリ切替
  │   5. ad-hoc: 行内指定 + 行内 -e の優先確認
  │   6. bash: ローカルステップとの混在確認
  ├ 変数:
  │   CHECK_LABEL = 機能テスト
  │   HOGE = FUGA
  └ 使用インベントリ:
      samples/local_test/inventory.ini
      samples/local_test/inventory_db.ini
      samples/local_test/inventory_web.ini

・ 実行開始: 機能テスト手順(共通設定なし・全ステップ個別定義スタイル)
  ├ 作業者: 仕様採取 / 確認者: 確認者
  └ ログ保存先: <LOGDIR>/feature_test_20260831_170702

・ ステップ 1/6: ad-hoc: 行内指定で全6ホストの疎通確認
  ├ 説明: フェンス1行目の「ansible ターゲット -i インベントリ」が起動指定として使われる。
  │   期待結果: 6ホスト全てが CHANGED、ホスト別結果マトリックスに O が6つ並ぶ。
  ├ 対象: all @ samples/local_test/inventory.ini (最初の実行対象)
  ├ コマンド (ansible ad-hoc / shellモジュール)
  │   $ echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"
  ├ 実行コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' all -i samples/local_test/inventory.ini -m shell -a 'echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"'
  ├ 正常性基準: rc == 0 and
  │   out("機能テスト: host=web01") and out("機能テスト: host=web02") and
  │   out("機能テスト: host=web03") and out("機能テスト: host=db01") and
  │   out("機能テスト: host=db02") and out("機能テスト: host=mon01") and
  │   not out("UNREACHABLE|FAILED")
  ├ 開始: 2026-08-31 17:07:02
  │   web02 | CHANGED | rc=0 >>
  │   機能テスト: host=web02
  │   web03 | CHANGED | rc=0 >>
  │   機能テスト: host=web03
  │   db01 | CHANGED | rc=0 >>
  │   機能テスト: host=db01
  │   web01 | CHANGED | rc=0 >>
  │   機能テスト: host=web01
  │   db02 | CHANGED | rc=0 >>
  │   機能テスト: host=db02
  │   mon01 | CHANGED | rc=0 >>
  │   機能テスト: host=mon01
  ├ ホスト別結果: db01=O db02=O mon01=O web01=O web02=O web03=O
  │   O=成功  X=失敗  !=到達不能  -=対象外
  └ 結果: ✓ Completed (rc=0, 1.071s, 終了 17:07:03)

・ ステップ 2/6: ad-hoc: RB-LOCALDEF で定義するスタイル
  ├ 説明: 行内指定の代わりに、ステップの RB-LOCALDEF で inventory / target を定義する書き方。
  │   期待結果: web系3ホストのみで実行される。
  ├ 対象: web @ samples/local_test/inventory_web.ini ⇄ 前ステップから変更
  ├ コマンド (ansible ad-hoc / shellモジュール)
  │   $ uptime
  ├ 実行コマンド: ansible web -i samples/local_test/inventory_web.ini -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -m shell -a uptime
  ├ 正常性基準: rc == 0 and out("web01") and out("web02") and out("web03") and
  │   not out("db01|db02|mon01") and not out("UNREACHABLE|FAILED")
  ├ 開始: 2026-08-31 17:07:03
  │   web03 | CHANGED | rc=0 >>
  │    17:07:04 up 56 min,  1 user,  load average: 1.22, 1.09, 1.00
  │   web01 | CHANGED | rc=0 >>
  │    17:07:04 up 56 min,  1 user,  load average: 1.22, 1.09, 1.00
  │   web02 | CHANGED | rc=0 >>
  │    17:07:04 up 56 min,  1 user,  load average: 1.22, 1.09, 1.00
  ├ ホスト別結果: web01=O web02=O web03=O
  └ 結果: ✓ Completed (rc=0, 0.824s, 終了 17:07:04)

・ ステップ 3/6: playbook: 行内 -i と -e(実行時上書き)
  ├ 説明: プレイブック行に -i(インベントリ)と -e(実行時に変えたい値)を直接書く。
  │   手順書変数 HOGE=FUGA は自動の -e JSON で渡るが、行内の -e HOGE=PIYO が優先される。
  │   期待結果: web系3ホストで実行され、出力が HOGE=PIYO になる(FUGA ではない)。
  ├ 対象: (プレイブックの hosts:) @ samples/local_test/inventory_web.ini ⇄ 前ステップから変更
  ├ プレイブック (ansible-playbook)
  │   -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
  ├ 実行コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
  ├ 正常性基準: rc == 0 and out("HOGE=PIYO") and not out("HOGE=FUGA") and
  │   not out("failed=[1-9]|unreachable=[1-9]")
  ├ 開始: 2026-08-31 17:07:04
  │   
  │   PLAY [変数表示プレイ] **********************************************************
  │   
  │   TASK [HOGE の値を表示] *********************************************************
  │   ok: [web01] => {
  │       "msg": "HOGE=PIYO (host=web01)"
  │   }
  │   ok: [web02] => {
  │       "msg": "HOGE=PIYO (host=web02)"
  │   }
  │   ok: [web03] => {
  │       "msg": "HOGE=PIYO (host=web03)"
  │   }
  │   
  │   PLAY RECAP *********************************************************************
  │   web01                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   web02                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   web03                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   
  ├ ホスト別結果: web01=O web02=O web03=O
  └ 結果: ✓ Completed (rc=0, 0.54s, 終了 17:07:05)

・ ステップ 4/6: playbook: 行ごとのインベントリ切替
  ├ 説明: 処理系統ごとにインベントリを分ける運用の確認。行ごとに -i を書き分ける。
  │   2行は && 連結で順に実行され、1行目が失敗したら2行目は実行されない。
  │   期待結果: 1行目は web系3ホスト(HOGE=FUGA)、2行目は db系2ホスト(HOGE=DB_RUN)で実行され、
  │   マトリックスには両系統のホストがマージされて表示される。
  ├ 対象: (プレイブックの hosts:) @ samples/local_test/inventory_web.ini, samples/local_test/inventory_db.ini ⇄ 前ステップから変更
  ├ プレイブック (ansible-playbook)
  │   -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml
  │   -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
  ├ 実行コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml && ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
  ├ 正常性基準: rc == 0 and
  │   out("HOGE=FUGA \(host=web01\)") and out("HOGE=FUGA \(host=web03\)") and
  │   out("HOGE=DB_RUN \(host=db01\)") and out("HOGE=DB_RUN \(host=db02\)") and
  │   not out("failed=[1-9]|unreachable=[1-9]")
  ├ 開始: 2026-08-31 17:07:05
  │   
  │   PLAY [変数表示プレイ] **********************************************************
  │   
  │   TASK [HOGE の値を表示] *********************************************************
  │   ok: [web01] => {
  │       "msg": "HOGE=FUGA (host=web01)"
  │   }
  │   ok: [web02] => {
  │       "msg": "HOGE=FUGA (host=web02)"
  │   }
  │   ok: [web03] => {
  │       "msg": "HOGE=FUGA (host=web03)"
  │   }
  │   
  │   PLAY RECAP *********************************************************************
  │   web01                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   web02                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   web03                      : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   
  │   
  │   PLAY [変数表示プレイ] **********************************************************
  │   
  │   TASK [HOGE の値を表示] *********************************************************
  │   ok: [db01] => {
  │       "msg": "HOGE=DB_RUN (host=db01)"
  │   }
  │   ok: [db02] => {
  │       "msg": "HOGE=DB_RUN (host=db02)"
  │   }
  │   
  │   PLAY RECAP *********************************************************************
  │   db01                       : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   db02                       : ok=1    changed=0    unreachable=0    failed=0    skipped=0    rescued=0    ignored=0   
  │   
  ├ ホスト別結果: db01=O db02=O web01=O web02=O web03=O
  └ 結果: ✓ Completed (rc=0, 1.072s, 終了 17:07:06)

・ ステップ 5/6: ad-hoc: 行内指定 + 行内 -e の優先確認
  ├ 説明: 起動指定行に -e HOGE=ADHOC を書くと、自動付与の手順書変数(HOGE=FUGA)より優先される。
  │   2行目以降のリモートコマンドでは jinja2({{ HOGE }} や {{ inventory_hostname }})が使える。
  │   期待結果: db系2ホストのみで実行され、出力が HOGE=ADHOC になる。
  ├ 対象: db @ samples/local_test/inventory_db.ini ⇄ 前ステップから変更
  ├ コマンド (ansible ad-hoc / shellモジュール)
  │   $ echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"
  ├ 実行コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"'
  ├ 正常性基準: rc == 0 and
  │   out("HOGE=ADHOC on db01") and out("HOGE=ADHOC on db02") and
  │   not out("HOGE=FUGA") and not out("web01|web02|web03|mon01") and
  │   not out("UNREACHABLE|FAILED")
  ├ 開始: 2026-08-31 17:07:06
  │   db01 | CHANGED | rc=0 >>
  │   HOGE=ADHOC on db01
  │   db02 | CHANGED | rc=0 >>
  │   HOGE=ADHOC on db02
  ├ ホスト別結果: db01=O db02=O
  └ 結果: ✓ Completed (rc=0, 0.837s, 終了 17:07:06)

・ ステップ 6/6: bash: ローカルステップとの混在確認
  ├ 説明: 同じ手順書内に bash ステップも混在できることの確認。ansible の設定は一切不要。
  │   期待結果: OK。このステップは ansible ではないためホスト別結果は表示されない。
  ├ コマンド (bash)
  │   $ echo "local step on $(hostname)"
  │   $ uname -a
  ├ 正常性基準: rc == 0 and "local step on" in stdout and out("Linux")
  ├ 開始: 2026-08-31 17:07:06
  │   local step on practicus
  │   Linux practicus 6.8.0-138-generic #138-Ubuntu SMP PREEMPT_DYNAMIC Fri Jul 31 22:41:49 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
  └ 結果: ✓ Completed (rc=0, 0.005s, 終了 17:07:06)

・ 最終ホスト別結果マトリックス
  ステップ                                    db01   db02   mon01   web01   web02   web03
  ───────────────────────────────────────────────────────────────────────────────────────
  1: ad-hoc: 行内指定で全6ホストの疎通確認     O      O       O       O       O       O  
  2: ad-hoc: RB-LOCALDEF で定義するスタイル    -      -       -       O       O       O  
  3: playbook: 行内 -i と -e(実行時上書き)     -      -       -       O       O       O  
  4: playbook: 行ごとのインベントリ切替        O      O       -       O       O       O  
  5: ad-hoc: 行内指定 + 行内 -e の優先確認     O      O       -       -       -       -  
  └ 記号解説: O=成功  X=失敗  !=到達不能  -=対象外

・ 実行結果: 全ステップ正常終了
No.   ステップ                                 結果     rc     所要   
──────────────────────────────────────────────────────────────────────
  1   ad-hoc: 行内指定で全6ホストの疎通確認    ✓ 完了    0   1.071s   
  2   ad-hoc: RB-LOCALDEF で定義するスタイル   ✓ 完了    0   0.824s   
  3   playbook: 行内 -i と -e(実行時上書き)    ✓ 完了    0    0.54s   
  4   playbook: 行ごとのインベントリ切替       ✓ 完了    0   1.072s   
  5   ad-hoc: 行内指定 + 行内 -e の優先確認    ✓ 完了    0   0.837s   
  6   bash: ローカルステップとの混在確認       ✓ 完了    0   0.005s   
  └ ログ保存先: <LOGDIR>/feature_test_20260831_170702
exit=0
```

### 4.1 生成されるログディレクトリの構成

```
<LOGDIR>/feature_test_20260831_170702/
  env_overlay.sh
  result.json
  run.log
  step01_stderr.txt
  step01_stdout.txt
  step02_stderr.txt
  step02_stdout.txt
  step03_stderr.txt
  step03_stdout.txt
  step04_stderr.txt
  step04_stdout.txt
  step05_stderr.txt
  step05_stdout.txt
  step06_stderr.txt
  step06_stdout.txt
```

`env_overlay.sh` と `result.json` はアトミック書き込み(一時ファイル + rename)を
経由するためパーミッションが `0600` になる。`run.log` は追記なので umask に従う。

### 4.2 `run.log` 全文

```
[2026-08-31 17:07:02] 手順書「機能テスト手順(共通設定なし・全ステップ個別定義スタイル)」実行開始 (samples/local_test/feature_test.md)
[2026-08-31 17:07:02] 作業者: 仕様採取  確認者: 確認者
[2026-08-31 17:07:02] 対象ステップ: [1, 2, 3, 4, 5, 6]
[2026-08-31 17:07:02] --- ステップ 1: ad-hoc: 行内指定で全6ホストの疎通確認 ---
[2026-08-31 17:07:02] コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' all -i samples/local_test/inventory.ini -m shell -a 'echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"'
[2026-08-31 17:07:03] 終了コード: 0  所要時間: 1.071s
[2026-08-31 17:07:03] ホスト別結果: db01=O db02=O mon01=O web01=O web02=O web03=O
[2026-08-31 17:07:03] 判定: OK
[2026-08-31 17:07:03] --- ステップ 2: ad-hoc: RB-LOCALDEF で定義するスタイル ---
[2026-08-31 17:07:03] コマンド: ansible web -i samples/local_test/inventory_web.ini -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -m shell -a uptime
[2026-08-31 17:07:04] 終了コード: 0  所要時間: 0.824s
[2026-08-31 17:07:04] ホスト別結果: web01=O web02=O web03=O
[2026-08-31 17:07:04] 判定: OK
[2026-08-31 17:07:04] --- ステップ 3: playbook: 行内 -i と -e(実行時上書き) ---
[2026-08-31 17:07:04] コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
[2026-08-31 17:07:05] 終了コード: 0  所要時間: 0.54s
[2026-08-31 17:07:05] ホスト別結果: web01=O web02=O web03=O
[2026-08-31 17:07:05] 判定: OK
[2026-08-31 17:07:05] --- ステップ 4: playbook: 行ごとのインベントリ切替 ---
[2026-08-31 17:07:05] コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml && ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
[2026-08-31 17:07:06] 終了コード: 0  所要時間: 1.072s
[2026-08-31 17:07:06] ホスト別結果: db01=O db02=O web01=O web02=O web03=O
[2026-08-31 17:07:06] 判定: OK
[2026-08-31 17:07:06] --- ステップ 5: ad-hoc: 行内指定 + 行内 -e の優先確認 ---
[2026-08-31 17:07:06] コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"'
[2026-08-31 17:07:06] 終了コード: 0  所要時間: 0.837s
[2026-08-31 17:07:06] ホスト別結果: db01=O db02=O
[2026-08-31 17:07:06] 判定: OK
[2026-08-31 17:07:06] --- ステップ 6: bash: ローカルステップとの混在確認 ---
[2026-08-31 17:07:06] コマンド: echo "local step on $(hostname)"
[2026-08-31 17:07:06] uname -a
[2026-08-31 17:07:06] 終了コード: 0  所要時間: 0.005s
[2026-08-31 17:07:06] 判定: OK
[2026-08-31 17:07:06] 実行終了: completed
```

### 4.3 `result.json` 全文

```json
{
  "procedure": {
    "file": "samples/local_test/feature_test.md",
    "title": "機能テスト手順(共通設定なし・全ステップ個別定義スタイル)",
    "mode": "batch",
    "operator": "仕様採取",
    "checker": "確認者",
    "selected_steps": [
      1,
      2,
      3,
      4,
      5,
      6
    ],
    "vars": {
      "CHECK_LABEL": "機能テスト",
      "HOGE": "FUGA"
    },
    "secrets": []
  },
  "status": "completed",
  "started_at": "2026-08-31T17:07:02",
  "finished_at": "2026-08-31T17:07:06",
  "steps": [
    {
      "number": 1,
      "title": "ad-hoc: 行内指定で全6ホストの疎通確認",
      "command": "ansible -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' all -i samples/local_test/inventory.ini -m shell -a 'echo \"{{CHECK_LABEL}}: host={{ inventory_hostname }}\"'",
      "criteria": "rc == 0 and\nout(\"機能テスト: host=web01\") and out(\"機能テスト: host=web02\") and\nout(\"機能テスト: host=web03\") and out(\"機能テスト: host=db01\") and\nout(\"機能テスト: host=db02\") and out(\"機能テスト: host=mon01\") and\nnot out(\"UNREACHABLE|FAILED\")",
      "status": "ok",
      "rc": 0,
      "duration": 1.071,
      "started_at": "2026-08-31T17:07:02",
      "finished_at": "2026-08-31T17:07:03",
      "detail": "",
      "host_results": {
        "web02": "ok",
        "web03": "ok",
        "db01": "ok",
        "web01": "ok",
        "db02": "ok",
        "mon01": "ok"
      },
      "host_matrix": true,
      "criteria_breakdown": []
    },
    {
      "number": 2,
      "title": "ad-hoc: RB-LOCALDEF で定義するスタイル",
      "command": "ansible web -i samples/local_test/inventory_web.ini -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' -m shell -a uptime",
      "criteria": "rc == 0 and out(\"web01\") and out(\"web02\") and out(\"web03\") and\nnot out(\"db01|db02|mon01\") and not out(\"UNREACHABLE|FAILED\")",
      "status": "ok",
      "rc": 0,
      "duration": 0.824,
      "started_at": "2026-08-31T17:07:03",
      "finished_at": "2026-08-31T17:07:04",
      "detail": "",
      "host_results": {
        "web03": "ok",
        "web01": "ok",
        "web02": "ok"
      },
      "host_matrix": true,
      "criteria_breakdown": []
    },
    {
      "number": 3,
      "title": "playbook: 行内 -i と -e(実行時上書き)",
      "command": "ansible-playbook -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO",
      "criteria": "rc == 0 and out(\"HOGE=PIYO\") and not out(\"HOGE=FUGA\") and\nnot out(\"failed=[1-9]|unreachable=[1-9]\")",
      "status": "ok",
      "rc": 0,
      "duration": 0.54,
      "started_at": "2026-08-31T17:07:04",
      "finished_at": "2026-08-31T17:07:05",
      "detail": "",
      "host_results": {
        "web01": "ok",
        "web02": "ok",
        "web03": "ok"
      },
      "host_matrix": true,
      "criteria_breakdown": []
    },
    {
      "number": 4,
      "title": "playbook: 行ごとのインベントリ切替",
      "command": "ansible-playbook -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml && ansible-playbook -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN",
      "criteria": "rc == 0 and\nout(\"HOGE=FUGA \\(host=web01\\)\") and out(\"HOGE=FUGA \\(host=web03\\)\") and\nout(\"HOGE=DB_RUN \\(host=db01\\)\") and out(\"HOGE=DB_RUN \\(host=db02\\)\") and\nnot out(\"failed=[1-9]|unreachable=[1-9]\")",
      "status": "ok",
      "rc": 0,
      "duration": 1.072,
      "started_at": "2026-08-31T17:07:05",
      "finished_at": "2026-08-31T17:07:06",
      "detail": "",
      "host_results": {
        "web01": "ok",
        "web02": "ok",
        "web03": "ok",
        "db01": "ok",
        "db02": "ok"
      },
      "host_matrix": true,
      "criteria_breakdown": []
    },
    {
      "number": 5,
      "title": "ad-hoc: 行内指定 + 行内 -e の優先確認",
      "command": "ansible -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo \"HOGE={{ HOGE }} on {{ inventory_hostname }}\"'",
      "criteria": "rc == 0 and\nout(\"HOGE=ADHOC on db01\") and out(\"HOGE=ADHOC on db02\") and\nnot out(\"HOGE=FUGA\") and not out(\"web01|web02|web03|mon01\") and\nnot out(\"UNREACHABLE|FAILED\")",
      "status": "ok",
      "rc": 0,
      "duration": 0.837,
      "started_at": "2026-08-31T17:07:06",
      "finished_at": "2026-08-31T17:07:06",
      "detail": "",
      "host_results": {
        "db01": "ok",
        "db02": "ok"
      },
      "host_matrix": true,
      "criteria_breakdown": []
    },
    {
      "number": 6,
      "title": "bash: ローカルステップとの混在確認",
      "command": "echo \"local step on $(hostname)\"\nuname -a",
      "criteria": "rc == 0 and \"local step on\" in stdout and out(\"Linux\")",
      "status": "ok",
      "rc": 0,
      "duration": 0.005,
      "started_at": "2026-08-31T17:07:06",
      "finished_at": "2026-08-31T17:07:06",
      "detail": "",
      "host_results": {},
      "host_matrix": false,
      "criteria_breakdown": []
    }
  ]
}
```

---

## 5. 失敗実行の例

判定NG・判定内訳・RB-ONFAIL を確認するためのデモ手順書 `fail_demo.md` を使用する。

### 5.1 手順書本文(`fail_demo.md`)

````markdown
# 失敗例デモ(仕様書の実行例採取用)

```runbook
vars:
  THRESHOLD: "90"
```

## 1. ディスク使用率確認(判定NGになる例)

### RB-DESCRIPTION
閾値 {{THRESHOLD}}% を超えていないことを確認する(このデモでは意図的に超過させる)。

### RB-CMD
```bash
echo "usage=95%"
```

### RB-EXPECTED
```
rc == 0 and out("usage=") and not out("9[0-9]%")
```

### RB-ONFAIL
ディスク使用率が閾値を超過しています。不要ファイルを退避してから
`runbook run --start-from 1` で再実行してください。

## 2. 実行されないステップ

### RB-CMD
```bash
echo "ここには到達しない"
```
````

### 5.2 実行結果

```
$ .venv/bin/runbook run <DEMO_DIR>/fail_demo.md --yes --operator 仕様採取 --log-dir <LOGDIR>
```

終了コード: 1(基準NGによる中断)

```
・ 実行前確認
  ├ 手順書: 失敗例デモ(仕様書の実行例採取用) (<DEMO_DIR>/fail_demo.md)
  ├ モード: 一括
  ├ 実行対象: 2/2 ステップ
  │   1. ディスク使用率確認(判定NGになる例)
  │   2. 実行されないステップ
  └ 変数:
      THRESHOLD = 90

・ 実行開始: 失敗例デモ(仕様書の実行例採取用)
  ├ 作業者: 仕様採取 / 確認者: (なし)
  └ ログ保存先: <LOGDIR>/fail_demo_20260831_170707

・ ステップ 1/2: ディスク使用率確認(判定NGになる例)
  ├ 説明: 閾値 {{THRESHOLD}}% を超えていないことを確認する(このデモでは意図的に超過させる)。
  ├ コマンド (bash)
  │   $ echo "usage=95%"
  ├ 正常性基準: rc == 0 and out("usage=") and not out("9[0-9]%")
  ├ 開始: 2026-08-31 17:07:07
  │   usage=95%
  ├ 詳細: 正常性基準を満たしませんでした
  ├ 判定内訳:
  │   [OK] rc == 0             → 実際 rc=0
  │   [OK] out("usage=")       → stdout の1行がマッチ (初出 L1: usage=95%)
  │   [NG] not out("9[0-9]%")  → stdout の1行がマッチ (初出 L1: usage=95%)
  └ 結果: ✘ Failed (rc=0, 0.003s, 終了 17:07:07)
失敗したため、実行を中断します。

▶ 失敗時ガイダンス (RB-ONFAIL):
  ディスク使用率が閾値を超過しています。不要ファイルを退避してから
  `runbook run --start-from 1` で再実行してください。

・ 実行結果: 実行中断 — ステップ 1「ディスク使用率確認(判定NGになる例)」で失敗
No.   ステップ                             結果       rc     所要         
──────────────────────────────────────────────────────────────────────────
  1   ディスク使用率確認(判定NGになる例)   ✘ 失敗      0   0.003s   ← 中断
  2   実行されないステップ                 - 未実行    -        -         
  └ ログ保存先: <LOGDIR>/fail_demo_20260831_170707
exit=1
```

判定内訳の各行に「実際の出力はどうだったか」が付くため、
`not out("9[0-9]%")` がどの行にマッチして落ちたのかが出力を遡らずに分かる。
末尾のリザルト一覧では、到達しなかったステップ2が `- 未実行` と明示される。

### 5.3 `run.log` 全文

```
[2026-08-31 17:07:07] 手順書「失敗例デモ(仕様書の実行例採取用)」実行開始 (<DEMO_DIR>/fail_demo.md)
[2026-08-31 17:07:07] 作業者: 仕様採取  確認者: (なし)
[2026-08-31 17:07:07] 対象ステップ: [1, 2]
[2026-08-31 17:07:07] --- ステップ 1: ディスク使用率確認(判定NGになる例) ---
[2026-08-31 17:07:07] コマンド: echo "usage=95%"
[2026-08-31 17:07:07] 終了コード: 0  所要時間: 0.003s
[2026-08-31 17:07:07] 判定: NG (正常性基準を満たしませんでした)
[2026-08-31 17:07:07] 判定内訳:
[2026-08-31 17:07:07]   [OK] rc == 0  → 実際 rc=0
[2026-08-31 17:07:07]   [OK] out("usage=")  → stdout の1行がマッチ (初出 L1: usage=95%)
[2026-08-31 17:07:07]   [NG] not out("9[0-9]%")  → stdout の1行がマッチ (初出 L1: usage=95%)
[2026-08-31 17:07:07] 失敗時ガイダンス(RB-ONFAIL):
[2026-08-31 17:07:07] ディスク使用率が閾値を超過しています。不要ファイルを退避してから
[2026-08-31 17:07:07] `runbook run --start-from 1` で再実行してください。
[2026-08-31 17:07:07] 実行終了: aborted
```

### 5.4 `result.json` 全文

```json
{
  "procedure": {
    "file": "<DEMO_DIR>/fail_demo.md",
    "title": "失敗例デモ(仕様書の実行例採取用)",
    "mode": "batch",
    "operator": "仕様採取",
    "checker": "",
    "selected_steps": [
      1,
      2
    ],
    "vars": {
      "THRESHOLD": "90"
    },
    "secrets": []
  },
  "status": "aborted",
  "started_at": "2026-08-31T17:07:07",
  "finished_at": "2026-08-31T17:07:07",
  "steps": [
    {
      "number": 1,
      "title": "ディスク使用率確認(判定NGになる例)",
      "command": "echo \"usage=95%\"",
      "criteria": "rc == 0 and out(\"usage=\") and not out(\"9[0-9]%\")",
      "status": "ng",
      "rc": 0,
      "duration": 0.003,
      "started_at": "2026-08-31T17:07:07",
      "finished_at": "2026-08-31T17:07:07",
      "detail": "正常性基準を満たしませんでした",
      "host_results": {},
      "host_matrix": false,
      "criteria_breakdown": [
        {
          "expr": "rc == 0",
          "ok": true,
          "evidence": "実際 rc=0"
        },
        {
          "expr": "out(\"usage=\")",
          "ok": true,
          "evidence": "stdout の1行がマッチ (初出 L1: usage=95%)"
        },
        {
          "expr": "not out(\"9[0-9]%\")",
          "ok": false,
          "evidence": "stdout の1行がマッチ (初出 L1: usage=95%)"
        }
      ]
    }
  ]
}
```

`steps` には実際に処理されたステップ1のみが含まれ、未到達のステップ2は現れない
(`procedure.selected_steps` には含まれる)。

---

## 6. シークレットマスキングの例

### 6.1 手順書本文(`secrets_demo.md`)

````markdown
# シークレットマスキングデモ(仕様書の実行例採取用)

```runbook
vars:
  DB_PASS: s3cret-value
secrets: [DB_PASS]
```

## 1. パスワードを含むコマンドの実行

### RB-CMD
```bash
echo "connect with password={{DB_PASS}}"
```

### RB-EXPECTED
```
rc == 0 and out("password=")
```
````

### 6.2 実行結果

```
$ .venv/bin/runbook run <DEMO_DIR>/secrets_demo.md --yes --operator 仕様採取 --log-dir <LOGDIR>
```

終了コード: 0

```
・ 実行前確認
  ├ 手順書: シークレットマスキングデモ(仕様書の実行例採取用) (<DEMO_DIR>/secrets_demo.md)
  ├ モード: 一括
  ├ 実行対象: 1/1 ステップ
  │   1. パスワードを含むコマンドの実行
  ├ 変数:
  │   DB_PASS = *****
  └ 秘匿変数(値は表示・ログでマスク): DB_PASS
      注意: export した値は env_overlay.sh に平文で残ります(保管・削除ルールに注意)

・ 実行開始: シークレットマスキングデモ(仕様書の実行例採取用)
  ├ 作業者: 仕様採取 / 確認者: (なし)
  └ ログ保存先: <LOGDIR>/secrets_demo_20260831_170707

・ ステップ 1/1: パスワードを含むコマンドの実行
  ├ コマンド (bash)
  │   $ echo "connect with password=*****"
  ├ 正常性基準: rc == 0 and out("password=")
  ├ 開始: 2026-08-31 17:07:07
  │   connect with password=*****
  └ 結果: ✓ Completed (rc=0, 0.003s, 終了 17:07:07)

・ 実行結果: 全ステップ正常終了
No.   ステップ                         結果     rc     所要   
──────────────────────────────────────────────────────────────
  1   パスワードを含むコマンドの実行   ✓ 完了    0   0.003s   
  └ ログ保存先: <LOGDIR>/secrets_demo_20260831_170707
exit=0
```

変数一覧・コマンド表示・出力中継のすべてで値が `*****` になっている。
判定は生出力に対して行うため、`out("password=")` は正しく真になる。

### 6.3 `run.log`(マスク確認)

```
[2026-08-31 17:07:07] 手順書「シークレットマスキングデモ(仕様書の実行例採取用)」実行開始 (<DEMO_DIR>/secrets_demo.md)
[2026-08-31 17:07:07] 作業者: 仕様採取  確認者: (なし)
[2026-08-31 17:07:07] 対象ステップ: [1]
[2026-08-31 17:07:07] --- ステップ 1: パスワードを含むコマンドの実行 ---
[2026-08-31 17:07:07] コマンド: echo "connect with password=*****"
[2026-08-31 17:07:07] 終了コード: 0  所要時間: 0.003s
[2026-08-31 17:07:07] 判定: OK
[2026-08-31 17:07:07] 実行終了: completed
```

### 6.4 `result.json`(マスク確認)

```json
{
  "procedure": {
    "file": "<DEMO_DIR>/secrets_demo.md",
    "title": "シークレットマスキングデモ(仕様書の実行例採取用)",
    "mode": "batch",
    "operator": "仕様採取",
    "checker": "",
    "selected_steps": [
      1
    ],
    "vars": {
      "DB_PASS": "*****"
    },
    "secrets": [
      "DB_PASS"
    ]
  },
  "status": "completed",
  "started_at": "2026-08-31T17:07:07",
  "finished_at": "2026-08-31T17:07:07",
  "steps": [
    {
      "number": 1,
      "title": "パスワードを含むコマンドの実行",
      "command": "echo \"connect with password=*****\"",
      "criteria": "rc == 0 and out(\"password=\")",
      "status": "ok",
      "rc": 0,
      "duration": 0.003,
      "started_at": "2026-08-31T17:07:07",
      "finished_at": "2026-08-31T17:07:07",
      "detail": "",
      "host_results": {},
      "host_matrix": false,
      "criteria_breakdown": []
    }
  ]
}
```

### 6.5 生出力ファイル(マスク確認)

```
$ cat <LOGDIR>/secrets_demo_20260831_170707/step01_stdout.txt
connect with password=*****
```

生出力ファイルにもマスクが適用される。マスクされないのは実行に必要な
`env_overlay.sh` のみ(05 章 §4・§5)。
