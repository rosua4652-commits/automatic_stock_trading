import asyncio

import time

from unittest.mock import AsyncMock, MagicMock



import pytest



from app.engine.news_llm import (

    ArticleLlmResult,

    apply_llm_to_score,

    analyze_article,

    clear_llm_cache,

)

from app.engine.news_signals import (

    NewsArticle,

    NewsSymbolScore,

    is_news_surge,

)

from app.models import AppConfig





@pytest.fixture(autouse=True)

def _clear_cache():

    clear_llm_cache()

    yield

    clear_llm_cache()





def test_apply_llm_bearish_blocks_surge():

    cfg = AppConfig(news_llm_enabled=True, news_llm_bearish_block_threshold=60)

    sc = NewsSymbolScore(score=45.0, sentiment="positive", headline="BTC surge rally")

    apply_llm_to_score(

        sc,

        [ArticleLlmResult(direction="bearish", confidence=80, reason="실제로는 규제 우려")],

        cfg,

    )

    assert sc.llm_direction == "bearish"

    assert sc.llm_confidence == 80.0

    assert sc.score < 25

    assert not is_news_surge(sc, cfg)





def test_apply_llm_bullish_keeps_surge():

    sc = NewsSymbolScore(score=30.0, sentiment="positive")

    apply_llm_to_score(

        sc,

        [ArticleLlmResult(direction="bullish", confidence=70, reason="ETF 승인 기대")],

    )

    assert sc.llm_direction == "bullish"

    assert is_news_surge(sc, AppConfig())





def test_is_news_surge_rejects_bearish_llm_even_high_keyword_score():

    sc = NewsSymbolScore(

        score=50.0,

        sentiment="positive",

        llm_direction="bearish",

        llm_confidence=65.0,

        llm_reason="제목과 달리 하락 압력",

    )

    assert not is_news_surge(sc, AppConfig(news_llm_enabled=True))





def test_analyze_article_uses_mock_gemini():

    cfg = AppConfig(

        news_llm_enabled=True,

        news_llm_provider="gemini",

        gemini_api_key="AIza-test",

    )

    art = NewsArticle(

        title="Bitcoin surge but analysts warn of crash",

        source="CoinDesk",

        published_ts=time.time(),

        snippet="Regulatory fears mount despite rally headlines",

    )

    mock_resp = MagicMock()

    mock_resp.json.return_value = {

        "candidates": [

            {

                "content": {

                    "parts": [

                        {

                            "text": (

                                '{"direction":"bearish","confidence":85,'

                                '"reason_ko":"급등 표현이나 하락 경고가 우세"}'

                            )

                        }

                    ]

                }

            }

        ]

    }



    client = AsyncMock()

    client.post = AsyncMock(return_value=mock_resp)



    async def _run():

        result = await analyze_article(client, art, cfg, ttl_sec=420)

        assert result.direction == "bearish"

        assert result.confidence == 85

        assert "하락" in result.reason



        cached = await analyze_article(client, art, cfg, ttl_sec=420)

        assert cached.direction == "bearish"

        assert client.post.await_count == 1



        call_args = client.post.call_args

        assert "generativelanguage.googleapis.com" in call_args[0][0]



    asyncio.run(_run())





def test_analyze_article_uses_mock_openai():

    cfg = AppConfig(

        news_llm_enabled=True,

        news_llm_provider="openai",

        openai_api_key="sk-test",

    )

    art = NewsArticle(

        title="Bitcoin surge but analysts warn of crash",

        source="CoinDesk",

        published_ts=time.time(),

    )

    mock_resp = MagicMock()

    mock_resp.json.return_value = {

        "choices": [

            {

                "message": {

                    "content": (

                        '{"direction":"bearish","confidence":85,'

                        '"reason_ko":"급등 표현이나 하락 경고가 우세"}'

                    )

                }

            }

        ]

    }



    client = AsyncMock()

    client.post = AsyncMock(return_value=mock_resp)



    async def _run():

        result = await analyze_article(client, art, cfg, ttl_sec=420)

        assert result.direction == "bearish"

        assert result.confidence == 85



    asyncio.run(_run())

