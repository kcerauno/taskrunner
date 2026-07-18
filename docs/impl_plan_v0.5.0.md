# v0.5.0 実装設計書(案B: ストラングラー方式)

対象仕様: `/home/practi/wk_refactoring_runbook/docs/external_spec_v2/`(D1〜D7)。
本書は実装のためのモジュール設計・インターフェース・移行手順を定める。
方針: parser.py / criteria.py は既存構造を維持して小改修、実行・ログ・表示系は
新モジュール(envstate / artifacts / render)へ再設計する。

## モジュール構成(after)

```
runbook/
  __init__.py      __version__ = "0.5.0"
  __main__.py      (変更なし)
  cli.py           argparse + フロー制御に痩せさせる(表示部品は render へ)
  parser.py        小改修(D1: RB-ROLLBACK→エラー / D6: playbook 行内指定 / share_env 廃止)
  criteria.py      変更なし
  executor.py      改修(D3: 環境注入+スナップショット捕捉 / D4: シグナル転送)
  envstate.py      新規(D3: baseline + 差分オーバーレイの純ロジック)
  artifacts.py     新規(D5/D7: 証跡書き込み層。logger.py を置換・削除)
  render.py        新規(D2: 共通表示部品。console / 一覧表 / ステップ詳細ほか)
```

---

## 1. parser.py(Step 1)

### D1: rollback 削除
- `_ROLLBACK_PATTERN` にマッチする行(フェンス外)を検出したら即
  `ParseError(f"{path}: 切り戻し機能(# RB-ROLLBACK)は v0.5.0 で削除されました。"
  f"切り戻し手順は別ファイルの手順書として作成してください")`。
- `Procedure.rollback_steps` フィールド、`in_rollback` 分岐、rollback 関連の
  エラーチェック(重複・後続ステップなし)をすべて削除。
- モジュール docstring の rollback 記述を削除。

### share_env 廃止
- `Procedure.share_env` フィールド、`share_env` の型検証を削除。
- `_CONFIG_KEYS`(frontmatter 拒否リスト)を `{"vars", "ansible", "secrets"}` に。
- ```runbook フェンス内の `share_env` キーは他の未知キーと同様**黙って無視**
  (仕様 02 章 §4 の現行方針に合わせる)。
- docstring 更新。

### D6: playbook 行内指定スタイル
`_resolve_playbook_command` の行ループを次の 2 分岐にする(行単位判定・混在可):

- 行が `^ansible-playbook(\s|$)` にマッチ → **行内指定**:
  - `ansible-playbook` に続く残り部分(strip)が空なら
    `ParseError(f"{ctx}: 行内指定(ansible-playbook ...)の後に引数がありません: {line!r}")`。
  - 組み立て: `ansible-playbook [-e '<JSON>'] <残り> [<extra_args>]`。
    設定側 inventory / target(-i / -l)は**付与しない**。inventory 必須チェックもしない
    (ansible ad-hoc の行内指定 §7.3 と同じ扱い)。
  - `used_inventories += _extract_inventory_values(残り)`(サマリー表示用)。
- それ以外 → 従来どおりの設定指定スタイル(現行実装のまま)。

変数置換は現行どおり parse_file 側で行全体に適用済み(変更不要)。
docstring に両スタイルと対称性(ansible §7.3)を記載。

### tests/test_parser.py
- rollback 関連テスト(パース成功系)→「RB-ROLLBACK があるとエラー」のテストに置換。
  エラーメッセージに「v0.5.0 で削除」「別ファイル」が含まれることを確認。
- share_env 関連テスト → 削除。代わりに「```runbook フェンスに share_env を書いても
  無視され Procedure に影響しない」テストと「frontmatter の share_env はエラーに
  **ならない**(拒否リストから外れた)」テストを追加。
  frontmatter 拒否が vars/ansible/secrets で引き続き働くテストは維持。
