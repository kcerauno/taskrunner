# runbook チートシート (v0.5.0)

## コマンド

```bash
runbook run   手順書.md                # 一括実行(失敗で即中断)
runbook run   -i 手順書.md             # 逐次実行(各ステップ前に Enter/s/q)
runbook check 手順書.md                # 静的検証のみ(実行しない)
runbook list  手順書.md                # ステップ一覧
runbook renumber 手順書.md             # ## 見出しに連番を付与(ファイル書き換え)
```

### 全コマンド共通

| オプション | 意味 |
|---|---|
| `--var KEY=VALUE` | 変数の指定/上書き(複数可) |

### run

| オプション | 意味 |
|---|---|
| `--only 1,3-5` | ステップ指定実行 |
| `--from N` / `--to N` | 範囲指定(`--only` と積集合) |
| `--start-from N` | N から最後まで**再開**(直近実行の環境変数を復元。なければエラー) |
| `-y`, `--yes` | 実行前確認ゲートを省略(非対話実行用) |
| `--operator NAME` / `--checker NAME` | 作業者(必須)/確認者(任意) |
| `--log-dir DIR` | ログ保存先(既定 `./logs`) |

### 全文を見る / 事前に確かめる

```bash
runbook list --detail 手順書.md        # 変数展開後の実行コマンドを全文表示
runbook check --preview 手順書.md      # 検証 + 実行コマンド全文
```

### 終了コード

`0` 成功 / `1` ステップ失敗による中断・check の NG / `2` パース・引数エラー / `130` 作業者による中止

---

## 手順書の骨格

````markdown
# タイトル

```runbook
title: 〇〇作業手順          # 任意
vars:                        # 任意: 変数(--var で上書き可)
  TARGET: web01
ansible:                     # 任意: ansible の共通既定
  target: web
  extra_args: "--forks 10"
  host_matrix: true
secrets: [DB_PASS]           # 任意: 値をマスクする変数
```

## 1. ステップ名

### RB-DESCRIPTION
作業説明(フェンスで囲まない)

### RB-LOCALDEF
```yaml
timeout: 300
cwd: /var/tmp
ansible:
  inventory: hosts.ini
  target: db01
```

### RB-CMD
```bash
echo hello
```

### RB-EXPECTED
```
rc == 0 and out("hello")
```

### RB-ONFAIL
失敗時に表示するガイダンス(フェンスで囲まない)
````

- `## ` 見出し 1 つ = 1 ステップ。**記載順 = 実行順 = ステップ番号**
- セクションは `RB-DESCRIPTION` / `RB-LOCALDEF` / `RB-CMD` / `RB-EXPECTED` / `RB-ONFAIL` の5種のみ
  (記載順は自由。上の順=説明 → 実行先 → コマンド → 判定 → 失敗時、が推奨)
- `RB-CMD` がないステップ = **手動ステップ**(`RB-DESCRIPTION` 必須。`y` 入力を待つ)
- 共通設定は最初の `## ` より**前**。frontmatter には書けない(エラー)

---

## 正常性基準 (RB-EXPECTED)

省略時は `rc == 0`。

| 要素 | 意味 |
|---|---|
| `rc` / `exit_code` | 終了コード |
| `stdout` / `stderr` | 出力全文(`"OK" in stdout` の形で使える) |
| `out("正規表現")` | 標準出力にマッチ |
| `err("正規表現")` | 標準エラーにマッチ |
| `match("正規表現")` | 標準出力 + 標準エラーにマッチ |

演算: `and` `or` `not` `==` `!=` `<` `<=` `>` `>=` `in` `not in` `( )`

```
rc == 0 and out("active \(running\)") and not out("ERROR|WARN")
(rc == 0 or rc == 2) and "failed=0" in stdout
```

文字列内のバックスラッシュ(`\|` `\d` `\(`)はそのまま書ける。

---

## ランナー(RB-CMD のフェンス言語で決まる)

| 言語 | ランナー | 組み立て |
|---|---|---|
| `bash`(や無指定) | shell | `/bin/bash -c` にそのまま渡す |
| `ansible` | ad-hoc | `ansible <target> -i <inv> -m shell -a '<中身>'` |
| `playbook` / `ansible-playbook` | playbook | 各行が `ansible-playbook` の引数列 |
| (RB-CMD なし) | manual | 作業者の完了確認 |

**インベントリは共通設定に置けない**(意図しない環境での実行を防ぐため)。
行内か `RB-LOCALDEF` で毎回明示する。未指定はエラー。

### ansible ad-hoc: 2つの書き方

````markdown
```ansible
uptime                                    ← RB-LOCALDEF で inventory/target を指定
```

```ansible
ansible web -i hosts.ini -e HOGE=X        ← 1行目に直接書く(設定側より優先)
uptime                                     ← 2行目以降がリモートコマンド
```
````

組み立て: `ansible <target> -i <inv> [-e '<JSON>'] [<extra_args>] -m shell -a '<中身>'`

