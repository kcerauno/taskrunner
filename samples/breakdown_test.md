# 判定内訳(NG時の詳細診断)テスト手順

NG で中断した瞬間に「どの条件で落ちたか」の内訳が表示されることを確認する手順書。
ステップ2が**意図的に失敗**し、判定内訳に [OK] / [NG] が混在して表示される。

実行方法(リポジトリ直下 = ~/wk_tool で):

    .venv/bin/runbook check --preview samples/breakdown_test.md
    .venv/bin/runbook run --yes --operator テスト samples/breakdown_test.md

期待結果: ステップ1は成功(内訳は表示されない)。ステップ2で NG となり、

    ├ 判定内訳:
    │   [OK] rc == 0
    │   [OK] out("active")
    │   [OK] rc == 0 or rc == 2
    │   [NG] not out("ERROR|FATAL")
    │   [NG] "running" in stdout

が表示されて即中断する(exit code 1)。内訳は run.log と result.json の
criteria_breakdown にも記録される。

## 1. 成功するステップ(OK時は内訳を表示しない)

### RB-DESCRIPTION
複数条件の基準式でも、OK のときは判定内訳が表示されないことの確認。

### RB-CMD
```bash
echo "service is active (running)"
```

### RB-EXPECTED
```
rc == 0 and out("active") and not out("ERROR|FATAL")
```

## 2. 意図的に失敗するステップ(NG時に内訳を表示)

### RB-DESCRIPTION
出力に ERROR を含み、running を含まないため、5条件のうち
「not out("ERROR|FATAL")」と「"running" in stdout」の2つが NG になる。
or のまとまり(rc == 0 or rc == 2)は分解されず1つの判断単位として表示される。

### RB-CMD
```bash
echo "service is active"
echo "ERROR: minor issue detected"
```

### RB-EXPECTED
```
rc == 0 and out("active") and
(rc == 0 or rc == 2) and
not out("ERROR|FATAL") and
"running" in stdout
```

### RB-ONFAIL
これはテスト用の意図的な失敗。判定内訳の [NG] 行が上に表示されていれば期待どおり。

## 3. 到達しないステップ(即中断の確認)

### RB-DESCRIPTION
ステップ2の NG で中断するため、このステップは実行されない。

### RB-CMD
```bash
echo "ここには到達しない"
```
