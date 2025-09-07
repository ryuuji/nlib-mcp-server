import logging
from typing import Optional
import json
import httpx
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel


class BookSummary(BaseModel):
    id: str
    isbn: Optional[str]
    title: str
    author: str
    publisher: str
    published_year: Optional[str]
    url: Optional[str]


mcp = FastMCP("nlib-mcp-server")


@mcp.tool()
async def nlib_search_books(free: Optional[str],
                            title: Optional[str],
                            author: Optional[str],
                            publisher: Optional[str],
                            ndc: Optional[str],
                            year_start: Optional[int],
                            year_end: Optional[int],
                            ctx: Context) -> str:
    """中津川市立図書館の蔵書を検索する"""
    async with httpx.AsyncClient() as client:
        response = await client.get("https://unitrad-osaka-1.calil.jp/v1/search", params={
            "region": "gifu",
            "free": free,
            "title": title,
            "author": author,
            "publisher": publisher,
            "ndc": ndc,
            "year_start": year_start,
            "year_end": year_end
        })
        logging.info(response.url)
        if response.status_code != 200:
            await ctx.error("検索に失敗しました")
            return json.dumps({
                "books": []
            })
        data = response.json()
        uuid = data.get("uuid")
        while "中津川市" in data['remains']:
            response = await client.get("https://unitrad-osaka-1.calil.jp/v1/polling", params={"uuid": uuid,"timeout":"3", "version": str(data.get("version"))})
            await ctx.info(f"検索しています...")
            if response.status_code != 200:
                await ctx.error("検索に失敗しました")
                return json.dumps({
                    "books": []
                })
            data = response.json()

        rets = []
        for book in data['books']:
            if 'holdings' in book and 100914 in book['holdings']:
                rets.append(BookSummary(
                    id=book['id'],
                    isbn=book['isbn'] if book['isbn'] else '',
                    title=book['title'],
                    author=book['author'],
                    publisher=book['publisher'],
                    published_year=str(book.get('pubdate')) if book.get('pubdate') else '',
                    url=book['url'].get("100914") if book['url'].get("100914") else ''
                ))

        rets_dict = [book.model_dump() for book in rets]
        return json.dumps({
            "books": rets_dict
        })
