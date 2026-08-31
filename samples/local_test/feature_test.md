# 機能テスト手順(共通設定なし・全ステップ個別定義スタイル)

手順書の共通設定(変数など)は frontmatter の代わりに、下記の runbook フェンスでも
定義できる。フェンスは標準の Markdown 要素なのでどのプレビューでも表示される。

```runbook
vars:
  CHECK_LABEL: 機能テスト
  HOGE: FUGA
```

この手順書は共通の ansible 設定(inventory / target)を持たない。
各ステップが行内指定またはステップ設定でインベントリ・ターゲットを個別に定義する。
ansible を使わない手順書では ansible の設定は一切不要。

実行方法(リポジトリ直下 = ~/wk_tool で):

    .venv/bin/runbook check samples/local_test/feature_test.md   # 事前検証
    .venv/bin/runbook list  samples/local_test/feature_test.md   # ステップ一覧
    .venv/bin/runbook run   samples/local_test/feature_test.md   # 一括実行
    .venv/bin/runbook run -i samples/local_test/feature_test.md  # 逐次実行
    .venv/bin/runbook run --only 5 samples/local_test/feature_test.md  # ステップ指定
    .venv/bin/runbook run --var HOGE=OVERRIDE samples/local_test/feature_test.md  # 変数上書き

実行開始前にサマリー確認(y 入力)と作業者名の入力を求められる。
繰り返しテストするときは次のように省略できる:

    .venv/bin/runbook run --yes --operator テスト samples/local_test/feature_test.md

## 1. ad-hoc: 行内指定で全6ホストの疎通確認

### RB-DESCRIPTION
フェンス1行目の「ansible ターゲット -i インベントリ」が起動指定として使われる。
期待結果: 6ホスト全てが CHANGED、ホスト別結果マトリックスに O が6つ並ぶ。

### RB-LOCALDEF
```yaml
ansible:
  host_matrix: true
```

### RB-CMD
```ansible
ansible all -i samples/local_test/inventory.ini
echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"
```

### RB-EXPECTED
```
rc == 0 and
out("機能テスト: host=web01") and out("機能テスト: host=web02") and
out("機能テスト: host=web03") and out("機能テスト: host=db01") and
out("機能テスト: host=db02") and out("機能テスト: host=mon01") and
not out("UNREACHABLE|FAILED")
```

## 2. ad-hoc: RB-LOCALDEF で定義するスタイル

### RB-DESCRIPTION
行内指定の代わりに、ステップの RB-LOCALDEF で inventory / target を定義する書き方。
期待結果: web系3ホストのみで実行される。

### RB-LOCALDEF
```yaml
ansible:
  inventory: samples/local_test/inventory_web.ini
  target: web
  host_matrix: true
```

### RB-CMD
```ansible
uptime
```

### RB-EXPECTED
```
rc == 0 and out("web01") and out("web02") and out("web03") and
not out("db01|db02|mon01") and not out("UNREACHABLE|FAILED")
```

## 3. playbook: 行内 -i と -e(実行時上書き)

### RB-DESCRIPTION
プレイブック行に -i(インベントリ)と -e(実行時に変えたい値)を直接書く。
手順書変数 HOGE=FUGA は自動の -e JSON で渡るが、行内の -e HOGE=PIYO が優先される。
期待結果: web系3ホストで実行され、出力が HOGE=PIYO になる(FUGA ではない)。

### RB-LOCALDEF
```yaml
ansible:
  host_matrix: true
```

### RB-CMD
```playbook
-i samples/local_test/inventory_web.ini samples/local_test/show_var.yml -e HOGE=PIYO
```

### RB-EXPECTED
```
rc == 0 and out("HOGE=PIYO") and not out("HOGE=FUGA") and
not out("failed=[1-9]|unreachable=[1-9]")
```

## 4. playbook: 行ごとのインベントリ切替

### RB-DESCRIPTION
処理系統ごとにインベントリを分ける運用の確認。行ごとに -i を書き分ける。
2行は && 連結で順に実行され、1行目が失敗したら2行目は実行されない。
期待結果: 1行目は web系3ホスト(HOGE=FUGA)、2行目は db系2ホスト(HOGE=DB_RUN)で実行され、
マトリックスには両系統のホストがマージされて表示される。

### RB-LOCALDEF
```yaml
ansible:
  host_matrix: true
```

### RB-CMD
```playbook
-i samples/local_test/inventory_web.ini samples/local_test/show_var.yml
-i samples/local_test/inventory_db.ini samples/local_test/show_var.yml -e HOGE=DB_RUN
```

### RB-EXPECTED
```
rc == 0 and
out("HOGE=FUGA \(host=web01\)") and out("HOGE=FUGA \(host=web03\)") and
out("HOGE=DB_RUN \(host=db01\)") and out("HOGE=DB_RUN \(host=db02\)") and
not out("failed=[1-9]|unreachable=[1-9]")
```

## 5. ad-hoc: 行内指定 + 行内 -e の優先確認

### RB-DESCRIPTION
起動指定行に -e HOGE=ADHOC を書くと、自動付与の手順書変数(HOGE=FUGA)より優先される。
2行目以降のリモートコマンドでは jinja2({{ HOGE }} や {{ inventory_hostname }})が使える。
期待結果: db系2ホストのみで実行され、出力が HOGE=ADHOC になる。

### RB-LOCALDEF
```yaml
ansible:
  host_matrix: true
```

### RB-CMD
```ansible
ansible db -i samples/local_test/inventory_db.ini -e HOGE=ADHOC
echo "HOGE={{ HOGE }} on {{ inventory_hostname }}"
```

### RB-EXPECTED
```
rc == 0 and
out("HOGE=ADHOC on db01") and out("HOGE=ADHOC on db02") and
not out("HOGE=FUGA") and not out("web01|web02|web03|mon01") and
not out("UNREACHABLE|FAILED")
```

## 6. bash: ローカルステップとの混在確認

### RB-DESCRIPTION
同じ手順書内に bash ステップも混在できることの確認。ansible の設定は一切不要。
期待結果: OK。このステップは ansible ではないためホスト別結果は表示されない。

### RB-CMD
```bash
echo "local step on $(hostname)"
uname -a
```

### RB-EXPECTED
```
rc == 0 and "local step on" in stdout and out("Linux")
```
