# runbook — VSCode 入力支援拡張

runbook 形式の Markdown 手順書を書くための VSCode 拡張。ビルド不要(素の JavaScript)。

## 機能

| 機能 | 内容 |
|---|---|
| スニペット | `rbtemplate`(手順書全体) / `rbstep` / `rbmanual` / `rbcmd` / `rbansible` / `rbansibleinline` / `rbplaybook` / `rbexpected` / `rbexpected2` / `rbdesc` / `rbonfail` / `rblocaldef` / `rbconfig` / `rbconfigfull` |
| 診断 | 保存時に `runbook check --json` を実行し、書式エラー・基準式エラーを赤波線、警告(見出し番号のずれ、空の RB-ONFAIL、共通設定の未知キー、インベントリ/playbook/cwd の不在)を黄波線で表示 |
| アウトライン | `## 見出し` をステップ、`### RB-*` をその子として表示(手動ステップは「手動ステップ」と注記) |
| 色分け | `### RB-*` セクション見出しと `{{VAR}}` を強調。さらに Markdown が知らない独自フェンス言語の中身に文法を埋め込む(```` ```runbook ```` → YAML、```` ```ansible ```` / ```` ```playbook ```` / ```` ```ansible-playbook ```` → shell) |
| コマンド | コマンドパレット(または右クリック)から `check` / `check --preview` / `list --detail` / `renumber` / `run -i` を実行 |

対象は「`### RB-` または ```` ```runbook ```` を含む Markdown」だけで、普通の Markdown には
診断もアウトラインも出さない。

## インストール

```bash
ln -s ~/wk_tool/vscode-extension ~/.vscode/extensions/runbook-md
# VSCode を再起動(またはコマンドパレット → Developer: Reload Window)
```

`.vsix` にして配布する場合は `npx @vscode/vsce package`(Node.js が必要)。

## スニペットの使い方

手順書の `.md` を開き、空行にプレフィックスを打って `Ctrl+Space` → `Enter`(または `Tab`)。
展開後は `Tab` で入力欄を順に移動し、`Esc` で抜ける。

VSCode は Markdown では既定で補完ポップアップを出さないため、`Ctrl+Space` を押すか、
`.vscode/settings.json` に次を入れて自動表示にする(このリポジトリでは設定済み):

```json
"[markdown]": {
  "editor.quickSuggestions": { "other": true, "comments": false, "strings": false },
  "editor.snippetSuggestions": "top",
  "editor.wordBasedSuggestions": "off"
}
```

| プレフィックス | 展開されるもの |
|---|---|
| `rbtemplate` | 手順書ファイル全体(タイトル + 共通設定 + 最初のステップ) |
| `rbstep` | コマンドステップ(RB-DESCRIPTION / RB-CMD / RB-EXPECTED。設定が要るときは `rblocaldef` を RB-CMD の前に挿入) |
| `rbmanual` | 手動ステップ(RB-CMD なし。RB-DESCRIPTION のみ) |
| `rbconfig` / `rbconfigfull` | ```` ```runbook ```` 共通設定(後者は title / secrets 付き) |
| `rbcmd` / `rbplaybook` | RB-CMD(bash / playbook) |
| `rbansible` | ansible ad-hoc(RB-LOCALDEF に inventory/target + RB-CMD にリモートコマンド) |
| `rbansibleinline` | ansible ad-hoc の行内指定スタイル(フェンス1行目に `ansible <target> -i <inv>`) |
| `rbexpected` / `rbexpected2` | RB-EXPECTED(後者は `rc == 0 and out(...) and not out(...)`) |
| `rbdesc` / `rbonfail` / `rblocaldef` | RB-DESCRIPTION / RB-ONFAIL / RB-LOCALDEF |

`{{VAR}}` を書いた後は保存すれば、未定義変数は赤波線で分かる。

## 設定

| 設定 | 既定値 | 説明 |
|---|---|---|
| `runbook.executablePath` | `runbook` | runbook 実行ファイル。venv 運用なら `${workspaceFolder}/.venv/bin/runbook` |
| `runbook.checkOnSave` | `true` | 保存時に検証する |
| `runbook.diagnosticsEnabled` | `true` | 診断表示のオン/オフ |

この wk_tool リポジトリで使う場合の `.vscode/settings.json`:

```json
{ "runbook.executablePath": "${workspaceFolder}/.venv/bin/runbook" }
```

## 仕組み

診断は CLI の `runbook check --json` を呼ぶだけで、書式の解釈をエディタ側に二重実装しない
(CLI と診断が食い違わない)。出力は次の形:

```json
{"ok": false, "path": "手順書.md", "steps": 4,
 "diagnostics": [{"severity": "warning", "line": 31, "step": 1, "message": "..."}]}
```

`line` はステップ見出しの行番号。メッセージが特定セクションを指す場合(例: RB-ONFAIL が空)は、
拡張側でそのセクション見出しの行へ波線を寄せる。パースエラーは行を特定できないため `line: 0`
(ファイル先頭)に出る。

## 既知の制限

- `{{VAR}}` の強調は ```` ```bash ```` などのコードフェンスの中には効かない(フェンス内は
  埋め込み文法が優先されるため)。フェンス外の本文では効く。
- 診断は保存時・ファイルオープン時のみ更新する(未保存の編集中には走らない)。
- `{{VAR}}` の補完・定義ジャンプ、RB-EXPECTED の式補完は未実装。
