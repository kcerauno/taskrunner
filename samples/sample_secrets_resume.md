# シークレットマスキングと再開実行のサンプル

`secrets:` 宣言(値を表示・ログからマスク)と `--start-from N`(途中からの再開。
share_env の環境変数も復元)の動作確認用手順書。

実行方法(リポジトリ直下 = ~/wk_tool で):

    .venv/bin/runbook run --yes --operator テスト samples/sample_secrets_resume.md
    # 実行後、ターミナル・logs/ 配下のどこにも SuperSecret99 が残っていないことを確認:
    #   grep -r SuperSecret99 logs/ | grep -v shared_env.sh   ← 何も出ない
    # (shared_env.sh のみ実行に必要なため平文。実行前確認にも注意が表示される)

    # ステップ2から再開(直近実行の shared_env.sh から TOKEN を復元):
    .venv/bin/runbook run --start-from 2 --yes --operator テスト samples/sample_secrets_resume.md

    # 値を手順書に書かない運用(--var で実行時に渡す):
    .venv/bin/runbook run --var DB_PASS=別の値 --yes --operator テスト samples/sample_secrets_resume.md

```runbook
vars:
  DB_PASS: SuperSecret99
  DB_HOST: db01
secrets: [DB_PASS]
share_env: true
```

## 1. 認証トークンの取得(シークレットを使う)

### RB-DESCRIPTION
シークレット変数 DB_PASS を使ってトークンを取得する想定。
コマンド表示・出力・ログのすべてで DB_PASS の値は ***** にマスクされる。
判定は生の出力に対して行われるため、out("{{DB_PASS}}") も正しく機能する。

### RB-CMD
```bash
echo "auth {{DB_HOST}} password={{DB_PASS}}"
export TOKEN="tok-$(date +%s)"
echo "TOKEN=$TOKEN を取得した"
```

### RB-EXPECTED
```
rc == 0 and out("password={{DB_PASS}}") and out("TOKEN=tok-")
```

## 2. トークンの使用(--start-from の再開対象)

### RB-DESCRIPTION
前ステップで export した TOKEN を使う。--start-from 2 で再開したときは
直近実行の shared_env.sh から TOKEN が復元されるため、このステップ単体でも動く。

### RB-CMD
```bash
echo "using $TOKEN for {{DB_HOST}}"
```

### RB-EXPECTED
```
rc == 0 and out("using tok-")
```
