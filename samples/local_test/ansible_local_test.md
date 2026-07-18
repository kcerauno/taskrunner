# ansible ローカル6ホスト検証手順

```runbook
vars:
  INVENTORY: samples/local_test/inventory.ini
  CHECK_LABEL: 定期点検
ansible:
  target: all
  host_matrix: true
```

## 1. 全6ホストの疎通確認

### RB-DESCRIPTION
インベントリの全擬似ホスト(web01-03, db01-02, mon01)で hostname と実行ユーザを表示する。
6ホスト全てが応答し、UNREACHABLE/FAILED がないことを確認する。

### RB-CMD
```ansible
echo "host=$(hostname) user=$(id -un)"
```

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
```

### RB-EXPECTED
```
rc == 0 and
out("web01 \| CHANGED") and out("web02 \| CHANGED") and out("web03 \| CHANGED") and
out("db01 \| CHANGED") and out("db02 \| CHANGED") and out("mon01 \| CHANGED") and
not out("UNREACHABLE|FAILED")
```

## 2. local uname

### RB-DESCRIPTION
localでuname -aを実行する。

### RB-CMD
```bash
uname -a && \
echo hoge
```

### RB-EXPECTED
```
rc == 0
```

## 3. webservers グループのみ負荷確認

### RB-DESCRIPTION
web01〜web03 の3ホストだけを対象に uptime を実行する(並列度6)。
dbservers/monitoring のホストが混ざっていないことも確認する。

### RB-CMD
```ansible
uptime
```

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: webservers
  extra_args: -f 6
timeout: 120
```

### RB-EXPECTED
```
rc == 0 and
out("web01") and out("web02") and out("web03") and
not out("db01|db02|mon01") and
not out("UNREACHABLE|FAILED")
```

## 4. db01 単一ホストのディスク確認

### RB-DESCRIPTION
ステップ設定で target を単一ホスト db01 に上書きし、ディスク使用率を確認する。
使用率100%のファイルシステムがないこと。

### RB-CMD
```ansible
df -h /
```

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: db01
```

### RB-EXPECTED
```
rc == 0 and out("db01 \| CHANGED") and not out(" 100%|UNREACHABLE|FAILED")
```

## 5. Playbook による稼働確認

### RB-DESCRIPTION
playbook フェンスにプレイブックのファイルパスを書くと ansible-playbook で実行される。
target(webservers)は -l として適用され、手順書の変数は -e で渡るので
プレイブック内の jinja2 から CHECK_LABEL をそのまま参照できる。

### RB-CMD
```playbook
samples/local_test/site_check.yml
```

### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: webservers
```

### RB-EXPECTED
```
rc == 0 and out("failed=0") and not out("failed=[1-9]|unreachable=[1-9]")
```

## 6. 手順書変数と jinja2 の混在確認

### RB-DESCRIPTION
ansible フェンス内では手順書の変数({{CHECK_LABEL}} など)は extra-vars として渡され、
ansible のマジック変数({{ inventory_hostname }} など)と同じ記法で共存できる。
webservers の各ホストが自分のホスト名(web01〜web03)を報告することを確認する。

### RB-CMD
```ansible
echo "{{CHECK_LABEL}}: {{ inventory_hostname }} は正常です"
```

```ansible
echo "{{CHECK_LABEL}}: {{ inventory_hostname }} は正常ですよーーーーー"
```


### RB-LOCALDEF
```yaml
ansible:
  inventory: "{{INVENTORY}}"
  target: webservers
```

### RB-EXPECTED
```
rc == 0 and
out("定期点検: web01 は正常です") and
out("定期点検: web02 は正常です") and
out("定期点検: web03 は正常です") and
not out("UNREACHABLE|FAILED")
```
