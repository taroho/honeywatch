# GeoIP セットアップ

## 概要

HoneyWatch の GeoIP 機能（`4-feat-geoip-ip-location`）は、攻撃イベントの送信元 IP を
MaxMind GeoLite2 データベース（`GeoLite2-City.mmdb`）を用いて地理情報（国・地域・都市・
緯度経度）に変換する。地理情報は永続化せず、API リクエストのたびに送信元 IP から都度解決する
（オンザフライ解決）ため、スキーマ変更やバックフィルは不要である。

`.mmdb` はライセンス上リポジトリに含めていないため、各自で取得・配置する必要がある。
**未配置でもシステムは動作する**（GeoIP が未読み込み状態になり、地理情報は null のまま
攻撃監視を継続する）。

## GeoLite2-City.mmdb の入手

MaxMind の GeoLite2 は無償で利用できるが、アカウント登録とライセンスキーの取得が必要である。

1. [MaxMind](https://www.maxmind.com/en/geolite2/signup) で無償アカウントを登録する。
2. アカウントページでライセンスキーを取得する。
3. GeoLite2 City 形式のデータベース（`GeoLite2-City.mmdb`）をダウンロードする。

## 配置

ダウンロードした `.mmdb` を、既定のパスに配置する。

```
data/geoip/GeoLite2-City.mmdb
```

`data/geoip/` ディレクトリが存在しない場合は作成する。`.mmdb` は各自で配置する運用のため、
ディレクトリを作成しても `.mmdb` ファイルはリポジトリにコミットしない。

## 環境変数

配置場所は環境変数 `GEOIP_DATABASE_PATH` で変更できる。`.env`（テンプレートは `.env.example`）に
次の項目を設定する。既定値のままで動作する。

| 環境変数 | 既定値 | 説明 |
|----------|--------|------|
| `GEOIP_DATABASE_PATH` | `data/geoip/GeoLite2-City.mmdb` | GeoLite2-City.mmdb のパス。任意のパスに変更可能 |
| `GEOIP_CACHE_SIZE` | `10000` | LRU キャッシュのエントリ上限 |
| `GEOIP_ENABLED` | `true` | 機能の有効/無効（無効時は常に未解決を返す） |

```
GEOIP_DATABASE_PATH=data/geoip/GeoLite2-City.mmdb
GEOIP_CACHE_SIZE=10000
GEOIP_ENABLED=true
```

## コミット・再配布に関する注意

- `GeoLite2-City.mmdb` および MaxMind のライセンスキーは、リポジトリにコミットしない。
- `data/geoip/` は `.gitignore` に登録済みのため、`.mmdb` はコミット対象外となる。
- MaxMind のライセンス条項に従い、`.mmdb` を再配布しない。
