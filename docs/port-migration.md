# ポート変更手順書: 22番を SSH Honeypot に明け渡す

## 目的

SSH Honeypot への攻撃を増やすため、標準の 22番を Honeypot に割り当てる。
管理用 SSH（OS の sshd）は 2200番に移動する。SSM は保険として残す。

※ 当初 5555 を検討したが、一部ネットワークでは非標準の高番ポートの outbound が
塞がれることがあるため、比較的通りやすい 2200 を採用した。

## 変更前後の構成

| ポート | 変更前 | 変更後 |
|-------|--------|--------|
| 22 | 管理 SSH（自IP） | SSH Honeypot（全世界公開） |
| 2222 | SSH Honeypot（全世界公開） | 廃止（コンテナ内リッスンのみ） |
| 2200 | なし | 管理 SSH（自IP） |
| 8080 | HTTP Honeypot | 変更なし |
| 8000 / 3000 | API / Dashboard（自IP） | 変更なし |

- コンテナ内は非 root 実行のため 2222 をリッスンし、ホスト 22 → コンテナ 2222 に転送する
- destination_port は `HONEYPOT_SSH_PUBLIC_PORT=22` で 22 として記録される

## 前提

- SSM Session Manager が有効（万一 SSH で締め出されても入れる保険）
- ローカルのコード変更は済んでいる（docker-compose.yml, config, .env.example 等）

## 重要な原則

**「新しい経路で入れることを確認してから、古い経路を閉じる」**
順番を守らないと EC2 から締め出される。各ステップの確認を飛ばさないこと。

---

## 手順

### ステップ 1: ローカルでコードを push

```bash
cd ~/taroho/honeywatch
git add src/ .env.example docker/ docs/
git commit -m "feat: 管理SSHを2200へ移動し22番をHoneypotに割り当て"
git push
```

### ステップ 2: EC2 に接続（現在の 22番 SSH で）

```bash
ssh -i HoneyWatchKey.pem ubuntu@<EC2のIP>
```

### ステップ 3: 管理 SSH を 2200 でも待ち受けるようにする

いきなり 22 を消さず、22 と 2200 の両方で入れる状態を作る。

**注意（Ubuntu の socket activation）:**
Ubuntu 22.04 以降は `ssh.socket` が SSH の待ち受けを管理しており、
`sshd_config` の `Port` だけでは反映されないことがある。その場合は
socket 側にポートを追加する:

```bash
sudo systemctl edit ssh.socket
```

```
[Socket]
ListenStream=
ListenStream=0.0.0.0:22
ListenStream=0.0.0.0:2200
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ssh.socket
sudo ss -tlnp | grep -E ':22|:2200'
```

`sshd_config` で直接指定する場合は以下（socket 無効時）。

```bash
sudo vim /etc/ssh/sshd_config
```

`Port` 設定を以下のように両方書く（コメントアウトされていれば外す）:

```
Port 22
Port 2200
```

保存して再起動:

```bash
sudo systemctl restart ssh
```

### ステップ 4: Security Group に 2200 を追加

AWS コンソール → Security Group → インバウンドルール:

| タイプ | ポート | ソース |
|-------|-------|--------|
| Custom TCP | 2200 | 自分の IP/32 |

### ステップ 5: 2200 で入れることを確認【最重要】

**別のターミナル**を開いて（今の接続は保持したまま）:

```bash
ssh -p 2200 -i HoneyWatchKey.pem ubuntu@<EC2のIP>
```

到達できないときは、まず `nc -zv <EC2のIP> 2200` で届くか確認する
（timed out ならネットワーク側で塞がれている。IP が変わっていないかも確認）。

**ここで入れたら成功。入れない場合は先に進まず原因を解決すること。**
（入れないまま次に進むと、22番を消したとき締め出される）

### ステップ 6: 管理 SSH から 22番を外す

2200 で入れることを確認できたら、sshd から 22 を削除する。

```bash
sudo vim /etc/ssh/sshd_config
```

`Port 22` を削除（または `#` でコメントアウト）し、2200 のみにする:

```
Port 2200
```

socket activation を使っている場合は socket 側を 2200 のみにする:

```
[Socket]
ListenStream=
ListenStream=0.0.0.0:2200
```
（`sudo systemctl daemon-reload && sudo systemctl restart ssh.socket`）

再起動:

```bash
sudo systemctl restart ssh
```

これ以降、OS の管理 SSH は 2200 のみ。22番は空く。

### ステップ 7: コードを反映

```bash
cd ~/honeywatch
git pull
```

### ステップ 8: EC2 の .env に公開ポートを追記

`.env` は git 管理外のため手動で追加する（忘れると destination_port が 2222 のままになる）。

```bash
vim ~/honeywatch/.env
```

以下を追加:

```
HONEYPOT_SSH_PUBLIC_PORT=22
```

### ステップ 9: Honeypot を再起動

```bash
cd ~/honeywatch/docker
docker compose up -d honeypot
```

### ステップ 10: Security Group で 22番を Honeypot 用に変更

AWS コンソール → Security Group → インバウンドルール:

- **22番**: ソースを `0.0.0.0/0` に変更（Honeypot として全世界公開）
- **2222番**: 既存ルールがあれば削除

### ステップ 11: 動作確認

```bash
# 別ターミナルから 22番の Honeypot に接続テスト
ssh -p 22 test@<EC2のIP>
```

パスワードを求められて拒否されれば Honeypot が 22番で稼働している。
数分〜数十分でブルートフォースが観測され始める。

記録を確認（destination_port が 22 になっているか）:

```bash
# 管理接続（2200）で EC2 に入り
curl -u admin:<APIパスワード> "http://localhost:8000/api/v1/events?per_page=5"
```

---

## 変更後の管理接続コマンド

```bash
# 管理 SSH（2200）
ssh -p 2200 -i HoneyWatchKey.pem ubuntu@<EC2のIP>

# Dashboard 閲覧のトンネル（2200 経由）
ssh -p 2200 -i HoneyWatchKey.pem \
  -L 3000:localhost:3000 -L 8000:localhost:8000 \
  ubuntu@<EC2のIP>
```

---

## ロールバック（元に戻す場合）

1. sshd_config を `Port 22` に戻して `sudo systemctl restart ssh`
2. Security Group: 22番を自分の IP に戻す、2222番を全開放で復活
3. `.env` から `HONEYPOT_SSH_PUBLIC_PORT` を削除
4. docker-compose.yml のポートを `"0.0.0.0:2222:2222"` に戻す
5. `docker compose up -d honeypot`

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| 2200 で入れない | Security Group の 2200 ルール、socket/sshd の 2200 待ち受け（`ss -tlnp`）、`systemctl status ssh.socket` を確認 |
| 全 SSH が timed out | EC2 の IP が変わっていないか確認（停止→起動で変わる）。`ssh` 先のホスト名/IP が最新か確認 |
| 全 SSH で入れない | SSM Session Manager から接続して設定を修正 |
| 22番の Honeypot に繋がらない | SG の 22番が 0.0.0.0/0 か、`docker compose ps honeypot` が Up か確認 |
| destination_port が 2222 のまま | EC2 の `.env` に `HONEYPOT_SSH_PUBLIC_PORT=22` があるか確認し、honeypot を再起動 |
