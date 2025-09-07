# nlib-mcp-server

中津川市立図書館のMCPサーバー

## コンセプト

- 検索関係はカーリル Unitrad APIを利用する
- カーリルの業務用API（有償ライセンス）にアクセスしています。このAPIエンドポイントは非公開ですが、このMCPサーバーを試用する目的でのアクセスを許可します

## 機能

- [ ] 蔵書を検索できる nlib_search_books

## インストール

```bash
uv install
uv run mcp install
```