- **フェンス内のリモートコマンドに `{{VAR}}` 置換はしない**。変数は `-e JSON` で
  ansible に渡り、jinja2 が解決する(`{{ inventory_hostname }}` と共存できる)
- 行内指定の1行目だけは置換される

### playbook: 1行 = 1回の ansible-playbook

フェンスの**各行がそのまま `ansible-playbook` の引数列**になる。
プレイブックのパスに続けてオプションを直接書ける。

````markdown
```playbook
# 空行と # 始まりの行は無視される
-i inventories/web.ini deploy.yml -e HOGE=PIYO --check
-i inventories/db.ini migrate.yml
```
````

組み立て(行ごと): `ansible-playbook [-i <inv>] [-l <target>] [-e '<JSON>'] [<extra_args>] <行の内容>`

| 書き方 | 生成されるコマンド |
|---|---|
| 行内に `-i` を書く | 設定側の inventory は**付けない**(ansible は複数 `-i` を結合するため二重指定は事故のもと) |
| `RB-LOCALDEF` で `inventory` + `target` | `-i <inv> -l <target>` が付く(target は `-l`= limit) |
| 複数行 | ` && ` で連結。**前の行が失敗したら以降は実行されない**(fail-fast) |

- 変数置換は**各行に適用される**(ad-hoc と違い、行はコントローラ側の値のため)
- 自動付与の `-e JSON` は前に置かれるので、**行内に書いた `-e` が優先**される
  (実行時だけ値を変えたいときに使う)
- 有効な行が 0 ならエラー

ホスト別結果は `PLAY RECAP` から抽出される
(`failed>0` → `X` / `unreachable>0` → `!` / それ以外 → `O`)。

---

## つまずきやすい点

| 症状 | 原因 |
|---|---|
| RB-ONFAIL が失敗時に出ない | **コードフェンスで囲んでいる**。自由記述セクション(`RB-ONFAIL` / `RB-DESCRIPTION`)はフェンス**外**に書く |
| 共通設定の `timeout` が効かない | `timeout` は `RB-LOCALDEF` 専用。**既定はタイムアウトなし(無制限に待つ)** |
| 共通設定に `inventory` を書くとエラー | 意図しない環境での実行を防ぐため、インベントリは**毎回明示**(行内 or RB-LOCALDEF) |
| playbook で `-e` が効かない | 自動付与の `-e JSON` は前に置かれる。上書きしたい値は**行内の `-e`** に書く(後勝ち) |
| playbook で 2行目以降が走らない | 行は ` && ` 連結。**前の行が失敗した**(fail-fast の仕様) |
| ansible フェンスの `{{VAR}}` が展開されない | ad-hoc の**リモートコマンドは置換対象外**。値は `-e JSON` で渡り jinja2 が解決する(仕様) |
| `# RB-ROLLBACK` でエラー | 切り戻し機能は v0.5.0 で廃止。切り戻しは**別ファイルの手順書**にする |
| 設定を書いたのに無視される | 共通設定で認識するのは `title` / `vars` / `ansible` / `secrets` のみ |

いずれも `runbook check` が警告・エラーで知らせる。**実行前に必ず `check` を通す。**

---

## 実行時の挙動

- ステップが**失敗したら常に即中断**。自動リトライ・自動スキップはしない
- 環境変数の引き継ぎは**常時有効**。`export` した値は次ステップに渡る
  (`unset` も引き継がれ、復活しない)
- 手動ステップは `y` の明示入力が必要(Enter 空打ちでは通らない)

### 失敗したとき

```
├ 判定内訳:
│   [OK] rc == 0            → 実際 rc=0
│   [NG] not out("WARN")    → stdout の3行がマッチ (初出 L2: WARN: ...)
└ 結果: ✘ Failed (rc=0, 0.005s, 終了 22:42:11)

・ 実行結果: 実行中断 — ステップ 5「...」で失敗
  5   ...        ✘ 失敗      0   0.005s   ← 中断
  6   ...        - 未実行    -        -
```

原因を解消してから `runbook run --start-from 5 手順書.md` で再開する
(直近実行の環境変数も復元される)。

---

## ログ成果物 `logs/<手順書名>_<日時>/`

| ファイル | 内容 |
|---|---|
| `run.log` | 人間可読の実行経過(作業者・判定・RB-ONFAIL) |
| `result.json` | 機械可読サマリ(rc・所要時間・判定内訳) |
| `stepNN_stdout.txt` / `stepNN_stderr.txt` | 各ステップの生出力 |
| `env_overlay.sh` | 環境変数の差分(`--start-from` の復元元) |

- `secrets` 宣言した値は表示・ログ・生出力すべてで `*****` になる
- **例外**: `env_overlay.sh` は実行に必要なため平文。ログの保管ルールに注意
- 集計: `tools/logs_report.py {evidence|runs|failures|timing}`
  (`evidence` は Excel 貼り付け用の TSV を出力)
