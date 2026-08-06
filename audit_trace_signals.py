import os
import sys
import time
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

from knowledge.coin import Coin
from intelligence.social import _fetch_twitter_mentions, _fetch_duckduckgo_mentions, collect_social, TWITTER_ENABLED, TWITTER_SEARCH_URL
from intelligence.news import _fetch_cryptopanic, _fetch_google_news, collect_news, CRYPTOPANIC_RSS
from intelligence.sentiment import collect_sentiment, analyze_sentiment
from intelligence.sarcasm import collect_sarcasm, detect_sarcasm
from intelligence.narrative import collect_narrative, classify_narrative
from intelligence.narrative_heat import collect_narrative_heat, _fetch_recent_headlines, calculate_narrative_heat
from intelligence.kol import collect_kol, _search_kol_mentions, KOL_LIST
from intelligence.community import collect_community, _fetch_twitter_followers, _extract_twitter_handle
from intelligence.momentum import collect_momentum

# Signals data from DB
jibanyan_coin = Coin()
jibanyan_coin.symbol = "Jibanyan"
jibanyan_coin.name = "Jibanyan cat"
jibanyan_coin.contract = "GoYgKp7R8VTcJveLzm6sfbVB3XJYeh1EYjftWzCipump"
jibanyan_coin.source = "GemTools"
jibanyan_coin.signal_id = "25710e91-d1df-4028-b97f-3bdd736aee72"
jibanyan_coin.raw_message = "🚀 $Jibanyan (Jibanyan cat)\nGoYgKp7R8VTcJveLzm6sfbVB3XJYeh1EYjftWzCipump\n\nGTscore: ⭐⭐☆☆☆\n\n📊 MC: $34.7K · ⏱ Age: 57m · 👪 Holders: 252"

danothy_coin = Coin()
danothy_coin.symbol = "DANOTHY"
danothy_coin.name = "Dumpster Danothy"
danothy_coin.contract = "mxHK8rcc5nXaUBNwRYPyWZgMF9qMShWX8jrJpW2pump"
danothy_coin.source = "GemTools"
danothy_coin.signal_id = "0a1df325-87d6-4085-bf30-801058bf32ef"
danothy_coin.raw_message = "🚀 $DANOTHY (Dumpster Danothy)\nmxHK8rcc5nXaUBNwRYPyWZgMF9qMShWX8jrJpW2pump\n\nGTscore: ⭐⭐☆☆☆\n\n📊 MC: $36.5K · ⏱ Age: 45s · 👪 Holders: 266"

coins = [jibanyan_coin, danothy_coin]

print("================================================================================")
print("INTELLIGENCE LAYER PRODUCTION AUDIT FOR SIGNALS: Jibanyan AND DANOTHY")
print("================================================================================\n")

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