- playbook 行内指定の新テスト:
  1) `ansible-playbook -i inv.ini site.yml` 行 → 組み立てが
     `ansible-playbook -e '<JSON>' -i inv.ini site.yml` 形式(設定側 -i/-l なし)。
  2) 残り部分が空(`ansible-playbook` のみの行)→ ParseError。
  3) 設定指定スタイル行との混在(2 行)→ それぞれのスタイルで組み立ち && 連結。
  4) 行内指定行では設定側 target(-l)が付与されないこと。
  5) 行内指定の inventories がサマリー用に抽出されること。

---

## 2. envstate.py(Step 2・新規)

環境変数の差分オーバーレイの**純ロジック**。I/O なし(文字列の生成・解析のみ)。

```python
# 差分計算から除外する変数(bash / OS が毎回書き換えるノイズ。
# これらをオーバーレイに載せると cwd 指定等と矛盾するため除外する)
EXCLUDED_VARS = {"SHLVL", "PWD", "OLDPWD", "_"}

@dataclass
class EnvOverlay:
    sets: dict[str, str]      # export する KEY: VALUE
    unsets: set[str]          # unset する KEY(tombstone)

    def to_script(self) -> str:
        # 先頭にコメント行 "# runbook env overlay (auto-generated)"
        # export 行(キーのソート順、shlex.quote で値をクォート)
        # unset 行(キーのソート順)
        # 末尾改行 1 つ。sets/unsets が空でもコメント行のみのスクリプトを返す

    @classmethod
    def from_script(cls, text: str) -> "EnvOverlay":
        # 自前生成フォーマットの逆パース。
        # shlex.split(text, comments=True) で全体をトークン化し、
        # "export" → 次トークンを KEY=VALUE(最初の = で分割)、
        # "unset" → 次トークンを KEY として読む。
        # 値に改行を含む場合も shlex のクォート処理で正しく往復する。
        # 想定外トークンは ValueError("env_overlay.sh の形式が不正です: ...")

    def apply(self, base: dict[str, str]) -> dict[str, str]:
        # base のコピーに sets を上書きし、unsets のキーを取り除いて返す


def diff_env(baseline: dict[str, str], snapshot: dict[str, str]) -> EnvOverlay:
    # sets   = {k: v for snapshot にあり、baseline にない or 値が異なる} - EXCLUDED_VARS
    # unsets = {k for baseline にあり snapshot にない} - EXCLUDED_VARS


class EnvManager:
    """baseline(実行開始時の親環境)+ 現在のオーバーレイを保持する"""
    def __init__(self, baseline: dict[str, str] | None = None):
        # baseline=None なら dict(os.environ) を取得して固定
    def child_env(self) -> dict[str, str]:
        # overlay.apply(baseline)
    def update_from_snapshot(self, snapshot: dict[str, str]) -> None:
        # self.overlay = diff_env(self.baseline, snapshot)
    def load_overlay_script(self, text: str) -> None:
        # self.overlay = EnvOverlay.from_script(text)
    def overlay_script(self) -> str:
        # self.overlay.to_script()
```

### tests/test_envstate.py(新規)
- diff: 追加 / 値変更 / 削除(tombstone)/ 変更なし / EXCLUDED_VARS 除外。
- to_script ↔ from_script の往復(通常値・空文字・シングルクォートや改行・
  `$` や日本語を含む値)。
- apply: sets 上書き + unsets 除去。baseline 由来変数の unset が消えること(tombstone)。
- EnvManager: update_from_snapshot 後の child_env が期待どおり。

---

## 3. artifacts.py(Step 2・新規。logger.py を置換)

証跡書き込み層。既存 logger.py の `RunLogger` を発展させた `RunArtifacts` を提供し、
**logger.py は削除**する。既存の良い部分(mkdir/EEXIST ループ、run.log の逐次
flush、_mask_deep)はそのまま移植する。

