# 06. 実行例集

本書は runbook v0.4.0 の実際の実行出力を採取したもの(採取日 2026-07-18)。

採取環境:

- 作業ディレクトリ: `/home/practi/wk_tool`
- runbook バイナリ: `.venv/bin/runbook`(バージョン 0.4.0)
- OS: Linux practicus 6.8.0-134-generic

以降のコマンド例で `<LOGDIR>` は
`/tmp/claude-1000/-home-practi-wk-tool/f7951314-eaa0-485c-ac2f-8f71e5a71db4/scratchpad/capture_logs`
を指す(本書執筆時の一時ログ出力先。実運用では既定の `./logs` などを使う)。

また `<DEMO_DIR>` は、5〜7節のデモ手順書(`fail_demo.md` / `secrets_demo.md`)を
配置した一時ディレクトリ
`/tmp/claude-1000/-home-practi-wk-tool/f7951314-eaa0-485c-ac2f-8f71e5a71db4/scratchpad`
を指す(実行コマンドではこのディレクトリ配下のファイルを絶対パスで指定した)。
出力中のこの2つのパスのみを可読性のため `<LOGDIR>` / `<DEMO_DIR>` に置換しており、
それ以外は実際の出力をそのまま掲載している。

---

## 1. バージョン・ヘルプ表示

### 1.1 `--version`

実行場所: `/home/practi/wk_tool`

```
$ .venv/bin/runbook --version
```

終了コード: 0

```
runbook 0.4.0
exit=0
```

### 1.2 `--help`(メインコマンド)

```
$ .venv/bin/runbook --help
```

終了コード: 0

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

終了コード: 0

```
usage: runbook run [-h] [--var KEY=VALUE] [-i] [--only SPEC] [--from N]
                   [--to N] [--start-from N] [--rollback] [-y]
                   [--operator NAME] [--checker NAME] [--log-dir LOG_DIR]
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
  --start-from N     ステップ N から最後まで再開実行する。share_env: true
                     の手順書では直近実行の環境変数(shared_env.sh)を復元する(見つからなければエラー)
  --rollback         切り戻しセクション(# RB-ROLLBACK 以降)のステップを実行する
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

終了コード: 0

```
usage: runbook check [-h] [--var KEY=VALUE] [--preview] file

positional arguments:
  file             手順書 Markdown ファイル

options:
  -h, --help       show this help message and exit
  --var KEY=VALUE  変数の指定/上書き(複数可)
  --preview        変数展開・ansibleコマンド組み立て後の実行コマンドを全文表示する
exit=0
```

### 1.5 `list --help`

```
$ .venv/bin/runbook list --help
```

終了コード: 0

```
usage: runbook list [-h] [--var KEY=VALUE] file

positional arguments:
  file             手順書 Markdown ファイル

options:
  -h, --help       show this help message and exit
  --var KEY=VALUE  変数の指定/上書き(複数可)
exit=0
```

### 1.6 `renumber --help`

```
$ .venv/bin/runbook renumber --help
```

終了コード: 0

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

サマリー行を含む全出力:

```
........................................................................ [ 72%]
...........................                                              [100%]
99 passed in 0.65s
exit=0
```

99 件全てパス、失敗・エラーなし。

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

### 3.2 `check --preview`(変数展開後の実行コマンドを全文表示)

```
$ .venv/bin/runbook check --preview samples/local_test/feature_test.md
```

終了コード: 0

```
OK samples/local_test/feature_test.md: 6 ステップ、書式・基準式に問題ありません

・ 展開後コマンド プレビュー
・ ステップ 1: ad-hoc: 行内指定で全6ホストの疎通確認
    $ ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' all -i samples/local_test/inventory.ini -m shell -a 'echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"'
    基準: rc == 0 and
out("機能テスト: host=web01") and out("機能テスト: host=web02") and
out("機能テスト: host=web03") and out("機能テスト: host=db01") and
out("機能テスト: host=db02") and out("機能テスト: host=mon01") and
not out("UNREACHABLE|FAILED")
・ ステップ 2: ad-hoc: RB-LOCALDEF で定義するスタイル
    $ ansible web -i samples/local_test/inventory_web.ini -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -m shell -a uptime
    基準: rc == 0 and out("web01") and out("web02") and out("web03") and
not out("db01|db02|mon01") and not out("UNREACHABLE|FAILED")
・ ステップ 3: playbook: 行内 -i と -e(実行時上書き)
    $ ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
    基準: rc == 0 and out("HOGE=PIYO") and not out("HOGE=FUGA") and
not out("failed=[1-9]|unreachable=[1-9]")
・ ステップ 4: playbook: 行ごとのインベントリ切替
    $ ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml && ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
    基準: rc == 0 and
out("HOGE=FUGA \(host=web01\)") and out("HOGE=FUGA \(host=web03\)") and
out("HOGE=DB_RUN \(host=db01\)") and out("HOGE=DB_RUN \(host=db02\)") and
not out("failed=[1-9]|unreachable=[1-9]")
・ ステップ 5: ad-hoc: 行内指定 + 行内 -e の優先確認
    $ ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"'
    基準: rc == 0 and
