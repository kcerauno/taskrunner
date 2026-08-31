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

### RB-LOCALDEF
```yaml
timeout: 30
```

### RB-CMD
```bash
uname -a
```

### RB-EXPECTED
```
rc == 0 and out("{{KEYWORD}}")
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