```python
def atomic_write_text(path: Path, text: str) -> None:
    # path と同一ディレクトリに tempfile.NamedTemporaryFile(delete=False) で書き、
    # flush + os.replace(tmp, path)。D7.2(rename の原子性は同一 FS 内のみ有効)。
    # renumber からも使う公開ヘルパー。

class StepFiles:
    """1 ステップ分の stepNN_stdout.txt / stepNN_stderr.txt への逐次書き込み"""
    # open 時に両ファイルを作成("w")。
    # write(line: str, is_stderr: bool): mask 適用済みの行(改行付き)を書いて即 flush
    # close(): クローズ(改行なしの最終部分もそのまま書かれている状態で終わる)

class RunArtifacts:
    def __init__(self, procedure_name, base_dir="logs", mask=None):
        # 現 RunLogger.__init__ と同一(mkdir/EEXIST ループ維持)+ run.log open
    def log(self, text=""): ...                    # 現行のまま(逐次 flush)
    def open_step_files(self, number: int) -> StepFiles
    def add_record(self, rec: StepRecord) -> None:
        # records に追加し、save_result("running") を呼ぶ(ステップ終了ごとの
        # アトミック更新。stepNN ファイルの書き込みはしない — StepFiles が担当済み)
    def save_result(self, status: str) -> None:
        # 現 finalize の result dict 生成 + _mask_deep + atomic_write_text
        # status は "running" / "completed" / "aborted"
    def write_env_overlay(self, script: str) -> None:
        # atomic_write_text(self.dir / "env_overlay.sh", script)。マスクしない(仕様 05 §5)
    def finalize(self, status: str) -> Path:
        # save_result(status) → log(f"実行終了: {status}") → run.log close → dir を返す
```

注意:
- StepRecord は executor.py に置いたまま(移動しない。churn 最小化)。
- rec.stdout / rec.stderr フィールドは全量捕捉(判定用)として維持するが、
  ファイル書き込みは StepFiles の逐次書き込みに一本化する。
- result dict のキー構成は cli 側 meta の変更(rollback / share_env 削除、
  resumed_env_from 追加)に従う。artifacts 自体は meta を透過するだけ。

### tests/test_artifacts.py(新規)
- atomic_write_text: 書き込み後の内容一致。一時ファイルが残らないこと。
- mkdir 衝突: 同名 dir を先に作っておくと _2 になること(現 logger テスト相当)。
- save_result("running") 後に result.json が整形式 JSON で status=="running"、
  finalize 後に最終 status になること。
- StepFiles: 逐次 write 後(close 前)にファイル内容が読めること(flush 確認)。
- mask が run.log / result.json / StepFiles に適用されること。

---

## 4. executor.py(Step 3)

### D3: 環境注入とスナップショット捕捉
- `_wrap_share_env` と `env_file` 引数を削除。
- 新シグネチャ:
  `run_command(command, timeout=None, cwd=None, on_line=None, env=None, capture_env=False, grace=10.0) -> ExecResult`
- `env`: Popen の env= にそのまま渡す(None なら親環境継承)。
- `capture_env=True` のとき:
  - `r, w = os.pipe()` を作り、コマンドを次のラッパーで包む:
    ```
    <command>
    __runbook_rc=$?
    env -0 >&<w> 2>/dev/null
    exit $__runbook_rc
    ```
    (`<w>` は実際の fd 番号。`pass_fds=(w,)` で子に同番号のまま渡る)
  - Popen 直後に親側で `os.close(w)`(EOF 検知のため必須)。
  - 専用スレッドで r からバイト列を EOF まで読み(パイプバッファ詰まり防止)、
    `errors="replace"` でデコード。
  - パース: 出力が空、または**末尾が `\0` で終わっていない**(強制終了による
    切断)場合は `env_snapshot = None`。それ以外は `\0` 区切りの各要素を
    最初の `=` で分割して dict にする(`=` を含まない要素は捨てる)。
  - `ExecResult.env_snapshot: dict[str, str] | None = None` を追加。
  - timed_out または interrupted のときは snapshot を None にする(不完全な
    可能性があるため。呼び出し側は None なら前回のオーバーレイを維持 = 仕様
    「途中 exit 時は直前のスナップショット」と同じ扱い)。

