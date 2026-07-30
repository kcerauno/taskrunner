#!/usr/bin/env python3
"""logs/ 配下の result.json を集計・書き出しするユーティリティ。

runbook 本体(runbook パッケージ)には手を入れず、蓄積された証跡を後から読むための
補助ツール。result.json だけを読み、生出力(stepNN_stdout.txt)は参照しない。

    # 1回の実行を Excel 貼り付け用の TSV にする(証跡の手動移行を楽にする)
    tools/logs_report.py evidence logs/output_demo_20260730_215504

    # 直近の実行を対象にする(ディレクトリ指定を省略)
    tools/logs_report.py evidence --latest output_demo

    # 全実行の一覧(いつ・誰が・どうなったか)
    tools/logs_report.py runs

    # 手順書ごとの失敗ステップ集計(手順書・基準式の弱点を見つける)
    tools/logs_report.py failures

    # ステップの所要時間の推移(遅くなっていないかを見る)
    tools/logs_report.py timing feature_test
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich import box  # noqa: E402
from rich.table import Table  # noqa: E402

# ホスト別結果の記号(O/X/!)とコンソール表示を揃えるため runbook 側の関数を使う
from runbook.render import console, host_results_logline  # noqa: E402

STATUS_LABEL = {"ok": "完了", "ng": "失敗", "error": "エラー", "skipped": "スキップ"}


def flat(text: str) -> str:
    """複数行の値を1行に潰す(TSV を Excel に貼ったときセルが分かれないようにする)"""
    return " ".join(text.split())


def make_table(*columns: str) -> Table:
    """CJK 幅を正しく扱うため rich の表を使う(手作業のパディングでは揃わない)"""
    table = Table(box=box.SIMPLE, header_style="bold #cfd3ea", border_style="#4a4f78",
                  pad_edge=False, show_edge=False)
    for name in columns:
        table.add_column(name, overflow="fold")
    return table


def load_runs(logs_dir: Path, prefix: str | None = None) -> list[tuple[Path, dict]]:
    """logs/*/result.json を読み、(ディレクトリ, 内容) を実行時刻順で返す。

    result.json が壊れている実行(実行中に強制終了された等)は警告して飛ばす。
    """
    runs = []
    for path in sorted(logs_dir.glob("*/result.json")):
        if prefix and not path.parent.name.startswith(prefix):
            continue
        try:
            runs.append((path.parent, json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError) as e:
            print(f"警告: {path} を読めません ({e})", file=sys.stderr)
    return runs


def pick_run(logs_dir: Path, target: str | None, latest: str | None) -> tuple[Path, dict]:
    if latest is not None:
        runs = load_runs(logs_dir, prefix=latest)
        if not runs:
            sys.exit(f"エラー: {latest} で始まる実行が {logs_dir} にありません")
        return runs[-1]
    if target is None:
        sys.exit("エラー: 実行ディレクトリか --latest を指定してください")
    d = Path(target)
    result = d / "result.json"
    if not result.exists():
        sys.exit(f"エラー: {result} がありません")
    return d, json.loads(result.read_text(encoding="utf-8"))


def cmd_evidence(args: argparse.Namespace) -> int:
    """1実行の証跡を TSV で出す。Excel へそのまま貼れる形にする。"""
    run_dir, d = pick_run(Path(args.logs), args.run, args.latest)
    proc = d["procedure"]
    w = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")

    # ヘッダ部: 誰がいつ何を実行したか(監査で必ず聞かれる項目)
    w.writerow(["手順書", proc["title"]])
    w.writerow(["ファイル", proc["file"]])
    w.writerow(["作業者", proc.get("operator") or "(記録なし)"])
    w.writerow(["確認者", proc.get("checker") or "(なし)"])
    w.writerow(["実行モード", "逐次" if proc.get("mode") == "interactive" else "一括"])
    w.writerow(["開始", d.get("started_at", "")])
    w.writerow(["終了", d.get("finished_at", "")])
    w.writerow(["結果", "完了" if d.get("status") == "completed" else "中断"])
    w.writerow(["証跡", str(run_dir)])
    w.writerow([])

    w.writerow(["No.", "ステップ", "結果", "rc", "所要(s)", "開始", "終了",
                "コマンド", "正常性基準", "備考", "ホスト別結果"])
    recorded = {s["number"] for s in d["steps"]}
    for s in d["steps"]:
        # ホスト別結果はコンソール・run.log と同じ「db01=O db02=X」表記に揃える
        hosts = host_results_logline(s.get("host_results", {}))
        w.writerow([
            s["number"], s["title"], STATUS_LABEL.get(s["status"], s["status"]),
            "" if s["rc"] is None else s["rc"],
            "" if s["duration"] is None else s["duration"],
            s.get("started_at") or "", s.get("finished_at") or "",
            " ; ".join(s["command"].splitlines()), flat(s["criteria"]),
            s.get("detail", ""), hosts,
        ])
    # 中断で到達しなかったステップも行として残す(証跡に穴を作らない)
    for n in sorted(set(proc.get("selected_steps", [])) - recorded):
        w.writerow([n, "(記録なし)", "未実行", "", "", "", "", "", "", "中断により未到達", ""])

    # 失敗の判定内訳は原因調査で最も参照されるので末尾に付ける
    for s in d["steps"]:
        if s.get("criteria_breakdown"):
            w.writerow([])
            w.writerow([f"ステップ{s['number']} 判定内訳", s["title"]])
            w.writerow(["判定", "条件式", "実際の出力"])
            for b in s["criteria_breakdown"]:
                w.writerow(["OK" if b["ok"] else "NG", flat(b["expr"]), b.get("evidence", "")])
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    """全実行の一覧。いつ・誰が・どの手順書を・どうしたか。"""
    runs = load_runs(Path(args.logs), args.prefix)
    if not runs:
        print("該当する実行がありません")
        return 0
    table = make_table("実行", "結果", "作業者", "確認者", "記録/対象", "失敗ステップ")
    for run_dir, d in runs:
        steps = d.get("steps", [])
        ng = [str(s["number"]) for s in steps if s["status"] in ("ng", "error")]
        selected = d["procedure"].get("selected_steps", [])
        completed = d.get("status") == "completed"
        table.add_row(
            run_dir.name,
            "[#5fd9a4]完了[/]" if completed else "[#ff6b60]中断[/]",
            d["procedure"].get("operator") or "-",
            d["procedure"].get("checker") or "-",
            f"{len(steps)}/{len(selected)}",
            ",".join(ng) or "-",
        )
    console.print(table)
    console.print(f"計 {len(runs)} 実行")
    return 0


def cmd_failures(args: argparse.Namespace) -> int:
    """手順書ごとに「どのステップが何回失敗したか」を集計する。

    同じステップが繰り返し失敗しているなら、環境ではなく手順書か基準式の側に
    問題がある可能性が高い(直すべき対象を特定するための材料)。
    """
    runs = load_runs(Path(args.logs), args.prefix)
    by_proc: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    details: dict[tuple, str] = {}
    for _, d in runs:
        name = Path(d["procedure"]["file"]).name
        totals[name] += 1
        for s in d.get("steps", []):
            if s["status"] in ("ng", "error"):
                key = (s["number"], s["title"])
                by_proc[name][key] += 1
                details[(name, key)] = s.get("detail", "")
    if not by_proc:
        print("失敗した実行はありません")
        return 0
    for name in sorted(by_proc):
        console.print(f"\n[bold #cfd3ea]■ {name}[/] (全 {totals[name]} 実行)")
        table = make_table("失敗回数", "No.", "ステップ", "内容")
        for (num, title), count in by_proc[name].most_common():
            table.add_row(f"{count}回", str(num), title, details[(name, (num, title))] or "-")
        console.print(table)
    return 0


def cmd_timing(args: argparse.Namespace) -> int:
    """ステップごとの所要時間の分布。遅いステップ・ばらつくステップを見つける。"""
    runs = load_runs(Path(args.logs), args.prefix)
    series: dict[tuple, list[float]] = defaultdict(list)
    for _, d in runs:
        for s in d.get("steps", []):
            if s.get("duration") is not None:
                series[(s["number"], s["title"])].append(s["duration"])
    if not series:
        print("所要時間の記録がありません")
        return 0
    table = make_table("No.", "ステップ", "回数", "最小(s)", "中央(s)", "最大(s)")
    for (num, title), values in sorted(series.items()):
        table.add_row(str(num), title, str(len(values)),
                      f"{min(values):.3f}", f"{statistics.median(values):.3f}",
                      f"{max(values):.3f}")
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="logs/ 配下の実行証跡(result.json)を集計・書き出しする",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--logs", default="logs", help="ログ保存先ディレクトリ(既定: logs)")
    sub = ap.add_subparsers(dest="subcommand", required=True)

    p_ev = sub.add_parser("evidence", help="1実行の証跡を TSV で出力する(Excel 貼り付け用)")
    p_ev.add_argument("run", nargs="?", help="実行ディレクトリ(例: logs/xxx_20260730_120000)")
    p_ev.add_argument("--latest", metavar="PREFIX",
                      help="この接頭辞で始まる最新の実行を対象にする(例: output_demo)")
    p_ev.set_defaults(func=cmd_evidence)

    p_runs = sub.add_parser("runs", help="全実行の一覧を表示する")
    p_runs.add_argument("prefix", nargs="?", help="手順書名の接頭辞で絞り込む")
    p_runs.set_defaults(func=cmd_runs)

    p_fail = sub.add_parser("failures", help="手順書ごとの失敗ステップを集計する")
    p_fail.add_argument("prefix", nargs="?", help="手順書名の接頭辞で絞り込む")
    p_fail.set_defaults(func=cmd_failures)

    p_time = sub.add_parser("timing", help="ステップごとの所要時間の分布を出す")
    p_time.add_argument("prefix", nargs="?", help="手順書名の接頭辞で絞り込む")
    p_time.set_defaults(func=cmd_timing)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