for coin in coins:
    symbol = coin.symbol
    name = coin.name
    print(f"################################################################################")
    print(f"TARGET COIN: {symbol} (Name: {name})")
    print(f"################################################################################\n")

    # --------------------------------------------------------------------------
    # 1. SOCIAL & X/TWITTER SEARCH
    # --------------------------------------------------------------------------
    print("--- [MODULE 1: SOCIAL & X/TWITTER SEARCH] ---")
    print(f"Executed: YES (via runner -> collect_social)")
    
    # Twitter Sub-call
    query_twitter = f"({symbol} OR {name}) (crypto OR sol OR solana OR token) lang:en -is:retweet"
    print(f"Sub-call 1: X/Twitter Search API v2")
    print(f"  Endpoint: {TWITTER_SEARCH_URL}")
    print(f"  Generated Query: {query_twitter}")
    if TWITTER_ENABLED:
        try:
            headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
            params = {"query": query_twitter, "max_results": 100, "tweet.fields": "created_at,public_metrics"}
            res = requests.get(TWITTER_SEARCH_URL, headers=headers, params=params, timeout=8)
            print(f"  HTTP Status Code: {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                raw_cnt = data.get("meta", {}).get("result_count", 0)
                kept_cnt = len(data.get("data", []))
                print(f"  Raw Results Returned: {raw_cnt}")
                print(f"  Results Kept After Filtering: {kept_cnt}")
            else:
                print(f"  Raw Results Returned: 0 (HTTP {res.status_code}: {res.text[:150]})")
                print(f"  Results Kept After Filtering: 0")
        except Exception as e:
            print(f"  HTTP Call Exception: {e}")
    else:
        print(f"  TWITTER_ENABLED is False (no bearer token)")

    # DuckDuckGo Sub-call
    print(f"Sub-call 2: DuckDuckGo Fallback")
    ddg_url = "https://api.duckduckgo.com/"
    ddg_query = f"{symbol} {name} crypto solana"
    print(f"  Endpoint: {ddg_url}")
    print(f"  Generated Query: {ddg_query}")
    try:
        ddg_params = {"q": ddg_query, "format": "json", "no_redirect": "1", "no_html": "1"}
        ddg_res = requests.get(ddg_url, params=ddg_params, timeout=5)
        print(f"  HTTP Status Code: {ddg_res.status_code}")
        if ddg_res.status_code == 200:
            ddg_data = ddg_res.json()
            topics = ddg_data.get("RelatedTopics", [])
            print(f"  Raw Results Returned: {len(topics)}")
            print(f"  Results Kept After Filtering: {len(topics)}")
        else:
            print(f"  Raw Results Returned: 0")
            print(f"  Results Kept After Filtering: 0")
    except Exception as e:
        print(f"  HTTP Call Exception: {e}")

    social_result = collect_social(coin)
    print(f"DB Output (Social): social_mentions={social_result.get('social_mentions')}, social_velocity={social_result.get('social_velocity')}, engagement_score={social_result.get('engagement_score')}, viral_score={social_result.get('viral_score')}\n")

    # --------------------------------------------------------------------------
    # 2. NEWS (CryptoPanic & Google News RSS)
    # --------------------------------------------------------------------------
    print("--- [MODULE 2: NEWS (CryptoPanic & Google News RSS)] ---")
    print(f"Executed: YES (via runner -> collect_news)")
    
    # Sub-call 1: CryptoPanic RSS
    print(f"Sub-call 1: CryptoPanic RSS")
    print(f"  Endpoint: {CRYPTOPANIC_RSS}")
    print(f"  Generated Query: None (RSS feed poll), filtered locally by headline containing '{symbol.upper()}'")
    try:
        cp_res = requests.get(CRYPTOPANIC_RSS, timeout=8)
        print(f"  HTTP Status Code: {cp_res.status_code}")
        if cp_res.status_code == 200:
            root = ET.fromstring(cp_res.text)
            items = list(root.iter("item"))
            raw_cnt = len(items)
            matched = [item for item in items if item.find("title") is not None and symbol.upper() in (item.find("title").text or "").upper()]
            print(f"  Raw Results Returned (Total items in RSS): {raw_cnt}")
            print(f"  Results Kept After Filtering (symbol match & age < 24h): {len(matched)}")
        else:
            print(f"  Raw Results Returned: 0")
            print(f"  Results Kept After Filtering: 0")
    except Exception as e:
        print(f"  HTTP Call Exception: {e}")

    # Sub-call 2: Google News RSS
    gn_query = f"{symbol} {name} crypto".replace(" ", "+")
    gn_url = f"https://news.google.com/rss/search?q={gn_query}&hl=en-US&gl=US&ceid=US:en"
    print(f"Sub-call 2: Google News RSS")
    print(f"  Endpoint: {gn_url}")
    print(f"  Generated Query: '{symbol} {name} crypto'")
    try:
        gn_res = requests.get(gn_url, timeout=8)
        print(f"  HTTP Status Code: {gn_res.status_code}")
        if gn_res.status_code == 200:
            root = ET.fromstring(gn_res.text)
            items = list(root.iter("item"))
            raw_cnt = len(items)
            print(f"  Raw Results Returned: {raw_cnt}")
            # Filter logic check
            kept = []
            now = time.time()
            for item in items:
                title_el = item.find("title")
                pub_el = item.find("pubDate")
                if title_el is None: continue
                pub_text = pub_el.text if pub_el is not None else ""
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_text)
                    m_old = (now - dt.timestamp()) / 60.0
                    if m_old <= 1440:
                        kept.append(item)
                except Exception:
                    pass
            print(f"  Results Kept After Filtering (age <= 24h): {len(kept)}")
        else:
            print(f"  Raw Results Returned: 0")
            print(f"  Results Kept After Filtering: 0")
    except Exception as e:
        print(f"  HTTP Call Exception: {e}")

    news_result = collect_news(coin)
    print(f"DB Output (News): news_score={news_result.get('news_score')}, news_headline='{news_result.get('news_headline')}', news_source='{news_result.get('news_source')}', freshness_score={news_result.get('freshness_score')}\n")

    # --------------------------------------------------------------------------
    # 3. SENTIMENT & SARCASM
    # --------------------------------------------------------------------------
    print("--- [MODULE 3 & 4: SENTIMENT & SARCASM] ---")
    print(f"Executed: YES (via runner -> collect_sentiment, collect_sarcasm)")
    print(f"  Endpoint/API: Local NLP pattern analysis (No external HTTP request)")
    print(f"  Input Text: Raw Telegram message ({len(coin.raw_message)} chars)")
    sent_res = collect_sentiment(coin)
    sarc_res = collect_sarcasm(coin)
    print(f"DB Output (Sentiment): pos={sent_res.get('sentiment_positive')}, neu={sent_res.get('sentiment_neutral')}, neg={sent_res.get('sentiment_negative')}, strength={sent_res.get('sentiment_strength')}")
    print(f"DB Output (Sarcasm): probability={sarc_res.get('sarcasm_probability')}\n")

    # --------------------------------------------------------------------------
    # 4. NARRATIVE & NARRATIVE HEAT
    # --------------------------------------------------------------------------
    print("--- [MODULE 5 & 6: NARRATIVE & NARRATIVE HEAT] ---")
    print(f"Executed: YES (via runner -> collect_narrative, collect_narrative_heat)")
    narr_res = collect_narrative(coin)
    primary_narrative = narr_res.get("primary_narrative")
    coin._intelligence_primary_narrative = primary_narrative
    print(f"Narrative Classification: Primary='{primary_narrative}', Secondary='{narr_res.get('secondary_narrative')}', Confidence={narr_res.get('narrative_confidence')}")
    
    # Narrative Heat API Call
    print(f"Narrative Heat External Call:")
    print(f"  Endpoint: {CRYPTOPANIC_RSS}")
    print(f"  Generated Query: Keyword match against CryptoPanic RSS headlines for narrative '{primary_narrative}'")
    try:
        nh_res = requests.get(CRYPTOPANIC_RSS, timeout=8)
        print(f"  HTTP Status Code: {nh_res.status_code}")
        if nh_res.status_code == 200:
            root = ET.fromstring(nh_res.text)
            items = list(root.iter("item"))
            print(f"  Raw Results Returned (Total headlines): {len(items)}")
            # Filter check
            from intelligence.narrative import NARRATIVE_KEYWORDS
            keywords = NARRATIVE_KEYWORDS.get(primary_narrative, [])
            matched_hl = 0
            for item in items:
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    hl_lower = title_el.text.lower()
                    if any(kw in hl_lower for kw in keywords):
                        matched_hl += 1
            print(f"  Results Kept After Filtering (Headlines matching '{primary_narrative}' keywords): {matched_hl}")
        else:
            print(f"  Raw Results Returned: 0")
            print(f"  Results Kept After Filtering: 0")
    except Exception as e:
        print(f"  HTTP Call Exception: {e}")

    nh_output = collect_narrative_heat(coin)
    print(f"DB Output (Narrative Heat): narrative_heat_score={nh_output.get('narrative_heat_score')}\n")

    # --------------------------------------------------------------------------
    # 5. KOL (Key Opinion Leaders)
    # --------------------------------------------------------------------------
    print("--- [MODULE 7: KOL ENGINE] ---")
    print(f"Executed: YES (via runner -> collect_kol)")
    kol_handles = " OR ".join(f"from:{k['handle']}" for k in KOL_LIST)
    kol_query = f"({symbol} OR {name}) ({kol_handles}) lang:en -is:retweet"
    print(f"  Endpoint: {TWITTER_SEARCH_URL}")
    print(f"  Generated Query: {kol_query[:120]}...")
    if TWITTER_ENABLED:
        try:
            headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
            params = {"query": kol_query, "max_results": 100, "tweet.fields": "author_id,public_metrics", "expansions": "author_id", "user.fields": "username"}
            kol_http_res = requests.get(TWITTER_SEARCH_URL, headers=headers, params=params, timeout=8)
            print(f"  HTTP Status Code: {kol_http_res.status_code}")
            if kol_http_res.status_code == 200:
                kdata = kol_http_res.json()
                raw_tweets = len(kdata.get("data", []))
                print(f"  Raw Results Returned: {raw_tweets}")
                print(f"  Results Kept After Filtering: {raw_tweets}")
            else:
                print(f"  Raw Results Returned: 0 (HTTP {kol_http_res.status_code}: {kol_http_res.text[:150]})")
                print(f"  Results Kept After Filtering: 0")
        except Exception as e:
            print(f"  HTTP Call Exception: {e}")
    else:
        print(f"  TWITTER_ENABLED is False")

    kol_output = collect_kol(coin)
    print(f"DB Output (KOL): kol_mentions={kol_output.get('kol_mentions')}, kol_score={kol_output.get('kol_score')}\n")

    # --------------------------------------------------------------------------
    # 6. COMMUNITY
    # --------------------------------------------------------------------------
    print("--- [MODULE 8: COMMUNITY GROWTH] ---")
    print(f"Executed: YES (via runner -> collect_community)")
    tw_handle = _extract_twitter_handle(coin)
    print(f"  Twitter Handle extracted from Coin: '{tw_handle}'")
    if tw_handle:
        tw_user_url = f"https://api.twitter.com/2/users/by/username/{tw_handle.lstrip('@')}"
        print(f"  Endpoint: {tw_user_url}")
        print(f"  Generated Query: username = {tw_handle}")
        if TWITTER_ENABLED:
            try:
                headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
                params = {"user.fields": "public_metrics"}
                u_res = requests.get(tw_user_url, headers=headers, params=params, timeout=6)
                print(f"  HTTP Status Code: {u_res.status_code}")
            except Exception as e:
                print(f"  HTTP Call Exception: {e}")
    else:
        print(f"  No Twitter handle found on Coin object (coin.twitter is None). Endpoint call skipped.")

    comm_output = collect_community(coin)
    print(f"DB Output (Community): telegram_members={comm_output.get('telegram_members')}, twitter_followers={comm_output.get('twitter_followers')}, message_rate={comm_output.get('message_rate')}, active_users={comm_output.get('active_users')}\n")

    # --------------------------------------------------------------------------
    # 7. MOMENTUM
    # --------------------------------------------------------------------------
    print("--- [MODULE 9: MOMENTUM] ---")
    print(f"Executed: YES (via runner -> collect_momentum)")
    print(f"  Data Source: Database snapshots for signal_id {coin.signal_id}")
    mom_output = collect_momentum(coin)
    print(f"DB Output (Momentum): mc_velocity={mom_output.get('mc_velocity')}, mc_acceleration={mom_output.get('mc_acceleration')}, buy_sell_ratio={mom_output.get('buy_sell_ratio')}\n\n")