out("HOGE=ADHOC on db01") and out("HOGE=ADHOC on db02") and
not out("HOGE=FUGA") and not out("web01|web02|web03|mon01") and
not out("UNREACHABLE|FAILED")
・ ステップ 6: bash: ローカルステップとの混在確認
    $ echo "local step on $(hostname)"
    $ uname -a
    基準: rc == 0 and "local step on" in stdout and out("Linux")
exit=0
```

### 3.3 `list`(ステップ一覧の表形式表示)

```
$ .venv/bin/runbook list samples/local_test/feature_test.md
```

終了コード: 0

```
機能テスト手順(共通設定なし・全ステップ個別定義スタイル) (samples/local_test/feature_test.md)
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┓
┃ No. ┃ ステップ              ┃ コマンド               ┃ 正常性基準            ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━┩
│   1 │ ad-hoc:               │ ansible -e             │ rc == 0 and           │
│     │ 行内指定で全6ホスト … │ '{"CHECK_LABEL":       │ out("機能テスト:      │
│     │                       │ "機能テスト", "HOGE":  │ host=web01") and      │
│     │                       │ "FUGA"}' all...        │ out("機能テスト:      │
│     │                       │                        │ host=web02") and      │
│     │                       │                        │ out("機能テスト:      │
│     │                       │                        │ host=web03") and      │
│     │                       │                        │ out("機能テスト:      │
│     │                       │                        │ host=db01") and       │
│     │                       │                        │ out("機能テスト:      │
│     │                       │                        │ host=db02") and       │
│     │                       │                        │ out("機能テスト:      │
│     │                       │                        │ host=mon01") and      │
│     │                       │                        │ not                   │
│     │                       │                        │ out("UNREACHABLE|FAIL │
│     │                       │                        │ ED")                  │
│   2 │ ad-hoc: RB-LOCALDEF   │ ansible web -i         │ rc == 0 and           │
│     │ で定義するスタイル    │ samples/local_test/inv │ out("web01") and      │
│     │                       │ entory_web.ini -e      │ out("web02") and      │
│     │                       │ '{...                  │ out("web03") and      │
│     │                       │                        │ not                   │
│     │                       │                        │ out("db01|db02|mon01" │
│     │                       │                        │ ) and not             │
│     │                       │                        │ out("UNREACHABLE|FAIL │
│     │                       │                        │ ED")                  │
│   3 │ playbook: 行内 -i と  │ ansible-playbook -e    │ rc == 0 and           │
│     │ -e(実行時上書き)      │ '{"CHECK_LABEL":       │ out("HOGE=PIYO") and  │
│     │                       │ "機能テスト", "HOGE":  │ not out("HOGE=FUGA")  │
│     │                       │ "FU...                 │ and                   │
│     │                       │                        │ not                   │
│     │                       │                        │ out("failed=[1-9]|unr │
│     │                       │                        │ eachable=[1-9]")      │
│   4 │ playbook:             │ ansible-playbook -e    │ rc == 0 and           │
│     │ 行ごとのインベントリ… │ '{"CHECK_LABEL":       │ out("HOGE=FUGA        │
│     │                       │ "機能テスト", "HOGE":  │ \(host=web01\)") and  │
│     │                       │ "FU...                 │ out("HOGE=FUGA        │
│     │                       │                        │ \(host=web03\)") and  │
│     │                       │                        │ out("HOGE=DB_RUN      │
│     │                       │                        │ \(host=db01\)") and   │
│     │                       │                        │ out("HOGE=DB_RUN      │
│     │                       │                        │ \(host=db02\)") and   │
│     │                       │                        │ not                   │
│     │                       │                        │ out("failed=[1-9]|unr │
│     │                       │                        │ eachable=[1-9]")      │
│   5 │ ad-hoc: 行内指定 +    │ ansible -e             │ rc == 0 and           │
│     │ 行内 -e の優先確認    │ '{"CHECK_LABEL":       │ out("HOGE=ADHOC on    │
│     │                       │ "機能テスト", "HOGE":  │ db01") and            │
│     │                       │ "FUGA"}' db ...        │ out("HOGE=ADHOC on    │
│     │                       │                        │ db02") and            │
│     │                       │                        │ not out("HOGE=FUGA")  │
│     │                       │                        │ and not               │
│     │                       │                        │ out("web01|web02|web0 │
│     │                       │                        │ 3|mon01") and         │
│     │                       │                        │ not                   │
│     │                       │                        │ out("UNREACHABLE|FAIL │
│     │                       │                        │ ED")                  │
│   6 │ bash:                 │ echo "local step on    │ rc == 0 and "local    │
│     │ ローカルステップとの… │ $(hostname)"           │ step on" in stdout    │
│     │                       │ uname -a               │ and out("Linux")      │
└─────┴───────────────────────┴────────────────────────┴───────────────────────┘
exit=0
```

---

## 4. 成功実行の例

対象手順書: `samples/local_test/feature_test.md`(全6ステップ、ansible 疑似6ホスト構成)

実行場所: `/home/practi/wk_tool`

```
$ .venv/bin/runbook run --yes --operator 仕様採取 --log-dir <LOGDIR> samples/local_test/feature_test.md
```

終了コード: 0(全ステップ正常終了)。生成されたログディレクトリは
`<LOGDIR>/feature_test_20260718_104500`。

ターミナル全出力:

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
  ├ 使用インベントリ:
  │   samples/local_test/inventory.ini
  │   samples/local_test/inventory_db.ini
  │   samples/local_test/inventory_web.ini
  └ 切り戻しセクション: なし

・ 実行開始: 機能テスト手順(共通設定なし・全ステップ個別定義スタイル)
  ├ 作業者: 仕様採取 / 確認者: (なし)
  └ ログ保存先: <LOGDIR>/feature_test_20260718_104500

・ ステップ 1/6: ad-hoc: 行内指定で全6ホストの疎通確認
  ├ 説明: フェンス1行目の「ansible ターゲット -i インベントリ」が起動指定として使われる。
  │   期待結果: 6ホスト全てが CHANGED、ホスト別結果マトリックスに O が6つ並ぶ。
  ├ コマンド (ansible ad-hoc / shellモジュール):
  │   $ echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"
  ├ 実行コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' all -i samples/local_test/inventory.ini -m shell -a 'echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"'
  ├ 正常性基準: rc == 0 and
  │   out("機能テスト: host=web01") and out("機能テスト: host=web02") and
  │   out("機能テスト: host=web03") and out("機能テスト: host=db01") and
  │   out("機能テスト: host=db02") and out("機能テスト: host=mon01") and
  │   not out("UNREACHABLE|FAILED")
  ├ 開始: 2026-07-18 10:45:00
  │   web03 | CHANGED | rc=0 >>
  │   機能テスト: host=web03
  │   web01 | CHANGED | rc=0 >>
  │   機能テスト: host=web01
  │   web02 | CHANGED | rc=0 >>
  │   機能テスト: host=web02
  │   db02 | CHANGED | rc=0 >>
  │   機能テスト: host=db02
  │   db01 | CHANGED | rc=0 >>
  │   機能テスト: host=db01
  │   mon01 | CHANGED | rc=0 >>
  │   機能テスト: host=mon01
  ├ ホスト別結果:
  │                                                     
  │        db01   db02   mon01   web01   web02   web03  
  │    ──────────────────────────────────────────────── 
  │         O      O       O       O       O       O    
  │                                                     
  │   O=成功  X=失敗  !=到達不能  -=対象外
  ├ 終了: 2026-07-18 10:45:01
  └ 結果: ✓ Completed (rc=0, 1.153s)

・ ステップ 2/6: ad-hoc: RB-LOCALDEF で定義するスタイル
  ├ 説明: 行内指定の代わりに、ステップの RB-LOCALDEF で inventory / target を定義する書き方。
  │   期待結果: web系3ホストのみで実行される。
  ├ コマンド (ansible ad-hoc / shellモジュール):
  │   $ uptime
  ├ 実行コマンド: ansible web -i samples/local_test/inventory_web.ini -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -m shell -a uptime
  ├ 正常性基準: rc == 0 and out("web01") and out("web02") and out("web03") and
  │   not out("db01|db02|mon01") and not out("UNREACHABLE|FAILED")
  ├ 開始: 2026-07-18 10:45:01
  │   web02 | CHANGED | rc=0 >>
  │    10:45:02 up 14 min,  1 user,  load average: 0.40, 0.57, 0.64
  │   web03 | CHANGED | rc=0 >>
  │    10:45:02 up 14 min,  1 user,  load average: 0.40, 0.57, 0.64
  │   web01 | CHANGED | rc=0 >>
  │    10:45:02 up 14 min,  1 user,  load average: 0.40, 0.57, 0.64
  ├ ホスト別結果:
  │                               
  │        web01   web02   web03  
  │    ────────────────────────── 
  │          O       O       O    
  │                               
  │   O=成功  X=失敗  !=到達不能  -=対象外
  ├ 終了: 2026-07-18 10:45:02
  └ 結果: ✓ Completed (rc=0, 0.813s)

・ ステップ 3/6: playbook: 行内 -i と -e(実行時上書き)
  ├ 説明: プレイブック行に -i(インベントリ)と -e(実行時に変えたい値)を直接書く。
  │   手順書変数 HOGE=FUGA は自動の -e JSON で渡るが、行内の -e HOGE=PIYO が優先される。
  │   期待結果: web系3ホストで実行され、出力が HOGE=PIYO になる(FUGA ではない)。
  ├ プレイブック (ansible-playbook):
  │   -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
  ├ 実行コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
  ├ 正常性基準: rc == 0 and out("HOGE=PIYO") and not out("HOGE=FUGA") and
  │   not out("failed=[1-9]|unreachable=[1-9]")
  ├ 開始: 2026-07-18 10:45:02
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
  ├ ホスト別結果:
  │                               
  │        web01   web02   web03  
  │    ────────────────────────── 
  │          O       O       O    
  │                               
  │   O=成功  X=失敗  !=到達不能  -=対象外
  ├ 終了: 2026-07-18 10:45:02
  └ 結果: ✓ Completed (rc=0, 0.558s)

・ ステップ 4/6: playbook: 行ごとのインベントリ切替
  ├ 説明: 処理系統ごとにインベントリを分ける運用の確認。行ごとに -i を書き分ける。
  │   2行は && 連結で順に実行され、1行目が失敗したら2行目は実行されない。
  │   期待結果: 1行目は web系3ホスト(HOGE=FUGA)、2行目は db系2ホスト(HOGE=DB_RUN)で実行され、
  │   マトリックスには両系統のホストがマージされて表示される。
  ├ プレイブック (ansible-playbook):
  │   -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml
  │   -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
  ├ 実行コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml && ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
  ├ 正常性基準: rc == 0 and
  │   out("HOGE=FUGA \(host=web01\)") and out("HOGE=FUGA \(host=web03\)") and
  │   out("HOGE=DB_RUN \(host=db01\)") and out("HOGE=DB_RUN \(host=db02\)") and
  │   not out("failed=[1-9]|unreachable=[1-9]")
  ├ 開始: 2026-07-18 10:45:02
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
  ├ ホスト別結果:
  │                                             
  │        db01   db02   web01   web02   web03  
  │    ──────────────────────────────────────── 
  │         O      O       O       O       O    
  │                                             
  │   O=成功  X=失敗  !=到達不能  -=対象外
  ├ 終了: 2026-07-18 10:45:03
  └ 結果: ✓ Completed (rc=0, 1.064s)

・ ステップ 5/6: ad-hoc: 行内指定 + 行内 -e の優先確認
  ├ 説明: 起動指定行に -e HOGE=ADHOC を書くと、自動付与の手順書変数(HOGE=FUGA)より優先される。
  │   2行目以降のリモートコマンドでは jinja2({{ HOGE }} や {{ inventory_hostname }})が使える。
  │   期待結果: db系2ホストのみで実行され、出力が HOGE=ADHOC になる。
  ├ コマンド (ansible ad-hoc / shellモジュール):
  │   $ echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"
  ├ 実行コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"'
  ├ 正常性基準: rc == 0 and
  │   out("HOGE=ADHOC on db01") and out("HOGE=ADHOC on db02") and
  │   not out("HOGE=FUGA") and not out("web01|web02|web03|mon01") and
  │   not out("UNREACHABLE|FAILED")
  ├ 開始: 2026-07-18 10:45:03
  │   db01 | CHANGED | rc=0 >>
  │   HOGE=ADHOC on db01
  │   db02 | CHANGED | rc=0 >>
  │   HOGE=ADHOC on db02
  ├ ホスト別結果:
  │                     
  │        db01   db02  
  │    ──────────────── 
  │         O      O    
  │                     
  │   O=成功  X=失敗  !=到達不能  -=対象外
  ├ 終了: 2026-07-18 10:45:04
  └ 結果: ✓ Completed (rc=0, 0.804s)

・ ステップ 6/6: bash: ローカルステップとの混在確認
  ├ 説明: 同じ手順書内に bash ステップも混在できることの確認。ansible の設定は一切不要。
  │   期待結果: OK。このステップは ansible ではないためホスト別結果は表示されない。
  ├ コマンド:
  │   $ echo "local step on $(hostname)"
  │   $ uname -a
  ├ 正常性基準: rc == 0 and "local step on" in stdout and out("Linux")
  ├ 開始: 2026-07-18 10:45:04
  │   local step on practicus
  │   Linux practicus 6.8.0-134-generic #134-Ubuntu SMP PREEMPT_DYNAMIC Fri Jun 26 18:43:11 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
  ├ 終了: 2026-07-18 10:45:04
  └ 結果: ✓ Completed (rc=0, 0.005s)

・ 最終ホスト別結果マトリックス
                                                                                  
    ステップ                         db01   db02   mon01   web01   web02   web03  
   ────────────────────────────────────────────────────────────────────────────── 
    1: ad-hoc:                        O      O       O       O       O       O    
    行内指定で全6ホストの疎通確認                                                 
    2: ad-hoc: RB-LOCALDEF            -      -       -       O       O       O    
    で定義するスタイル                                                            
    3: playbook: 行内 -i と           -      -       -       O       O       O    
    -e(実行時上書き)                                                              
    4: playbook:                      O      O       -       O       O       O    
    行ごとのインベントリ切替                                                      
    5: ad-hoc: 行内指定 + 行内 -e     O      O       -       -       -       -    
    の優先確認                                                                    
                                                                                  
  └ 記号解説: O=成功  X=失敗  !=到達不能  -=対象外

・ 実行結果: 全ステップ正常終了
  └ ログ保存先: <LOGDIR>/feature_test_20260718_104500
exit=0
```

### 4.1 生成されるログディレクトリの構成

```
$ ls -la <LOGDIR>/feature_test_20260718_104500
```

```
合計 44
drwxrwxr-x 2 practi practi 4096  7月 18 10:45 .
drwxrwxr-x 3 practi practi 4096  7月 18 10:45 ..
-rw-rw-r-- 1 practi practi 5456  7月 18 10:45 result.json
-rw-rw-r-- 1 practi practi 3073  7月 18 10:45 run.log
-rw-rw-r-- 1 practi practi    0  7月 18 10:45 step01_stderr.txt
-rw-rw-r-- 1 practi practi  320  7月 18 10:45 step01_stdout.txt
-rw-rw-r-- 1 practi practi    0  7月 18 10:45 step02_stderr.txt
-rw-rw-r-- 1 practi practi  264  7月 18 10:45 step02_stdout.txt
-rw-rw-r-- 1 practi practi    0  7月 18 10:45 step03_stderr.txt
-rw-rw-r-- 1 practi practi  778  7月 18 10:45 step03_stdout.txt
-rw-rw-r-- 1 practi practi    0  7月 18 10:45 step04_stderr.txt
-rw-rw-r-- 1 practi practi 1383  7月 18 10:45 step04_stdout.txt
-rw-rw-r-- 1 practi practi    0  7月 18 10:45 step05_stderr.txt
-rw-rw-r-- 1 practi practi   88  7月 18 10:45 step05_stdout.txt
-rw-rw-r-- 1 practi practi    0  7月 18 10:45 step06_stderr.txt
-rw-rw-r-- 1 practi practi  150  7月 18 10:45 step06_stdout.txt
```

ステップごとに `stepNN_stdout.txt` / `stepNN_stderr.txt` が生成され、実行ログ全体は `run.log`、構造化結果は `result.json` にまとめられる。

### 4.2 `run.log` 全文

```
[2026-07-18 10:45:00] 手順書「機能テスト手順(共通設定なし・全ステップ個別定義スタイル)」実行開始 (samples/local_test/feature_test.md)
[2026-07-18 10:45:00] 作業者: 仕様採取  確認者: (なし)
[2026-07-18 10:45:00] 対象ステップ: [1, 2, 3, 4, 5, 6]
[2026-07-18 10:45:00] --- ステップ 1: ad-hoc: 行内指定で全6ホストの疎通確認 ---
[2026-07-18 10:45:00] コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' all -i samples/local_test/inventory.ini -m shell -a 'echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"'
[2026-07-18 10:45:01] 終了コード: 0  所要時間: 1.153s
[2026-07-18 10:45:01] ホスト別結果: db01=O db02=O mon01=O web01=O web02=O web03=O
[2026-07-18 10:45:01] 判定: OK
[2026-07-18 10:45:01] --- ステップ 2: ad-hoc: RB-LOCALDEF で定義するスタイル ---
[2026-07-18 10:45:01] コマンド: ansible web -i samples/local_test/inventory_web.ini -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -m shell -a uptime
[2026-07-18 10:45:02] 終了コード: 0  所要時間: 0.813s
[2026-07-18 10:45:02] ホスト別結果: web01=O web02=O web03=O
[2026-07-18 10:45:02] 判定: OK
[2026-07-18 10:45:02] --- ステップ 3: playbook: 行内 -i と -e(実行時上書き) ---
[2026-07-18 10:45:02] コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
[2026-07-18 10:45:02] 終了コード: 0  所要時間: 0.558s
[2026-07-18 10:45:02] ホスト別結果: web01=O web02=O web03=O
[2026-07-18 10:45:02] 判定: OK
[2026-07-18 10:45:02] --- ステップ 4: playbook: 行ごとのインベントリ切替 ---
[2026-07-18 10:45:02] コマンド: ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_web.ini samples/local_test/show_var.yml && ansible-playbook -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' -i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
[2026-07-18 10:45:03] 終了コード: 0  所要時間: 1.064s
[2026-07-18 10:45:03] ホスト別結果: db01=O db02=O web01=O web02=O web03=O
[2026-07-18 10:45:03] 判定: OK
[2026-07-18 10:45:03] --- ステップ 5: ad-hoc: 行内指定 + 行内 -e の優先確認 ---
[2026-07-18 10:45:03] コマンド: ansible -e '{"CHECK_LABEL": "機能テスト", "HOGE": "FUGA"}' db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC -m shell -a 'echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"'
[2026-07-18 10:45:04] 終了コード: 0  所要時間: 0.804s
[2026-07-18 10:45:04] ホスト別結果: db01=O db02=O
[2026-07-18 10:45:04] 判定: OK
[2026-07-18 10:45:04] --- ステップ 6: bash: ローカルステップとの混在確認 ---
[2026-07-18 10:45:04] コマンド: echo "local step on $(hostname)"
[2026-07-18 10:45:04] uname -a
[2026-07-18 10:45:04] 終了コード: 0  所要時間: 0.005s
[2026-07-18 10:45:04] 判定: OK
[2026-07-18 10:45:04] 実行終了: completed
```

### 4.3 `result.json` 全文

```json
{
  "procedure": {
    "file": "samples/local_test/feature_test.md",
    "title": "機能テスト手順(共通設定なし・全ステップ個別定義スタイル)",
    "mode": "batch",
    "rollback": false,
    "operator": "仕様採取",
    "checker": "",
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
    "secrets": [],
    "share_env": false
  },
  "status": "completed",
  "started_at": "2026-07-18T10:45:00",
  "finished_at": "2026-07-18T10:45:04",
  "steps": [
    {
      "number": 1,
      "title": "ad-hoc: 行内指定で全6ホストの疎通確認",
      "command": "ansible -e '{\"CHECK_LABEL\": \"機能テスト\", \"HOGE\": \"FUGA\"}' all -i samples/local_test/inventory.ini -m shell -a 'echo \"{{CHECK_LABEL}}: host={{ inventory_hostname }}\"'",
      "criteria": "rc == 0 and\nout(\"機能テスト: host=web01\") and out(\"機能テスト: host=web02\") and\nout(\"機能テスト: host=web03\") and out(\"機能テスト: host=db01\") and\nout(\"機能テスト: host=db02\") and out(\"機能テスト: host=mon01\") and\nnot out(\"UNREACHABLE|FAILED\")",
      "status": "ok",
      "rc": 0,
      "duration": 1.153,
      "started_at": "2026-07-18T10:45:00",
      "finished_at": "2026-07-18T10:45:01",
      "detail": "",
      "host_results": {
        "web03": "ok",
        "web01": "ok",
        "web02": "ok",
        "db02": "ok",
        "db01": "ok",
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
      "duration": 0.813,
      "started_at": "2026-07-18T10:45:01",
      "finished_at": "2026-07-18T10:45:02",
      "detail": "",
      "host_results": {
        "web02": "ok",
        "web03": "ok",
        "web01": "ok"
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
      "duration": 0.558,
      "started_at": "2026-07-18T10:45:02",
      "finished_at": "2026-07-18T10:45:02",
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
      "duration": 1.064,
      "started_at": "2026-07-18T10:45:02",
      "finished_at": "2026-07-18T10:45:03",
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
      "duration": 0.804,
      "started_at": "2026-07-18T10:45:03",
      "finished_at": "2026-07-18T10:45:04",
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
      "started_at": "2026-07-18T10:45:04",
      "finished_at": "2026-07-18T10:45:04",
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

判定NG・RB-ONFAIL・切り戻し案内を確認するためのデモ手順書 `fail_demo.md` を使用する。

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

# RB-ROLLBACK

## 1. 切り戻し例

### RB-CMD
```bash
echo "rollback done"
```
````

### 5.2 実行結果

実行場所: `/home/practi/wk_tool`(手順書は `<DEMO_DIR>/fail_demo.md` を絶対パスで指定)

```
$ .venv/bin/runbook run --yes --operator 仕様採取 --log-dir <LOGDIR> <DEMO_DIR>/fail_demo.md
```

終了コード: 1(判定NGによる中断)。生成されたログディレクトリは
`<LOGDIR>/fail_demo_20260718_104520`。

ターミナル全出力:

```
・ 実行前確認
  ├ 手順書: 失敗例デモ(仕様書の実行例採取用) (<DEMO_DIR>/fail_demo.md)
  ├ モード: 一括
  ├ 実行対象: 2/2 ステップ
  │   1. ディスク使用率確認(判定NGになる例)
  │   2. 実行されないステップ
  ├ 変数:
  │   THRESHOLD = 90
  └ 切り戻しセクション: あり(1 ステップ。中断時に案内)

・ 実行開始: 失敗例デモ(仕様書の実行例採取用)
  ├ 作業者: 仕様採取 / 確認者: (なし)
  └ ログ保存先: <LOGDIR>/fail_demo_20260718_104520

・ ステップ 1/2: ディスク使用率確認(判定NGになる例)
  ├ 説明: 閾値 {{THRESHOLD}}% を超えていないことを確認する(このデモでは意図的に超過させる)。
  ├ コマンド:
  │   $ echo "usage=95%"
  ├ 正常性基準: rc == 0 and out("usage=") and not out("9[0-9]%")
  ├ 開始: 2026-07-18 10:45:20
  │   usage=95%
  ├ 終了: 2026-07-18 10:45:20
  ├ 詳細: 正常性基準を満たしませんでした
  ├ 判定内訳:
  │   [OK] rc == 0
  │   [OK] out("usage=")
  │   [NG] not out("9[0-9]%")
  └ 結果: ✘ Failed (rc=0, 0.002s)
失敗したため、実行を中断します。

▶ 失敗時ガイダンス (RB-ONFAIL):
  ディスク使用率が閾値を超過しています。不要ファイルを退避してから
  `runbook run --start-from 1` で再実行してください。

・ 実行結果: 実行中断
  └ ログ保存先: <LOGDIR>/fail_demo_20260718_104520
▶ この手順書には切り戻しセクションがあります(1 ステップ)。切り戻す場合は次を実行:
    runbook run --rollback <DEMO_DIR>/fail_demo.md
exit=1
```

判定基準は `rc == 0` と `out("usage=")` は OK だが、`not out("9[0-9]%")` が NG となったため
ステップ全体は失敗と判定され、判定内訳(`[OK]`/`[NG]`)が式ごとに表示される。以降のステップ
(ステップ2)は実行されず、RB-ONFAIL の案内文とロールバック実行コマンドが表示されて
終了コード 1 で終了する。

### 5.3 `run.log` 全文

```
[2026-07-18 10:45:20] 手順書「失敗例デモ(仕様書の実行例採取用)」実行開始 (<DEMO_DIR>/fail_demo.md)
[2026-07-18 10:45:20] 作業者: 仕様採取  確認者: (なし)
[2026-07-18 10:45:20] 対象ステップ: [1, 2]
[2026-07-18 10:45:20] --- ステップ 1: ディスク使用率確認(判定NGになる例) ---
[2026-07-18 10:45:20] コマンド: echo "usage=95%"
[2026-07-18 10:45:20] 終了コード: 0  所要時間: 0.002s
[2026-07-18 10:45:20] 判定: NG (正常性基準を満たしませんでした)
[2026-07-18 10:45:20] 判定内訳:
[2026-07-18 10:45:20]   [OK] rc == 0
[2026-07-18 10:45:20]   [OK] out("usage=")
[2026-07-18 10:45:20]   [NG] not out("9[0-9]%")
[2026-07-18 10:45:20] 失敗時ガイダンス(RB-ONFAIL):
[2026-07-18 10:45:20] ディスク使用率が閾値を超過しています。不要ファイルを退避してから
[2026-07-18 10:45:20] `runbook run --start-from 1` で再実行してください。
[2026-07-18 10:45:20] 切り戻し案内: runbook run --rollback <DEMO_DIR>/fail_demo.md
[2026-07-18 10:45:20] 実行終了: aborted
```

ステップ2(「実行されないステップ」)は判定NGにより実行されなかったため、ログに一切記録
されない。生成されるファイルも `step01_stdout.txt` / `step01_stderr.txt` のみで、
`step02_*` は作成されない。

### 5.4 `result.json` 全文

```json
{
  "procedure": {
    "file": "<DEMO_DIR>/fail_demo.md",
    "title": "失敗例デモ(仕様書の実行例採取用)",
    "mode": "batch",
    "rollback": false,
    "operator": "仕様採取",
    "checker": "",
    "selected_steps": [
      1,
      2
    ],
    "vars": {
      "THRESHOLD": "90"
    },
    "secrets": [],
    "share_env": false
  },
  "status": "aborted",
  "started_at": "2026-07-18T10:45:20",
  "finished_at": "2026-07-18T10:45:20",
  "steps": [
    {
      "number": 1,
      "title": "ディスク使用率確認(判定NGになる例)",
      "command": "echo \"usage=95%\"",
      "criteria": "rc == 0 and out(\"usage=\") and not out(\"9[0-9]%\")",
      "status": "ng",
      "rc": 0,
      "duration": 0.002,
      "started_at": "2026-07-18T10:45:20",
      "finished_at": "2026-07-18T10:45:20",
      "detail": "正常性基準を満たしませんでした",
      "host_results": {},
      "host_matrix": false,
      "criteria_breakdown": [
        {
          "expr": "rc == 0",
          "ok": true
        },
        {
          "expr": "out(\"usage=\")",
          "ok": true
        },
        {
          "expr": "not out(\"9[0-9]%\")",
          "ok": false
        }
      ]
    }
  ]
}
```

`status` が `aborted` となり、`steps` 配列にはステップ1のみが記録される。
`criteria_breakdown` に各判定式(`expr`)ごとの真偽(`ok`)が記録されている点に注意。

---

## 6. シークレットマスキングの例

`secrets:` に指定した変数の値がターミナル出力・`run.log`・`result.json`・生ログファイル
(`stepNN_stdout.txt`)の全てでマスクされることを確認するためのデモ手順書
`secrets_demo.md` を使用する。

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

実行場所: `/home/practi/wk_tool`(手順書は `<DEMO_DIR>/secrets_demo.md` を絶対パスで指定)

```
$ .venv/bin/runbook run --yes --operator 仕様採取 --log-dir <LOGDIR> <DEMO_DIR>/secrets_demo.md
```

終了コード: 0。生成されたログディレクトリは `<LOGDIR>/secrets_demo_20260718_104530`。

ターミナル全出力:

```
・ 実行前確認
  ├ 手順書: シークレットマスキングデモ(仕様書の実行例採取用) (<DEMO_DIR>/secrets_demo.md)
  ├ モード: 一括
  ├ 実行対象: 1/1 ステップ
  │   1. パスワードを含むコマンドの実行
  ├ 変数:
  │   DB_PASS = *****
  ├ 秘匿変数(値は表示・ログでマスク): DB_PASS
  └ 切り戻しセクション: なし

・ 実行開始: シークレットマスキングデモ(仕様書の実行例採取用)
  ├ 作業者: 仕様採取 / 確認者: (なし)
  └ ログ保存先: <LOGDIR>/secrets_demo_20260718_104530

・ ステップ 1/1: パスワードを含むコマンドの実行
  ├ コマンド:
  │   $ echo "connect with password=*****"
  ├ 正常性基準: rc == 0 and out("password=")
  ├ 開始: 2026-07-18 10:45:30
  │   connect with password=*****
  ├ 終了: 2026-07-18 10:45:30
  └ 結果: ✓ Completed (rc=0, 0.002s)

・ 実行結果: 全ステップ正常終了
  └ ログ保存先: <LOGDIR>/secrets_demo_20260718_104530
exit=0
```

実行前サマリーの「変数」欄・「コマンド」欄・実際の標準出力表示のいずれも
`s3cret-value` ではなく `*****` に置き換わっている。

### 6.3 `run.log`(マスク確認)

```
[2026-07-18 10:45:30] 手順書「シークレットマスキングデモ(仕様書の実行例採取用)」実行開始 (<DEMO_DIR>/secrets_demo.md)
[2026-07-18 10:45:30] 作業者: 仕様採取  確認者: (なし)
[2026-07-18 10:45:30] 対象ステップ: [1]
[2026-07-18 10:45:30] --- ステップ 1: パスワードを含むコマンドの実行 ---
[2026-07-18 10:45:30] コマンド: echo "connect with password=*****"
[2026-07-18 10:45:30] 終了コード: 0  所要時間: 0.002s
[2026-07-18 10:45:30] 判定: OK
[2026-07-18 10:45:30] 実行終了: completed
```

`コマンド:` 行の実行コマンド文字列自体も `*****` にマスクされてログへ記録される。

### 6.4 `result.json`(マスク確認)

```json
{
  "procedure": {
    "file": "<DEMO_DIR>/secrets_demo.md",
    "title": "シークレットマスキングデモ(仕様書の実行例採取用)",
    "mode": "batch",
    "rollback": false,
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
    ],
    "share_env": false
  },
  "status": "completed",
  "started_at": "2026-07-18T10:45:30",
  "finished_at": "2026-07-18T10:45:30",
  "steps": [
    {
      "number": 1,
      "title": "パスワードを含むコマンドの実行",
      "command": "echo \"connect with password=*****\"",
      "criteria": "rc == 0 and out(\"password=\")",
      "status": "ok",
      "rc": 0,
      "duration": 0.002,
      "started_at": "2026-07-18T10:45:30",
      "finished_at": "2026-07-18T10:45:30",
      "detail": "",
      "host_results": {},
      "host_matrix": false,
      "criteria_breakdown": []
    }
  ]
}
```

`vars.DB_PASS` および `command` フィールドの双方でマスクされていることが分かる。

なお、ログディレクトリ内の生の標準出力キャプチャファイル `step01_stdout.txt` も
確認したところ、内容は次の通りマスクされていた(実行コマンドそのものがマスク後の
文字列で実行されるため、標準出力にも平文の `s3cret-value` は一切現れない)。

```
$ cat <LOGDIR>/secrets_demo_20260718_104530/step01_stdout.txt
```

```
connect with password=*****
```

---

## 7. 切り戻し実行の例

`fail_demo.md` の `# RB-ROLLBACK` セクション(切り戻し例、1ステップ)を `--rollback` で
実行する。

実行場所: `/home/practi/wk_tool`(手順書は `<DEMO_DIR>/fail_demo.md` を絶対パスで指定)

```
$ .venv/bin/runbook run --rollback --yes --operator 仕様採取 --log-dir <LOGDIR> <DEMO_DIR>/fail_demo.md
```

終了コード: 0。生成されたログディレクトリは `<LOGDIR>/fail_demo_rollback_20260718_104548`
(通常実行のディレクトリ名と区別するため `_rollback` が付与される)。

ターミナル全出力:

```
・ 実行前確認
  ├ 手順書: 失敗例デモ(仕様書の実行例採取用) (<DEMO_DIR>/fail_demo.md)
  ├ 切り戻し実行(--rollback): 切り戻しセクションのステップを実行します
  ├ モード: 一括
  ├ 実行対象: 1/1 ステップ
  │   1. 切り戻し例
  ├ 変数:
  │   THRESHOLD = 90
  └ (切り戻し実行)

・ 実行開始: 失敗例デモ(仕様書の実行例採取用) (切り戻し)
  ├ 作業者: 仕様採取 / 確認者: (なし)
  └ ログ保存先: <LOGDIR>/fail_demo_rollback_20260718_104548

・ ステップ 1/1: 切り戻し例
  ├ コマンド:
  │   $ echo "rollback done"
  ├ 正常性基準: rc == 0
  ├ 開始: 2026-07-18 10:45:48
  │   rollback done
  ├ 終了: 2026-07-18 10:45:48
  └ 結果: ✓ Completed (rc=0, 0.003s)

・ 実行結果: 全ステップ正常終了
  └ ログ保存先: <LOGDIR>/fail_demo_rollback_20260718_104548
exit=0
```

実行前確認欄に「切り戻し実行(--rollback)」の専用行が追加され、実行開始の見出しにも
「(切り戻し)」が付く。対象は `# RB-ROLLBACK` 以降の「1. 切り戻し例」ステップのみで、
本編(RB-ROLLBACK より前)のステップは実行されない。

### 7.1 `run.log` 全文

```
[2026-07-18 10:45:48] 手順書「失敗例デモ(仕様書の実行例採取用)」実行開始 (<DEMO_DIR>/fail_demo.md) [切り戻し実行]
[2026-07-18 10:45:48] 作業者: 仕様採取  確認者: (なし)
[2026-07-18 10:45:48] 対象ステップ: [1]
[2026-07-18 10:45:48] --- ステップ 1: 切り戻し例 ---
[2026-07-18 10:45:48] コマンド: echo "rollback done"
[2026-07-18 10:45:48] 終了コード: 0  所要時間: 0.003s
[2026-07-18 10:45:48] 判定: OK
[2026-07-18 10:45:48] 実行終了: completed
```

先頭行に `[切り戻し実行]` の注記が付き、通常実行のログと区別できる。

### 7.2 `result.json` 全文

```json
{
  "procedure": {
    "file": "<DEMO_DIR>/fail_demo.md",
    "title": "失敗例デモ(仕様書の実行例採取用)",
    "mode": "batch",
    "rollback": true,
    "operator": "仕様採取",
    "checker": "",
    "selected_steps": [
      1
    ],
    "vars": {
      "THRESHOLD": "90"
    },
    "secrets": [],
    "share_env": false
  },
  "status": "completed",
  "started_at": "2026-07-18T10:45:48",
  "finished_at": "2026-07-18T10:45:48",
  "steps": [
    {
      "number": 1,
      "title": "切り戻し例",
      "command": "echo \"rollback done\"",
      "criteria": "rc == 0",
      "status": "ok",
      "rc": 0,
      "duration": 0.003,
      "started_at": "2026-07-18T10:45:48",
      "finished_at": "2026-07-18T10:45:48",
      "detail": "",
      "host_results": {},
      "host_matrix": false,
      "criteria_breakdown": []
    }
  ]
}
```

`procedure.rollback` が `true` になっており、通常実行の `result.json`(`false`)と
区別できる。
