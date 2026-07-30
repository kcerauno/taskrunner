# ansible ad-hoc サンプル手順書

```runbook
vars:
  INVENTORY: ./samples/local_test/inventory.ini
```

注意: 意図しない環境での実行を防ぐため、インベントリは共通設定(上記の runbook フェンス)
には書けない。各ステップで「行内指定」または「RB-LOCALDEF」により毎回指定する。

## 全webサーバの稼働確認(行内指定スタイル)

### RB-DESCRIPTION
フェンス1行目を「ansible ターゲット -i インベントリ [オプション]」で始めると、
その行が起動指定としてそのまま使われる。2行目以降がリモートコマンド。

### RB-CMD
```ansible
ansible webservers -i {{INVENTORY}}
uptime
```

### RB-EXPECTED
```
rc == 0 and out("CHANGED|SUCCESS") and not out("UNREACHABLE|FAILED")
```

## DBサーバのディスク確認(RB-LOCALDEF スタイル)

### RB-DESCRIPTION
行内指定の代わりに、ステップの RB-LOCALDEF で inventory / target を指定する書き方。
extra_args で任意のオプションも追加できる。

### RB-CMD
```ansible
df -h
```

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: db01
timeout: 300
```

### RB-EXPECTED
```
rc == 0 and not out(" 100%|UNREACHABLE|FAILED")
```
