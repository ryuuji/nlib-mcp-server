"""
Unitrad UI APIライブラリ

Copyright (c) 2017 CALIL Inc.
This software is released under the MIT License.
http://opensource.org/licenses/mit-license.php
"""

import logging
import asyncio
import aiohttp
import urllib.parse
from typing import Dict, List, Any, Optional, Callable, TypedDict, Union

# 定数
ENDPOINT = 'https://unitrad.calil.jp/v1/'
FIELDS = ['free', 'title', 'author', 'publisher', 'isbn', 'ndc', 'year_start', 'year_end', 'region']

# 型定義
class UnitradQuery(TypedDict, total=False):
    free: Optional[str]
    title: Optional[str]
    author: Optional[str]
    publisher: Optional[str]
    isbn: Optional[str]
    ndc: Optional[int]
    year_start: Optional[str]
    year_end: Optional[str]
    region: str

class BookDiff(TypedDict):
    _idx: int
    # その他の任意のキー
    
class BooksDiff(TypedDict):
    insert: List[Any]
    update: List[BookDiff]

class UnitradResult(TypedDict):
    uuid: str
    version: int
    running: bool
    books: List[Any]
    books_diff: Optional[BooksDiff]
    remains: Optional[List[str]]
    errors: Optional[List[str]]

# ヘルパー関数

def object_to_query_string(params: Dict[str, Any]) -> str:
    """
    クエリパラメータをURLに変換するヘルパー関数
    
    Args:
        params: オブジェクトパラメータ
    
    Returns:
        URLクエリ文字列
    """
    query_params = []
    for key, value in params.items():
        if value is not None and value != '':
            query_params.append(f"{urllib.parse.quote(key)}={urllib.parse.quote(str(value))}")
    
    return f"?{'&'.join(query_params)}" if query_params else ""

async def _request(command: str, params: Dict[str, Any] = None) -> Any:
    """
    Unitrad APIにアクセスするための共通関数
    
    Args:
        command: APIのコマンド
        params: クエリパラメータ
    
    Returns:
        APIレスポンス
    
    Raises:
        Exception: API呼び出しに失敗した場合
    """
    if params is None:
        params = {}
        
    url = f"{ENDPOINT}{command}{object_to_query_string(params)}"
    logging.info(url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"API request failed: {response.status}")
            
            return await response.json()


class Api:
    """横断検索APIクラス"""
    
    def __init__(self, query: UnitradQuery, callback: Callable[[UnitradResult], None]):
        """
        検索APIの起動
        
        Args:
            query: 検索クエリ
            callback: コールバック関数
        """
        self.callback = callback
        self.killed = False
        self.data = None
        asyncio.create_task(self.search(query))
    
    def kill(self) -> None:
        """検索の中止"""
        self.killed = True
    
    async def search(self, query: UnitradQuery) -> None:
        """
        検索を実行
        
        Args:
            query: 検索クエリ
        """
        logging.info("Starting Unitrad search")
        logging.info(query)
        if self.killed:
            return
        
        try:
            data = await _request('search', strip_query(query))
            await self.receive(data)
        except Exception as err:
            logging.info(f"Search error: {err}")
            # エラー時は少し待って再試行
            await asyncio.sleep(1)
            asyncio.create_task(self.search(query))
    
    async def polling(self) -> None:
        """ポーリングを実行"""
        logging.info("Starting Unitrad polling")
        if self.killed:
            return
        
        try:
            data = await _request('polling', {
                'uuid': self.data['uuid'],
                'version': self.data['version'],
                'diff': 1,
                'timeout': 10
            })
            
            if data is None:
                await asyncio.sleep(1)
                asyncio.create_task(self.polling())
            else:
                await self.receive(data)
        except Exception as err:
            logging.info(f"Polling error: {err}")
            await asyncio.sleep(1)
            asyncio.create_task(self.polling())
    
    async def receive(self, data: UnitradResult) -> None:
        """
        APIからのデータを処理
        
        Args:
            data: APIのレスポンスデータ
        """
        logging.info("Received data from Unitrad API")
        if self.killed:
            return
        
        if 'books_diff' in data and data['books_diff']:
            # 差分更新の場合
            self.data['books'].extend(data['books_diff']['insert'])
            
            # books_diff以外のプロパティを更新
            for key, value in data.items():
                if key != 'books_diff':
                    self.data[key] = value
            
            # 個別の書籍データを更新
            for d in data['books_diff']['update']:
                for key, value in d.items():
                    if key != '_idx':
                        idx = d['_idx']
                        if isinstance(value, list):
                            self.data['books'][idx][key].extend(value)
                        elif isinstance(value, dict):
                            for k, v in value.items():
                                self.data['books'][idx][key][k] = v
                        else:
                            self.data['books'][idx][key] = value
        else:
            # 完全に新しいデータの場合
            self.data = data
        
        # コールバックで通知
        self.callback(self.data)
        
        # 継続判定
        if data['running'] is True:
            logging.info('[Unitrad] continue...')
            if data['version'] == 1 and len(self.data['books']) == 0:
                await asyncio.sleep(0.02)
                asyncio.create_task(self.polling())
            else:
                await asyncio.sleep(0.5)
                asyncio.create_task(self.polling())
        else:
            logging.info('[Unitrad] complete.')


def normalize_query(query: Dict[str, str]) -> UnitradQuery:
    """
    クエリを共通形式にして返す
    
    Args:
        query: 元のクエリ
    
    Returns:
        正規化されたクエリ
    """
    tmp = {}
    for k in FIELDS:
        tmp[k] = query.get(k, '')
    return tmp


def is_empty_query(query: Optional[UnitradQuery]) -> bool:
    """
    クエリが空かどうか判定する
      "region"のみの場合は空と判定する
    
    Args:
        query: 判定するクエリ
    
    Returns:
        空かどうか
    """
    if query:
        for k in FIELDS:
            if k == 'region':
                continue
            if k in query and query[k] != '':
                return False
    return True


def is_equal_query(q1: Optional[UnitradQuery], q2: Optional[UnitradQuery]) -> bool:
    """
    クエリが同じかどうか判定する
    
    Args:
        q1: 比較元クエリ
        q2: 比較先クエリ
    
    Returns:
        同じかどうか
    """
    for k in FIELDS:
        if k == 'region':
            continue
        val1 = q1.get(k, '') if q1 else ''
        val2 = q2.get(k, '') if q2 else ''
        if val1 != val2:
            return False
    return True


def strip_query(query: UnitradQuery) -> UnitradQuery:
    """
    クエリを内容のあるプロパティだけにする
    
    Args:
        query: 元のクエリ
    
    Returns:
        内容のあるプロパティのみのクエリ
    """
    tmp = {}
    for k in FIELDS:
        if k in query and query[k] != '':
            tmp[k] = query[k]
    return tmp


async def fetch_mapping(region: str, callback: Callable[[Any], None]) -> None:
    """
    マッピングデータを取得する
    
    Args:
        region: リージョン
        callback: コールバック関数
    """
    try:
        data = await _request('mapping', {'region': region})
        callback(data)
    except Exception as err:
        logging.info(f"Mapping fetch error: {err}")
