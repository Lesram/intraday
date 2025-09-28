"""
Social Sentiment Analysis Module for Twitter & Reddit with FinBERT.
Fetches social media data and computes sentiment using FinBERT.
"""

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
import os
import re
import time
from typing import Any

# Centralized DISABLE_ML check for test mode
DISABLE_ML = os.environ.get("DISABLE_ML", "0") == "1"

# Import real numpy - it's lightweight and needed
import numpy as np

# Social media APIs (with fallbacks for development)
try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False

    class _DummyOAuthHandler:
        def __init__(self, *args, **kwargs):
            pass
        def set_access_token(self, *args, **kwargs):
            pass

    class _DummyAPI:
        def __init__(self, *args, **kwargs):
            pass
        def verify_credentials(self):
            return type("_User", (), {"screen_name": "dummy"})()

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            pass
        def get_me(self):
            return type("_User", (), {"username": "dummy"})()

    class tweepy:  # type: ignore
        OAuthHandler = _DummyOAuthHandler
        API = _DummyAPI
        Client = _DummyClient


try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

    class _DummyReddit:
        def __init__(self, *args, **kwargs):
            self.user = type("_U", (), {"me": lambda self: type("_Me", (), {})()})()
            self.auth = type("_A", (), {"limits": {}})()
        def subreddit(self, name):
            class _Sub:
                def hot(self, limit=50):
                    return []
            return _Sub()

    class praw:  # type: ignore
        Reddit = _DummyReddit


# NLP and ML libraries (with fallbacks) - Skip during testing to prevent hangs
NLP_AVAILABLE = False
if not DISABLE_ML and not os.environ.get('DISABLE_TORCH') and not os.environ.get('DISABLE_TRANSFORMERS') and not os.environ.get('PYTEST_RUNNING'):
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
        NLP_AVAILABLE = True
    except ImportError:
        NLP_AVAILABLE = False

# Fallback classes when imports are disabled
if not NLP_AVAILABLE:
    class pipeline:
        pass


from ..utils.helpers import hash_string
from ..utils.logger import get_structured_logger, performance_logger


