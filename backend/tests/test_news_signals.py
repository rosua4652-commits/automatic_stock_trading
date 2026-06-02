import time

from app.engine.news_signals import (
    NewsArticle,
    is_news_surge,
    score_articles_for_base,
    _match_bases,
)
from app.models import AppConfig


def test_match_bases_from_headline():
    bases = _match_bases("Bitcoin ETF approval drives BTC surge to new high")
    assert "BTC" in bases


def test_parse_rss_link():
    xml = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>BTC ETF approved</title>
        <link>https://example.com/btc-etf</link>
        <pubDate>Mon, 02 Jun 2025 10:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""
    from app.engine.news_signals import _parse_rss_xml

    arts = _parse_rss_xml(xml, "Test")
    assert len(arts) == 1
    assert arts[0].url == "https://example.com/btc-etf"


def test_score_articles_includes_url():
    now = time.time()
    arts = [
        NewsArticle(
            title="Solana partnership listing",
            source="CoinDesk",
            published_ts=now - 3600,
            url="https://example.com/sol-news",
        ),
    ]
    sc = score_articles_for_base("SOL", arts)
    assert sc.url == "https://example.com/sol-news"


def test_score_articles_positive_keywords():
    now = time.time()
    arts = [
        NewsArticle(
            title="Solana partnership with major bank listing on exchange",
            source="CoinDesk",
            published_ts=now - 3600,
        ),
        NewsArticle(
            title="SOL token burn announced amid rally",
            source="CoinTelegraph",
            published_ts=now - 7200,
        ),
    ]
    sc = score_articles_for_base("SOL", arts)
    assert sc.count == 2
    assert sc.score >= 25
    assert sc.sentiment == "positive"
    assert is_news_surge(sc, AppConfig())


def test_score_articles_negative_reduces():
    now = time.time()
    arts = [
        NewsArticle(
            title="Token hack exploit leads to crash and delist fears",
            source="CoinDesk",
            published_ts=now - 1800,
        ),
    ]
    sc = score_articles_for_base("ETH", arts)
    assert sc.sentiment == "negative"


def test_news_disabled():
    cfg = AppConfig(news_enabled=False)
    sc = score_articles_for_base(
        "BTC",
        [
            NewsArticle(
                title="Bitcoin ETF approval",
                source="x",
                published_ts=time.time(),
            )
        ],
    )
    assert not is_news_surge(sc, cfg)
