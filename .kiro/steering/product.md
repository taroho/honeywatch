# Product

## 概要

HoneyWatch は **Honeypot-Based Attack Monitoring & Analysis Platform** です。
インターネット上の不審なアクセスを Honeypot で観測し、攻撃パターンを分析・可視化するセキュリティ監視プラットフォームです。

セキュリティエンジニア志望のポートフォリオとして、「攻撃を観測して、分析して、可視化する」作品を目指します。

## コンセプト

単なる Honeypot ではなく、以下の3点を重点的に実現する:

1. **実際の攻撃を観測できる** — 複数プロトコルの Honeypot で攻撃トラフィックを収集
2. **観測データから攻撃パターンを分析できる** — 攻撃分類・リスクスコア・タイムライン分析
3. **MITRE ATT&CK + AI で「なぜこの攻撃なのか」を説明できる** — セキュリティフレームワークへのマッピングと AI による要約

## 主要機能

| 機能 | 説明 |
|------|------|
| Honeypot | SSH / HTTP（将来的に FTP / Telnet も追加）の偽サービスで攻撃を観測 |
| Attack Log Collection | タイムスタンプ、送信元 IP、ポート、プロトコル、認証情報、リクエスト等をイベントとして記録 |
| Attack Classification | Brute Force, Port Scan, HTTP Scan, Credential Attack, Command Injection 等に自動分類 |
| Dashboard | 攻撃数、ユニーク IP 数、攻撃タイムライン、Top IP 等を可視化 |
| IP Analysis | IP 単位の攻撃履歴・リスクスコア表示 |
| Attack Timeline | 時間帯別の攻撃傾向を可視化 |
| Attack Pattern Analysis | 攻撃パターンの検出と詳細レポート |
| MITRE ATT&CK Mapping | 攻撃イベントを MITRE ATT&CK の Technique にマッピング |
| AI Attack Analyst | ログを AI に渡しセキュリティアナリスト向け要約を生成 |
| Alert | 閾値超過時にアラート通知（Slack / Discord 等） |

## 開発フェーズ

| Phase | 内容 |
|-------|------|
| Phase 1 — MVP | Honeypot、ログ収集、DB 保存、基本 Dashboard |
| Phase 2 — Detection | 攻撃分類、IP 分析、Timeline、Risk Score |
| Phase 3 — Security Intelligence | MITRE ATT&CK mapping、GeoIP、攻撃パターン分析、Alert |
| Phase 4 — AI | 攻撃ログ要約、インシデント分析、推奨対応、自然言語検索 |
| Phase 5 — Production | Docker、CI/CD、Tests、Security hardening、Monitoring、Documentation |

## デプロイ方針（最終構成）

- AWS EC2 インスタンス 1台に全コンポーネントを同居させる
- Docker Compose でコンテナ管理
- ネットワーク分離は Docker ネットワーク + Security Group で実現

```
Cloud (AWS)
└── HoneyWatch 専用 VM (EC2)
     ├── Honeypot コンテナ（外部公開: SSH 22, HTTP 80 / 8080）
     ├── Event Worker コンテナ
     ├── API + Dashboard コンテナ（管理用: 8000, 3000）
     ├── PostgreSQL コンテナ（内部のみ）
     └── Redis コンテナ（内部のみ）
```

- Security Group で Honeypot ポートのみ全開放、管理ポートは自分の IP のみ許可

- HTTP Honeypot はホスト **80 番**でも待ち受ける（コンテナ内は 8080 リッスンのまま、ホスト 80/8080 → コンテナ 8080 にマッピング）。80 番で待つことで無差別 Web スキャン（WordPress ログイン総当たり・PHP 脆弱性探索・`.env` 探索等）を広く観測する。従来の 8080 も併せて公開する。
- 本番で 80 を観測対象にするには、Security Group のインバウンドに TCP 80 を全開放（`0.0.0.0/0`）で追加する。
- 公開ポートの整理:
  - 攻撃観測用（全開放）: SSH `22`、HTTP `80` / `8080`
  - 管理用（自分の IP のみ許可）: 管理 SSH `2200`、API `8000`、Dashboard `3000`
  - 外部非公開（`127.0.0.1` バインド）: PostgreSQL `5432`、Redis `6379`
- 開発時はローカル Docker Compose で同一構成を再現できるようにする

## セキュリティ方針

- Honeypot を本番環境へ直接さらさず、隔離環境で運用する
- 最小権限の原則を徹底する
- ログに含まれる個人情報（IP 等）の取り扱いに配慮する
- 管理系ネットワークと Honeypot ネットワークを分離する
- 実際の認証情報など機密性の高い値は必要以上に保存しない
