# 出力表示デモ(v0.5.1 の可読性改善を一通り確認する手順書)

この手順書は **意図的に途中で失敗します**。目的は正常系の確認ではなく、
`runbook run` の出力表示(特に失敗時)を目で確認することです。

実行方法(SSH 不要。全ホストが `ansible_connection=local` の擬似ホスト):

```
runbook run samples/output_demo.md -y --operator デモ --checker デモ
```

確認できる表示:

| 表示 | 確認できるステップ |
|---|---|
| 終了時刻を `結果` 行にまとめる | 全ステップ |
| ホスト別結果の1行表示(`db01=O web01=O`) | 2・4 |
| 記号の凡例が最初の1回だけ出る | 2 に出て、4 では繰り返さない |
| 出力行の色分け(ホスト区切り・`PLAY`/`TASK`・失敗行) | 2・3・4 |
| 判定内訳に「実際の出力はどうだったか」が付く | 5(失敗するステップ) |
| 失敗時ガイダンス(RB-ONFAIL) | 5 |
| 最終サマリーが失敗ステップ名を示す | 末尾 |
| ステップ別リザルト一覧(完了/失敗/未実行) | 末尾 |
| 最終ホスト別結果マトリックス | 末尾 |

一覧表の他の状態も見たい場合:

- `- 対象外` … `runbook run samples/output_demo.md --only 1,2 -y --operator デモ`
- `→ スキップ` … `runbook run samples/output_demo.md -i --operator デモ` で `s` を入力

```runbook
vars:
  INVENTORY: ./samples/local_test/inventory.ini
  CHECK_LABEL: 出力デモ
```

## 1. bash ステップ(基準を満たして完了する)

### RB-DESCRIPTION
最も単純なステップ。`結果` 行に rc・所要時間・終了時刻がまとまって出ることを確認する。

### RB-CMD
```bash
echo "demo start on $(hostname)"
date '+%Y-%m-%d %H:%M:%S'
```

### RB-EXPECTED
```
rc == 0 and out("demo start")
```

## 2. ansible: 全6ホスト成功(ホスト別結果の1行表示と凡例)

### RB-DESCRIPTION
ホスト別結果が `db01=O db02=O ...` の1行で出る(表を組まない)。
記号の凡例はこのステップにだけ出て、後続では繰り返さない。
出力の `web01 | CHANGED | rc=0 >>` というホスト区切り行が緑になる。

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: all
  host_matrix: true
timeout: 120
```

### RB-CMD
```ansible
echo "{{CHECK_LABEL}}: host={{ inventory_hostname }}"
```

### RB-EXPECTED
```
rc == 0 and out("host=web01") and out("host=db01") and out("host=mon01") and
not out("UNREACHABLE|FAILED")
```

## 3. playbook: PLAY / TASK / PLAY RECAP の色分け

### RB-DESCRIPTION
プレイブック実行では `PLAY [...]` `TASK [...]` `PLAY RECAP` が見出しとして色付きになり、
長い出力の中で区切りが分かる。`failed=0` の RECAP 行は色を付けない
(`failed=1` 以上のときだけ赤くなる)。

### RB-LOCALDEF
```yaml
ansible:
  host_matrix: true
timeout: 120
```

### RB-CMD
```playbook
-i {{INVENTORY}} ./samples/local_test/show_var.yml -e HOGE=DEMO
```

### RB-EXPECTED
```
rc == 0 and out("HOGE=DEMO") and not out("failed=[1-9]|unreachable=[1-9]")
```

## 4. ansible: 一部ホストが失敗(想定内なのでステップは完了する)

### RB-DESCRIPTION
db 系2ホストだけコマンドが失敗する。ホスト別結果に `X` が出て、
出力の `db01 | FAILED | rc=1 >>` が赤くなる。
「一部ホストの失敗を想定内として次に進む」書き方の例でもあるので、
基準式は rc=2(一部失敗)を許容している。凡例はここでは繰り返さない。

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: dbservers
  host_matrix: true
timeout: 120
```

### RB-CMD
```ansible
test -f /nonexistent-path-for-demo
```

### RB-EXPECTED
```
rc == 2 and out("db01 \| FAILED") and out("db02 \| FAILED") and
not out("UNREACHABLE")
```

## 5. 意図的に失敗するステップ(判定内訳と失敗時ガイダンス)

### RB-DESCRIPTION
ここで失敗して実行が中断する。判定内訳の各条件に「実際どうだったか」が付くことを確認する。
`not out("WARN")` は 3 行にマッチしたこと・初出が何行目かまで出るので、
出力を目でスクロールして探す必要がない。

### RB-CMD
```bash
echo "service is active"
echo "WARN: cache miss rate high"
echo "WARN: retry queue growing"
echo "WARN: disk io saturated"
echo "summary: 3 warnings"
```

### RB-EXPECTED
```
rc == 0 and out("active") and out("NOT_IN_OUTPUT") and not out("WARN")
```

### RB-ONFAIL
警告内容を確認し、影響範囲を切り分ける。
`WARN` が想定内であれば基準式の `not out("WARN")` を見直す。
解消しない場合は作業を中止し、チームリーダーへ連絡する。

## 6. 到達しないステップ(一覧で「未実行」になる)

### RB-DESCRIPTION
ステップ5で中断するため、このステップは実行されない。
末尾のリザルト一覧で `- 未実行` と表示され、飛ばされたことが引き算なしで分かる。

### RB-CMD
```bash
echo "this never runs"
```

### RB-EXPECTED
```
rc == 0
```

## 7. 到達しない手動ステップ

### RB-DESCRIPTION
手動ステップも同様に `- 未実行` として一覧に出る。
(RB-CMD がないステップは手動ステップになり、作業者の完了確認を待つ)