### D4: シグナル転送
- `ExecResult.interrupted: int | None = None` を追加(受信シグナル番号)。
- run_command 内で子プロセス起動後、SIGINT / SIGTERM / SIGHUP のハンドラを
  `signal.signal` で一時差し替える(呼び出しは main thread 前提):
  ```python
  def _handler(signum, frame):
      received に signum を記録(初回のみ)
      os.killpg(pgid, signum)(ProcessLookupError は無視)
      threading.Timer(grace, killpg SIGKILL) を起動(初回のみ)
  ```
- finally で必ず元のハンドラに戻し、Timer を cancel する。
- 受信していれば `interrupted=signum` を設定して返す(rc は子の終了コード
  そのまま。通常 -signum)。

### tests/test_executor.py 追加
- env= 指定でコマンドが `printenv KEY` で値を見えること。
- capture_env: `export FOO=bar` 実行後 snapshot に FOO が入ること。
  `exit 3` を含むコマンドでも rc=3 が保たれ snapshot は None(途中 exit)。
  ※ 途中 exit の検証: `export FOO=bar; exit 3` は wrapper 末尾まで到達しない
  ため snapshot なし・rc=3。
- シグナル: `sleep 5` 実行中に threading.Timer(0.3) で
  `os.kill(os.getpid(), SIGTERM)` → interrupted==SIGTERM、所要 < 3s、
  ハンドラが復元されていること。

---

## 5. render.py(Step 3・新規)

cli.py から表示部品を移設する(ロジック変更は show_step_header の preview 対応のみ)。

- 移設対象: `console`(Console インスタンス)、`MASK` 定数、`print_tree_item`、
  `show_step_header`、`step_table`(現 `_step_table`)、`print_host_matrix`、
  `_MATRIX_MARKS/_MATRIX_LEGEND/_LOG_MARKS`、`host_results_logline`。
- `show_step_header(step, total, mask, preview=False)` に拡張:
  - `preview=True` かつ manual ステップ →
    `  └ 手動ステップ(作業者の完了確認のみ)` を表示(run 時の文言と使い分け)。
  - それ以外は現行と同一(これが check --preview 第 2 部 = run と同一形式の根拠)。
  - preview ではステップ番号表示を `ステップ N/総数` のまま使う(run と同一)。
- cli.py は `from .render import console, ...` で利用。make_mask は cli に残す
  (Procedure 依存のため)。

---

## 6. cli.py(Step 3)

### 削除(D1)
- `--rollback` オプション、rollback 分岐、`show_rollback_hint`、サマリー・
  実行開始・list・check の rollback 表示、`log_name` の `_rollback` サフィックス。

### 環境変数フロー(D3)
```python
envman = EnvManager()                       # baseline 固定
resume_src = _find_latest_env_overlay(...)  # --start-from 時のみ検索(常時有効なので
                                            # share_env 条件なし)。なければ ValueError
                                            # (現行メッセージの shared_env.sh を
                                            #  env_overlay.sh に変えたもの)
# 確認ゲート通過・RunArtifacts 作成後:
if resume_src: shutil.copy(resume_src, art.dir / "env_overlay.sh")
               envman.load_overlay_script((art.dir / "env_overlay.sh").read_text())
else:          art.write_env_overlay(envman.overlay_script())   # 空オーバーレイ(常に作成)
# 各コマンドステップ:
result = run_command(step.command, timeout=..., cwd=..., on_line=echo,
                     env=envman.child_env(), capture_env=True)
if result.env_snapshot is not None:
    envman.update_from_snapshot(result.env_snapshot)
    art.write_env_overlay(envman.overlay_script())
```
- `_find_latest_shared_env` → `_find_latest_env_overlay` に改名、対象ファイル名変更。
- meta: `rollback` / `share_env` を削除。`--start-from` 時のみ
  `start_from` / `resumed_env_from`(復元元ディレクトリの env_overlay.sh パス文字列)。
- サマリー(D3/04 §3.1): rollback 行削除。secrets があれば無条件で
  「注意: export した値は env_overlay.sh に平文で残ります(保管・削除ルールに注意)」。
  `--start-from` 時は復元元を表示。
- 実行開始表示: share_env 行を削除し、復元時のみ「環境変数を復元: <パス>」を表示。