class SocialSentimentAnalyzer:
    """
    Social sentiment analyzer using Twitter, Reddit, and FinBERT.
    Aggregates sentiment from multiple sources for trading signals.
    """

    def __init__(
        self,
        twitter_credentials: dict | None = None,
        subreddit_list: list[str] | None = None,
        reddit_credentials: dict | None = None,
    ):
        """
        Initialize with API credentials and target subreddits.

        Args:
            twitter_credentials: Dict with Twitter API credentials
            subreddit_list: List of subreddits to monitor
            reddit_credentials: Dict with Reddit API credentials
        """
        self.logger = get_structured_logger("social_sentiment")

        # API clients
        self.twitter_client = None
        self.reddit_client = None

        # FinBERT model
        self.finbert_pipeline = None
        self.model_loaded = False

        # Configuration
        self.subreddit_list = subreddit_list or [
            "StockMarket",
            "investing",
            "wallstreetbets",
            "cryptocurrency",
            "Bitcoin",
            "ethtrader",
        ]

        # Rate limiting and circuit breaker configuration
        self.request_timeout = 10  # seconds
        self.max_retries = 3
        self.retry_delay = 1.0  # seconds between retries
        self.circuit_breaker_threshold = 5  # failures before opening circuit
        self.circuit_breaker_cooldown = 300  # 5 minutes cooldown
        self.circuit_open_until = {}  # Track when circuits should close

        # Sentiment data storage (in-memory for now)
        # Use lazy maps that do NOT persist keys upon read access, but DO persist on first mutation.
        class _WriteBackDeque(deque):
            """A deque that writes itself back into a parent mapping upon first mutation.

            This preserves memory efficiency (mere reads don't persist), while allowing
            analyzer.sentiment_history[sym].append(...) to create a persistent entry.
            """
            def __init__(self, parent_map: dict, parent_key: str, maxlen: int | None = None):
                self._parent_map = parent_map
                self._parent_key = parent_key
                self._persisted = False
                super().__init__(maxlen=maxlen)

            def _ensure_persisted(self):
                if not self._persisted:
                    # Insert self into the parent map so subsequent access returns the same deque
                    self._parent_map[self._parent_key] = self
                    self._persisted = True

            # Mutating operations should trigger persistence
            def append(self, x):
                self._ensure_persisted()
                return super().append(x)

            def appendleft(self, x):
                self._ensure_persisted()
                return super().appendleft(x)

            def clear(self):
                self._ensure_persisted()
                return super().clear()

            def extend(self, iterable):
                self._ensure_persisted()
                return super().extend(iterable)

            def extendleft(self, iterable):
                self._ensure_persisted()
                return super().extendleft(iterable)

            def insert(self, i, x):
                self._ensure_persisted()
                return super().insert(i, x)

            def pop(self):
                self._ensure_persisted()
                return super().pop()

            def popleft(self):
                self._ensure_persisted()
                return super().popleft()

            def remove(self, value):
                self._ensure_persisted()
                return super().remove(value)

            def rotate(self, n=1):
                self._ensure_persisted()
                return super().rotate(n)

        class _LazyDefaultDict(defaultdict):
            def __missing__(self, key):
                # Return a fresh default value but DO NOT set the key
                return self.default_factory() if self.default_factory else None
            def __getitem__(self, key):  # maintain convenient access pattern in tests
                if key in self:
                    return super().__getitem__(key)
                # If default is a deque, return a write-back wrapper that persists on mutation
                if self.default_factory:
                    tmp = self.default_factory()
                    if isinstance(tmp, deque):
                        # Try to preserve maxlen if provided
                        maxlen = getattr(tmp, 'maxlen', None)
                        return _WriteBackDeque(self, key, maxlen=maxlen)
                    return tmp
                return None

        self.sentiment_history = _LazyDefaultDict(lambda: deque(maxlen=1000))
        self.symbol_mentions = _LazyDefaultDict(int)
        self.last_update = {}
        self.failed_requests = defaultdict(int)  # Track failures per source

        # Rate limiting
        self.twitter_rate_limit = 0
        self.reddit_rate_limit = 0

        # Text preprocessing
        # Require at least 2 characters to avoid matching "$A" as a ticker
        self.cashtag_pattern = re.compile(r"\$([A-Z]{2,5})\b")
        self.crypto_pattern = re.compile(
            r"\b(BTC|ETH|ADA|DOT|LINK|UNI|DOGE)\b", re.IGNORECASE
        )

        # Initialize APIs
        self._init_twitter(twitter_credentials)
        self._init_reddit(reddit_credentials)
        self._init_finbert()

        self.logger.info(
            "Social sentiment analyzer initialized",
            twitter_enabled=self.twitter_client is not None,
            reddit_enabled=self.reddit_client is not None,
            finbert_enabled=self.model_loaded,
        )

    # Explicit mutators for structures to ensure keys persist only on write
    def add_sentiment_record(self, symbol: str, record: dict[str, Any]) -> None:
        dq = self.sentiment_history.get(symbol)
        if dq is None:
            dq = deque(maxlen=1000)
        dq.append(record)
        # Persist only when adding data
        self.sentiment_history[symbol] = dq

    def increment_symbol_mention(self, symbol: str, amount: int = 1) -> None:
        current = self.symbol_mentions.get(symbol, 0)
        current += int(amount)
        # Persist only when incrementing
        self.symbol_mentions[symbol] = current

    def _init_twitter(self, credentials: dict | None):
        """Initialize Twitter API client."""
        if not TWEEPY_AVAILABLE:
            self.logger.warning("Tweepy not available, Twitter analysis disabled")
            return

        if not credentials:
            self.logger.warning("No Twitter credentials provided")
            return

        try:
            auth = tweepy.OAuthHandler(
                credentials.get("api_key", ""), credentials.get("api_secret", "")
            )

            if "access_token" in credentials and "access_token_secret" in credentials:
                auth.set_access_token(
                    credentials["access_token"], credentials["access_token_secret"]
                )

            # Try using Bearer token if available (v2 API)
            if "bearer_token" in credentials:
                client = tweepy.Client(
                    bearer_token=credentials["bearer_token"],
                    consumer_key=credentials.get("api_key", ""),
                    consumer_secret=credentials.get("api_secret", ""),
                    access_token=credentials.get("access_token", ""),
                    access_token_secret=credentials.get("access_token_secret", ""),
                )
                # Test connection
                try:
                    if hasattr(client, "get_me"):
                        me = client.get_me()
                        _ = getattr(me, "username", None)  # access to ensure structure
                except Exception:
                    client = None
                self.twitter_client = client
            else:
                # Fallback to v1.1 API
                api = tweepy.API(auth, wait_on_rate_limit=True)
                # Test connection and set None if it fails
                try:
                    _ = api.verify_credentials()
                    self.twitter_client = api
                except Exception:
                    self.twitter_client = None

        except Exception as e:
            self.logger.error("Failed to initialize Twitter client", error=str(e))
            self.twitter_client = None

    def _init_reddit(self, credentials: dict | None):
        """Initialize Reddit API client."""
        if not PRAW_AVAILABLE:
            self.logger.warning("PRAW not available, Reddit analysis disabled")
            return

        if not credentials:
            self.logger.warning("No Reddit credentials provided")
            return

        try:
            reddit = praw.Reddit(
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", ""),
                user_agent=credentials.get("user_agent", "SentimentAnalyzer/1.0"),
            )
            # Test connection
            try:
                # Access a property/method to validate credentials
                _ = reddit.user.me()
                self.reddit_client = reddit
                self.logger.info("Reddit client initialized")
            except Exception:
                self.reddit_client = None

        except Exception as e:
            self.logger.error("Failed to initialize Reddit client", error=str(e))
            self.reddit_client = None

    def _init_finbert(self):
        """Initialize FinBERT model for sentiment analysis."""
        if not NLP_AVAILABLE:
            self.logger.warning("Transformers not available, using mock sentiment")
            return

        try:
            # Load FinBERT model specifically trained for financial sentiment
            model_name = "ProsusAI/finbert"

            if NLP_AVAILABLE:
                device_id = 0 if hasattr(torch, 'cuda') and torch.cuda.is_available() else -1
                device_name = "GPU" if hasattr(torch, 'cuda') and torch.cuda.is_available() else "CPU"
            else:
                device_id = -1
                device_name = "CPU"

            self.finbert_pipeline = pipeline(
                "sentiment-analysis",
                model=model_name,
                tokenizer=model_name,
                device=device_id,
            )

            self.model_loaded = True
            self.logger.info(
                "FinBERT model loaded successfully",
                model=model_name,
                device=device_name,
            )

        except Exception as e:
            self.logger.error("Failed to load FinBERT model", error=str(e))
            # Fallback to basic sentiment
            try:
                self.finbert_pipeline = pipeline(
                    "sentiment-analysis",
                    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                )
                self.model_loaded = True
                self.logger.info("Loaded fallback sentiment model")
            except Exception as e2:
                self.logger.error("Failed to load any sentiment model", error=str(e2))
                self.model_loaded = False

    def analyze_text_finbert(self, text: str) -> float:
        """
        Analyze a piece of text using FinBERT and return sentiment score.

        Args:
            text: Text to analyze

        Returns:
            Sentiment score from -1 (negative) to +1 (positive)
        """
        if not self.model_loaded or not text.strip():
            return 0.0

        try:
            # Clean and truncate text
            cleaned_text = self._clean_text(text)
            if len(cleaned_text) < 10:  # Too short to be meaningful
                return 0.0

            # Truncate to model's max length (usually 512 tokens)
            if len(cleaned_text) > 500:
                cleaned_text = cleaned_text[:500]

            # Get prediction
            start_time = time.time()
            result = self.finbert_pipeline(cleaned_text)
            inference_time = (time.time() - start_time) * 1000

            # Log performance
            performance_logger.log_latency("finbert_inference", inference_time)

            # Convert to numeric score
            if isinstance(result, list) and len(result) > 0:
                prediction = result[0]
                label = prediction.get("label", "").upper()
                score = prediction.get("score", 0.5)

                # Convert to -1 to +1 scale
                if "POSITIVE" in label or "POS" in label:
                    return float(score)
                elif "NEGATIVE" in label or "NEG" in label:
                    return float(-score)
                else:  # NEUTRAL
                    return 0.0

            return 0.0

        except Exception as e:
            self.logger.error(
                "FinBERT analysis failed", text_length=len(text), error=str(e)
            )
            return 0.0

    def _clean_text(self, text: str) -> str:
        """Clean and preprocess text for sentiment analysis."""
        if not text:
            return ""

        # Remove URLs
        text = re.sub(
            r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            "",
            text,
        )

        # Remove user mentions and hashtags (but keep cashtags)
        text = re.sub(r"@\w+", "", text)
        text = re.sub(r"#(?!\$)", "", text)

        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove emojis (basic cleanup)
        text = re.sub(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]",
            "",
            text,
        )

        return text.strip()

    def extract_symbols(self, text: str) -> list[str]:
        """Extract stock symbols and crypto mentions from text."""
        symbols = []

        # Extract cashtags ($AAPL, $MSFT, etc.)
        cashtags = self.cashtag_pattern.findall(text.upper())
        symbols.extend(cashtags)

        # Extract crypto symbols
        crypto_matches = self.crypto_pattern.findall(text)
        symbols.extend([c.upper() for c in crypto_matches])

        return list(set(symbols))  # Remove duplicates

    async def stream_twitter_sentiment(
        self, symbols: list[str], duration_hours: float = 1.0
    ):
        """
        Continuously stream tweets for given symbols and compute sentiment.

        Args:
            symbols: List of symbols to track
            duration_hours: How long to stream (hours)
        """
        if not self.twitter_client:
            self.logger.warning("Twitter client not available")
            return

        try:
            # Create query for symbols
            symbol_queries = []
            for symbol in symbols:
                if "/" not in symbol:  # Stock symbol
                    symbol_queries.append(f"${symbol}")
                else:  # Crypto pair
                    base = symbol.split("/")[0]
                    symbol_queries.append(base)

            query = " OR ".join(symbol_queries)

            self.logger.info(
                "Starting Twitter stream", query=query, duration_hours=duration_hours
            )

            # Stream tweets
            end_time = datetime.now(UTC) + timedelta(hours=duration_hours)
            tweet_count = 0

            if hasattr(self.twitter_client, "search_recent_tweets"):
                # Twitter API v2
                while datetime.now(UTC) < end_time:
                    try:
                        tweets = self.twitter_client.search_recent_tweets(
                            query=query,
                            max_results=100,
                            tweet_fields=["created_at", "public_metrics"],
                        )

                        if tweets.data:
                            for tweet in tweets.data:
                                await self._process_tweet(tweet.text, symbols)
                                tweet_count += 1

                        # Wait before next batch
                        await asyncio.sleep(60)  # 1 minute between batches

                    except Exception as e:
                        self.logger.error("Twitter streaming error", error=str(e))
                        await asyncio.sleep(300)  # 5 minute backoff
            else:
                # Twitter API v1.1 fallback
                tweets = tweepy.Cursor(
                    self.twitter_client.search_tweets,
                    q=query,
                    lang="en",
                    tweet_mode="extended",
                ).items(1000)

                for tweet in tweets:
                    await self._process_tweet(tweet.full_text, symbols)
                    tweet_count += 1

            self.logger.info(
                "Twitter streaming completed", tweets_processed=tweet_count
            )

        except Exception as e:
            self.logger.error("Twitter streaming failed", error=str(e))

    async def _process_tweet(self, text: str, symbols: list[str]):
        """Process individual tweet for sentiment."""
        try:
            # Extract mentioned symbols
            mentioned_symbols = self.extract_symbols(text)

            # Filter to tracked symbols
            relevant_symbols = [s for s in mentioned_symbols if s in symbols]

            if not relevant_symbols:
                return

            # Analyze sentiment
            sentiment = self.analyze_text_finbert(text)
            timestamp = datetime.now(UTC)

            # Store sentiment for each relevant symbol
            for symbol in relevant_symbols:
                sentiment_data = {
                    "timestamp": timestamp,
                    "source": "twitter",
                    "text_hash": hash_string(text),
                    "sentiment": sentiment,
                    "symbols": relevant_symbols,
                }

                self.sentiment_history[symbol].append(sentiment_data)
                self.symbol_mentions[symbol] += 1

        except Exception as e:
            self.logger.error("Tweet processing failed", error=str(e))

    async def fetch_reddit_headlines(
        self, symbols: list[str], limit_per_subreddit: int = 50
    ) -> dict[str, list[dict]]:
        """
        Fetch latest subreddit posts and compute sentiment scores.

        Args:
            symbols: Symbols to track
            limit_per_subreddit: Maximum posts per subreddit

        Returns:
            Dictionary of sentiment data by symbol
        """
        if not self.reddit_client:
            self.logger.warning("Reddit client not available")
            return {}

        try:
            results = defaultdict(list)
            total_posts = 0

            for subreddit_name in self.subreddit_list:
                try:
                    subreddit = self.reddit_client.subreddit(subreddit_name)

                    # Get hot posts
                    posts = list(subreddit.hot(limit=limit_per_subreddit))

                    for post in posts:
                        # Combine title and selftext
                        text = f"{post.title} {post.selftext or ''}"

                        # Extract relevant symbols
                        mentioned_symbols = self.extract_symbols(text)
                        relevant_symbols = [
                            s for s in mentioned_symbols if s in symbols
                        ]

                        if not relevant_symbols:
                            continue

                        # Analyze sentiment
                        sentiment = self.analyze_text_finbert(text)

                        post_data = {
                            "timestamp": datetime.fromtimestamp(post.created_utc),
                            "source": f"reddit_{subreddit_name}",
                            "title": post.title,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "sentiment": sentiment,
                            "symbols": relevant_symbols,
                            "url": post.url,
                        }

                        # Store for each symbol
                        for symbol in relevant_symbols:
                            results[symbol].append(post_data)
                            self.sentiment_history[symbol].append(
                                {
                                    "timestamp": post_data["timestamp"],
                                    "source": f"reddit_{subreddit_name}",
                                    "text_hash": hash_string(text),
                                    "sentiment": sentiment,
                                    "symbols": relevant_symbols,
                                    "engagement": post.score + post.num_comments,
                                }
                            )

                        total_posts += 1

                    # Rate limiting
                    await asyncio.sleep(1)

                except Exception as e:
                    self.logger.error(
                        "Failed to process subreddit",
                        subreddit=subreddit_name,
                        error=str(e),
                    )
                    continue

            self.logger.info(
                "Reddit data fetched",
                posts_processed=total_posts,
                symbols_found=len(results),
            )

            return dict(results)

        except Exception as e:
            self.logger.error("Reddit fetching failed", error=str(e))
            return {}

    def get_aggregated_sentiment(
        self, symbol: str, hours_back: int = 24, min_mentions: int = 5
    ) -> dict[str, Any] | None:
        """
        Return current aggregated sentiment score for a symbol.

        Args:
            symbol: Symbol to analyze
            hours_back: Hours of history to consider
            min_mentions: Minimum mentions required

        Returns:
            Dictionary with sentiment metrics or None
        """
        try:
            if symbol not in self.sentiment_history:
                return None

            # Filter recent data
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours_back)
            recent_data = [
                d
                for d in self.sentiment_history[symbol]
                if d["timestamp"] >= cutoff_time
            ]

            if len(recent_data) < min_mentions:
                return None

            # Calculate metrics (sanitize non-finite)
            sentiments = [d["sentiment"] for d in recent_data]
            sentiments = [s for s in sentiments if np.isfinite(s)]
            if not sentiments:
                return None

            # Weighted average (more recent = higher weight)
            now = datetime.now(UTC)
            weighted_sum = 0
            total_weight = 0

            for data in recent_data:
                age_hours = (now - data["timestamp"]).total_seconds() / 3600
                weight = max(0.1, 1.0 - (age_hours / hours_back))  # Linear decay

                # Higher weight for posts with more engagement
                if "engagement" in data:
                    weight *= min(3.0, 1.0 + data["engagement"] / 100)

                weighted_sum += data["sentiment"] * weight
                total_weight += weight

            weighted_avg = weighted_sum / total_weight if total_weight > 0 else 0

            # Source breakdown
            sources = defaultdict(list)
            for d in recent_data:
                sources[d["source"]].append(d["sentiment"])

            source_stats = {}
            for source, sents in sources.items():
                clean_sents = [s for s in sents if np.isfinite(s)]
                source_stats[source] = {
                    "count": len(clean_sents),
                    "avg_sentiment": float(np.mean(clean_sents)) if clean_sents else 0.0,
                    "std_sentiment": float(np.std(clean_sents)) if clean_sents else 0.0,
                }

            result = {
                "symbol": symbol,
                "timestamp": datetime.now(UTC),
                "hours_analyzed": hours_back,
                "total_mentions": len(recent_data),
                "avg_sentiment": float(np.mean(sentiments)),
                "weighted_sentiment": weighted_avg,
                "sentiment_std": float(np.std(sentiments)),
                "positive_ratio": (sum(1 for s in sentiments if s > 0.1) / len(sentiments)) if sentiments else 0.0,
                "negative_ratio": (sum(1 for s in sentiments if s < -0.1) / len(sentiments)) if sentiments else 0.0,
                "neutral_ratio": (sum(1 for s in sentiments if abs(s) <= 0.1) / len(sentiments)) if sentiments else 0.0,
                "source_breakdown": source_stats,
                "momentum": self._calculate_sentiment_momentum(symbol, hours_back),
            }

            self.logger.info(
                "Sentiment aggregated",
                symbol=symbol,
                mentions=len(recent_data),
                weighted_sentiment=weighted_avg,
            )

            return result

        except Exception as e:
            self.logger.error(
                "Sentiment aggregation failed", symbol=symbol, error=str(e)
            )
            return None

    def _calculate_sentiment_momentum(self, symbol: str, hours_back: int = 24) -> float:
        """Calculate sentiment momentum (recent vs older sentiment)."""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=hours_back)
            recent_data = [
                d
                for d in self.sentiment_history[symbol]
                if d["timestamp"] >= cutoff_time
            ]

            if len(recent_data) < 10:
                return 0.0

            # Split into recent vs older
            mid_point = len(recent_data) // 2
            recent_half = recent_data[mid_point:]  # More recent
            older_half = recent_data[:mid_point]  # Older

            recent_vals = [d["sentiment"] for d in recent_half]
            older_vals = [d["sentiment"] for d in older_half]
            recent_vals = [s for s in recent_vals if np.isfinite(s)]
            older_vals = [s for s in older_vals if np.isfinite(s)]
            if not recent_vals or not older_vals:
                return 0.0
            recent_avg = np.mean(recent_vals)
            older_avg = np.mean(older_vals)

            # Momentum is the difference
            momentum = recent_avg - older_avg

            return float(momentum)

        except Exception:
            return 0.0

    def get_sentiment_summary(self, symbols: list[str]) -> dict[str, Any]:
        """Get sentiment summary for multiple symbols."""
        summary = {}

        for symbol in symbols:
            sentiment_data = self.get_aggregated_sentiment(symbol)
            if sentiment_data:
                summary[symbol] = {
                    "weighted_sentiment": sentiment_data["weighted_sentiment"],
                    "total_mentions": sentiment_data["total_mentions"],
                    "momentum": sentiment_data["momentum"],
                    "positive_ratio": sentiment_data["positive_ratio"],
                }
            else:
                summary[symbol] = {
                    "weighted_sentiment": 0.0,
                    "total_mentions": 0,
                    "momentum": 0.0,
                    "positive_ratio": 0.5,
                }

        return summary
