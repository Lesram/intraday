"""
Social Sentiment Analysis Module for Twitter & Reddit with FinBERT.
Fetches social media data and computes sentiment using FinBERT.
"""

import asyncio
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Social media APIs (with fallbacks for development)
try:
    import tweepy

    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False

    class tweepy:
        pass


try:
    import praw

    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False

    class praw:
        pass


# NLP and ML libraries (with fallbacks)
try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    NLP_AVAILABLE = True
except ImportError:
    NLP_AVAILABLE = False

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
        twitter_credentials: Optional[Dict] = None,
        subreddit_list: Optional[List[str]] = None,
        reddit_credentials: Optional[Dict] = None,
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

        # Sentiment data storage (in-memory for now)
        self.sentiment_history = defaultdict(lambda: deque(maxlen=1000))
        self.symbol_mentions = defaultdict(int)
        self.last_update = {}

        # Rate limiting
        self.twitter_rate_limit = 0
        self.reddit_rate_limit = 0

        # Text preprocessing
        self.cashtag_pattern = re.compile(r"\$([A-Z]{1,5})\b")
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

    def _init_twitter(self, credentials: Optional[Dict]):
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
                self.twitter_client = tweepy.Client(
                    bearer_token=credentials["bearer_token"],
                    consumer_key=credentials.get("api_key", ""),
                    consumer_secret=credentials.get("api_secret", ""),
                    access_token=credentials.get("access_token", ""),
                    access_token_secret=credentials.get("access_token_secret", ""),
                )
            else:
                # Fallback to v1.1 API
                self.twitter_client = tweepy.API(auth, wait_on_rate_limit=True)

            # Test connection
            if hasattr(self.twitter_client, "get_me"):
                me = self.twitter_client.get_me()
                self.logger.info("Twitter client initialized", user=me.username)
            else:
                # v1.1 API test
                me = self.twitter_client.verify_credentials()
                self.logger.info("Twitter client initialized", user=me.screen_name)

        except Exception as e:
            self.logger.error("Failed to initialize Twitter client", error=str(e))
            self.twitter_client = None

    def _init_reddit(self, credentials: Optional[Dict]):
        """Initialize Reddit API client."""
        if not PRAW_AVAILABLE:
            self.logger.warning("PRAW not available, Reddit analysis disabled")
            return

        if not credentials:
            self.logger.warning("No Reddit credentials provided")
            return

        try:
            self.reddit_client = praw.Reddit(
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", ""),
                user_agent=credentials.get("user_agent", "SentimentAnalyzer/1.0"),
            )

            # Test connection
            self.reddit_client.auth.limits
            self.logger.info("Reddit client initialized")

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

            self.finbert_pipeline = pipeline(
                "sentiment-analysis",
                model=model_name,
                tokenizer=model_name,
                device=0 if torch.cuda.is_available() else -1,
            )

            self.model_loaded = True
            self.logger.info(
                "FinBERT model loaded successfully",
                model=model_name,
                device="GPU" if torch.cuda.is_available() else "CPU",
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

    def extract_symbols(self, text: str) -> List[str]:
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
        self, symbols: List[str], duration_hours: float = 1.0
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
            end_time = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
            tweet_count = 0

            if hasattr(self.twitter_client, "search_recent_tweets"):
                # Twitter API v2
                while datetime.now(timezone.utc) < end_time:
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

    async def _process_tweet(self, text: str, symbols: List[str]):
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
            timestamp = datetime.now(timezone.utc)

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
        self, symbols: List[str], limit_per_subreddit: int = 50
    ) -> Dict[str, List[Dict]]:
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
    ) -> Optional[Dict[str, Any]]:
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
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            recent_data = [
                d
                for d in self.sentiment_history[symbol]
                if d["timestamp"] >= cutoff_time
            ]

            if len(recent_data) < min_mentions:
                return None

            # Calculate metrics
            sentiments = [d["sentiment"] for d in recent_data]

            # Weighted average (more recent = higher weight)
            now = datetime.now(timezone.utc)
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
                source_stats[source] = {
                    "count": len(sents),
                    "avg_sentiment": np.mean(sents),
                    "std_sentiment": np.std(sents),
                }

            result = {
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc),
                "hours_analyzed": hours_back,
                "total_mentions": len(recent_data),
                "avg_sentiment": np.mean(sentiments),
                "weighted_sentiment": weighted_avg,
                "sentiment_std": np.std(sentiments),
                "positive_ratio": sum(1 for s in sentiments if s > 0.1)
                / len(sentiments),
                "negative_ratio": sum(1 for s in sentiments if s < -0.1)
                / len(sentiments),
                "neutral_ratio": sum(1 for s in sentiments if abs(s) <= 0.1)
                / len(sentiments),
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
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
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

            recent_avg = np.mean([d["sentiment"] for d in recent_half])
            older_avg = np.mean([d["sentiment"] for d in older_half])

            # Momentum is the difference
            momentum = recent_avg - older_avg

            return float(momentum)

        except Exception:
            return 0.0

    def get_sentiment_summary(self, symbols: List[str]) -> Dict[str, Any]:
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