### 出力の逐次書き込み(D5)
- ステップ実行前に `files = art.open_step_files(step.number)` を開き、
  `echo` コールバック内で console 出力と同時に `files.write(mask(line)+"\n", is_stderr)`。
  実行後 close。rec.stdout/stderr への全量格納は判定用に維持。
- run.log のステップ開始エントリ(`--- ステップ N ---` とコマンド)は現行どおり
  実行前に書かれている(変更不要)。
- add_record が毎回 save_result("running") する(artifacts 側で実装済み)。

### シグナル(D4)
- `class SignalInterrupt(Exception): signum` を定義。main() 冒頭で SIGTERM /
  SIGHUP に「raise SignalInterrupt(signum)」ハンドラを設定(SIGINT は既定の
  KeyboardInterrupt のまま)。
- main() の except: KeyboardInterrupt → 現行どおり「中断されました」130。
  SignalInterrupt → 「中断されました」128+signum。
- cmd_run: `result.interrupted` が非 None のとき:
  - rec.status = "error"、rec.detail = f"シグナル ({signal.Signals(n).name}) により中断"
  - add_record → 判定・内訳はスキップ → RB-ONFAIL は表示しない(操作者の意図的
    中断のため)→ status="aborted"、exit_code = 128+n、break。
- cmd_run のステップループ全体を try で包み、KeyboardInterrupt / SignalInterrupt
  (プロンプト待ち中の受信)でも finalize("aborted") してから 128+n を返す
  (証跡を壊さない。仕様 05 §8)。

### check --preview の 2 部構成(D2)
```python
console.print()  # 第 1 部: list と同一の表
console.print(step_table(f"{proc.title} ({proc.path})", proc.steps, mask))
# 第 2 部: run と同一のステップ詳細
for s in proc.steps:
    show_step_header(s, len(proc.steps), mask, preview=True)
```
- 現行の独自プレビュー表示は削除。

### renumber(D7.3)
- rollback リセット分岐を削除。
- `path.write_text(...)` → `artifacts.atomic_write_text(path, ...)`。

### その他
- `__init__.py` の `__version__` を "0.5.0" に、pyproject.toml の version も
  "0.5.0" に(現在 0.1.0 で不整合のため合わせて修正)。
- cli.py 冒頭 docstring から rollback / share_env を削除し新機能を反映。

### tests(test_cli.py 等)
- rollback 系テストを削除/エラー期待に変更。share_env 系を常時引き継ぎ前提に書き換え。
- 追加: (1) run 後に env_overlay.sh が生成され、export した変数が次ステップに
  見えること(2 ステップの手順書で export → printenv)。(2) unset の tombstone が
  効くこと。(3) --start-from が env_overlay.sh を復元すること。(4) result.json に
  rollback / share_env キーがなく、実行中スナップショットで status=="running" に
  なること(1 ステップ目終了時点の result.json を読むテストは難しければ、
  add_record 直後の save_result を artifacts テストでカバー済みとして省略可)。
  (5) preview が表+詳細の 2 部構成になること(出力に両方の要素が含まれる程度の
  緩い assert でよい)。
- samples/: sample_procedure.md / sample_secrets_resume.md の RB-ROLLBACK
  セクションと share_env: true 行を削除(切り戻しは別ファイル化の方針に合わせ、
  単純に削除でよい)。テストがこれらを参照している場合は追従。

---

## 移行手順と検証

1. Step 1(parser)と Step 2(envstate + artifacts)は独立 → 並行実装可。
   それぞれ完了時に `pytest tests/ -q` 全緑を確認(Step 2 時点では logger.py は
   まだ残す。cli が参照しているため削除は Step 3 で行う)。
2. Step 3(executor / render / cli / logger.py 削除 / samples / 残テスト)。
3. 各 Step 完了ごとに git commit(レビューは Fable が diff で実施)。
4. 最終検証: 全テスト + サンプル手順書での実機実行(run / list / check --preview /
   renumber / --start-from 再開 / Ctrl-C 相当のシグナル)。
