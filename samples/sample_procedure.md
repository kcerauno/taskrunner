# サンプル手順書(動作確認用)

```runbook
vars:
  TARGET_DIR: /tmp
  KEYWORD: Linux
```

## 事前確認: ディスク使用状況

### RB-DESCRIPTION
対象ディレクトリのあるファイルシステムの使用状況を確認する。
出力にファイルシステム情報が含まれ、使用率100%でないことを確認する。

### RB-CMD
```bash
df -h {{TARGET_DIR}}
```

### RB-EXPECTED
```
rc == 0 and out("Filesystem|ファイルシス") and not out(" 100%")
```

## OS情報の取得

### RB-DESCRIPTION
カーネル情報を取得し、期待するOS種別であることを確認する。

### RB-CMD
```bash
uname -a
```

### RB-EXPECTED
```
rc == 0 and out("{{KEYWORD}}")
```

### RB-LOCALDEF
```yaml
timeout: 30
```

## 作業ファイルの作成と確認

### RB-DESCRIPTION
作業用ファイルを作成し、書き込んだ内容が読み出せることを確認する。
コードフェンスが複数ある場合は連結して実行される。

### RB-CMD
```bash
echo "runbook test $(date +%Y%m%d)" > {{TARGET_DIR}}/runbook_sample.txt
```
```bash
cat {{TARGET_DIR}}/runbook_sample.txt
rm {{TARGET_DIR}}/runbook_sample.txt
```

### RB-EXPECTED
```
rc == 0 and "runbook test" in stdout and not err(".")
```

### RB-ONFAIL
{{TARGET_DIR}} の書き込み権限とディスク残量を確認する。
解消しない場合は作業を中止し、チームリーダーへ連絡する。

## 作業結果の目視確認(手動ステップ)

### RB-DESCRIPTION
RB-CMD のないステップは手動ステップになる。
画面やダッシュボードなどコマンド化できない確認をここに書く。
実行時はこの説明が表示され、作業者が y を入力するまで次へ進まない
(確認時刻と作業者名がログに記録される)。

# RB-ROLLBACK

## 作業ファイルの削除(切り戻し)

### RB-DESCRIPTION
この見出し(# RB-ROLLBACK)以降は切り戻しセクション。通常実行では走らず、
`runbook run --rollback samples/sample_procedure.md` でのみ実行される。
本編が中断したときは、実行方法が自動で案内される(自動では実行されない)。

### RB-CMD
```bash
rm -f {{TARGET_DIR}}/runbook_sample.txt
ls {{TARGET_DIR}}/runbook_sample.txt 2>&1 || echo "removed"
```

### RB-EXPECTED
```
out("removed")
```
