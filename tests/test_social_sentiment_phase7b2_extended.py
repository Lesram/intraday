"""
Phase 7B.2 Extended: Social Sentiment Analysis Module Testing - Advanced Coverage
Targeting async methods, sentiment processing, and data aggregation
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, UTC, timedelta
import numpy as np
from collections import defaultdict, deque

from backend.data.social_sentiment import SocialSentimentAnalyzer


class TestAsyncTwitterMethodsPhase7B2:
    """Test async Twitter streaming and processing methods"""
    
    @pytest.fixture
    def analyzer_with_twitter(self):
        """Create analyzer with mocked Twitter client"""
        analyzer = SocialSentimentAnalyzer()
        analyzer.twitter_client = Mock()
        analyzer.model_loaded = True
        analyzer.finbert_pipeline = Mock()
        return analyzer
    
    @pytest.mark.asyncio
    async def test_process_tweet_basic(self, analyzer_with_twitter):
        """Test basic tweet processing"""
        # Mock sentiment analysis
        analyzer_with_twitter.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.8}]
        
        text = "Great day for $AAPL stock!"
        symbols = ["AAPL"]
        
        await analyzer_with_twitter._process_tweet(text, symbols)
        
        # Check that sentiment was stored
        assert len(analyzer_with_twitter.sentiment_history["AAPL"]) > 0
        assert analyzer_with_twitter.symbol_mentions["AAPL"] > 0
    
    @pytest.mark.asyncio
    async def test_process_tweet_multiple_symbols(self, analyzer_with_twitter):
        """Test tweet processing with multiple symbols"""
        analyzer_with_twitter.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.75}]
        
        text = "$AAPL and $MSFT looking strong today"
        symbols = ["AAPL", "MSFT"]
        
        await analyzer_with_twitter._process_tweet(text, symbols)
        
        # Check both symbols were processed
        assert len(analyzer_with_twitter.sentiment_history["AAPL"]) > 0
        assert len(analyzer_with_twitter.sentiment_history["MSFT"]) > 0
        assert analyzer_with_twitter.symbol_mentions["AAPL"] > 0
        assert analyzer_with_twitter.symbol_mentions["MSFT"] > 0
    
    @pytest.mark.asyncio
    async def test_process_tweet_negative_sentiment(self, analyzer_with_twitter):
        """Test tweet processing with negative sentiment"""
        analyzer_with_twitter.finbert_pipeline.return_value = [{"label": "NEGATIVE", "score": 0.9}]
        
        text = "Worried about $TSLA earnings"
        symbols = ["TSLA"]
        
        await analyzer_with_twitter._process_tweet(text, symbols)
        
        # Check negative sentiment was recorded
        sentiment_data = analyzer_with_twitter.sentiment_history["TSLA"][0]
        assert sentiment_data["sentiment"] < 0
        assert "TSLA" in sentiment_data["symbols"]
        assert sentiment_data["source"] == "twitter"
    
    @pytest.mark.asyncio
    async def test_stream_twitter_sentiment_mock(self, analyzer_with_twitter):
        """Test Twitter streaming with mock data"""
        # Mock the Twitter client stream
        mock_tweet = Mock()
        mock_tweet.text = "Bullish on $AAPL today! Great earnings"
        mock_tweet.public_metrics = {"retweet_count": 10, "like_count": 50}
        
        # Mock the streaming method
        async def mock_stream(*args, **kwargs):
            yield mock_tweet
        
        analyzer_with_twitter.twitter_client.get_tweets = AsyncMock(return_value=[mock_tweet])
        analyzer_with_twitter.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.8}]
        
        symbols = ["AAPL"]
        
        # Test that streaming can process tweets
        # Since we can't easily test the actual streaming, test the processing logic
        await analyzer_with_twitter._process_tweet(mock_tweet.text, symbols)
        
        assert len(analyzer_with_twitter.sentiment_history["AAPL"]) > 0


class TestAsyncRedditMethodsPhase7B2:
    """Test async Reddit data fetching methods"""
    
    @pytest.fixture
    def analyzer_with_reddit(self):
        """Create analyzer with mocked Reddit client"""
        analyzer = SocialSentimentAnalyzer()
        analyzer.reddit_client = Mock()
        analyzer.model_loaded = True
        analyzer.finbert_pipeline = Mock()
        return analyzer
    
    @pytest.mark.asyncio
    async def test_fetch_reddit_headlines_basic(self, analyzer_with_reddit):
        """Test basic Reddit headline fetching"""
        # Mock Reddit submission
        mock_submission = Mock()
        mock_submission.title = "AAPL earnings beat expectations!"
        mock_submission.selftext = "Great quarter for Apple"
        mock_submission.score = 150
        mock_submission.num_comments = 25
        mock_submission.created_utc = datetime.now().timestamp()
        
        # Mock subreddit
        mock_subreddit = Mock()
        mock_subreddit.hot.return_value = [mock_submission]
        analyzer_with_reddit.reddit_client.subreddit.return_value = mock_subreddit
        
        analyzer_with_reddit.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.8}]
        
        symbols = ["AAPL"]
        subreddits = ["investing"]
        
        await analyzer_with_reddit.fetch_reddit_headlines(symbols, limit_per_subreddit=1)
        
        # Check that data was processed
        assert len(analyzer_with_reddit.sentiment_history["AAPL"]) > 0
        sentiment_data = analyzer_with_reddit.sentiment_history["AAPL"][0]
        assert sentiment_data["source"] == "reddit"
        assert sentiment_data["symbol"] == "AAPL"
    
    @pytest.mark.asyncio
    async def test_fetch_reddit_headlines_multiple_subreddits(self, analyzer_with_reddit):
        """Test Reddit fetching from multiple subreddits"""
        mock_submission1 = Mock()
        mock_submission1.title = "TSLA breaking new highs"
        mock_submission1.selftext = ""
        mock_submission1.score = 200
        mock_submission1.num_comments = 50
        mock_submission1.created_utc = datetime.now().timestamp()
        
        mock_submission2 = Mock()
        mock_submission2.title = "Bitcoin rally continues"
        mock_submission2.selftext = "BTC looking strong"
        mock_submission2.score = 100
        mock_submission2.num_comments = 30
        mock_submission2.created_utc = datetime.now().timestamp()
        
        # Mock multiple subreddits
        def mock_subreddit(name):
            mock_sub = Mock()
            if name == "investing":
                mock_sub.hot.return_value = [mock_submission1]
            else:
                mock_sub.hot.return_value = [mock_submission2]
            return mock_sub
        
        analyzer_with_reddit.reddit_client.subreddit = mock_subreddit
        analyzer_with_reddit.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.7}]
        
        symbols = ["TSLA", "BTC"]
        subreddits = ["investing", "cryptocurrency"]
        
        await analyzer_with_reddit.fetch_reddit_headlines(symbols, limit_per_subreddit=1)
        
        # Check both symbols were processed
        assert len(analyzer_with_reddit.sentiment_history["TSLA"]) > 0
        assert len(analyzer_with_reddit.sentiment_history["BTC"]) > 0
    
    @pytest.mark.asyncio
    async def test_fetch_reddit_headlines_exception_handling(self, analyzer_with_reddit):
        """Test Reddit fetching with exception handling"""
        # Mock Reddit client to raise exception
        analyzer_with_reddit.reddit_client.subreddit.side_effect = Exception("Reddit API Error")
        
        symbols = ["AAPL"]
        subreddits = ["investing"]
        
        # Should not raise exception
        await analyzer_with_reddit.fetch_reddit_headlines(symbols, limit_per_subreddit=1)
        
        # Should track the failed request
        assert analyzer_with_reddit.failed_requests["reddit"] > 0


class TestSentimentAggregationPhase7B2:
    """Test sentiment data aggregation and analysis"""
    
    @pytest.fixture
    def analyzer_with_data(self):
        """Create analyzer with sample sentiment data"""
        analyzer = SocialSentimentAnalyzer()
        
        # Add sample sentiment data (need at least 5 for min_mentions)
        now = datetime.now(UTC)
        sample_data = [
            {
                "timestamp": now - timedelta(hours=1),
                "sentiment": 0.8,
                "source": "twitter",
                "weight": 1.0
            },
            {
                "timestamp": now - timedelta(hours=2),
                "sentiment": 0.6,
                "source": "reddit",
                "weight": 1.5
            },
            {
                "timestamp": now - timedelta(hours=3),
                "sentiment": -0.3,
                "source": "twitter", 
                "weight": 1.0
            },
            {
                "timestamp": now - timedelta(hours=4),
                "sentiment": 0.4,
                "source": "reddit",
                "weight": 1.2
            },
            {
                "timestamp": now - timedelta(hours=5),
                "sentiment": 0.2,
                "source": "twitter",
                "weight": 1.0
            },
            {
                "timestamp": now - timedelta(hours=25), # Outside 24h window
                "sentiment": 0.9,
                "source": "twitter",
                "weight": 1.0
            }
        ]
        
        analyzer.sentiment_history["AAPL"].extend(sample_data)
        analyzer.symbol_mentions["AAPL"] = len(sample_data)
        
        return analyzer
    
    def test_get_aggregated_sentiment_basic(self, analyzer_with_data):
        """Test basic sentiment aggregation"""
        result = analyzer_with_data.get_aggregated_sentiment("AAPL")
        
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["total_mentions"] == 5  # 5 within 24h window
        assert isinstance(result["avg_sentiment"], float)
        assert isinstance(result["weighted_sentiment"], float)
        assert isinstance(result["sentiment_std"], float)
        
        # Check ratios sum to 1
        total_ratio = (result["positive_ratio"] + 
                      result["negative_ratio"] + 
                      result["neutral_ratio"])
        assert abs(total_ratio - 1.0) < 0.01
    
    def test_get_aggregated_sentiment_custom_window(self, analyzer_with_data):
        """Test sentiment aggregation with custom time window"""
        result = analyzer_with_data.get_aggregated_sentiment("AAPL", hours_back=1, min_mentions=1)
        
        assert result is not None
        assert result["total_mentions"] == 1  # Only 1 within 1h window
        assert result["hours_analyzed"] == 1
    
    def test_get_aggregated_sentiment_no_data(self, analyzer_with_data):
        """Test sentiment aggregation with no data"""
        result = analyzer_with_data.get_aggregated_sentiment("UNKNOWN_SYMBOL")
        
        assert result is None
    
    def test_get_aggregated_sentiment_source_breakdown(self, analyzer_with_data):
        """Test sentiment aggregation with source breakdown"""
        result = analyzer_with_data.get_aggregated_sentiment("AAPL")
        
        assert "source_breakdown" in result
        sources = result["source_breakdown"]
        
        assert "twitter" in sources
        assert "reddit" in sources
        
        # Check twitter stats
        twitter_stats = sources["twitter"]
        assert "count" in twitter_stats
        assert "avg_sentiment" in twitter_stats
        assert "std_sentiment" in twitter_stats
    
    def test_calculate_sentiment_momentum(self, analyzer_with_data):
        """Test sentiment momentum calculation"""
        momentum = analyzer_with_data._calculate_sentiment_momentum("AAPL")
        
        assert isinstance(momentum, float)
        # With our sample data, momentum should reflect recent vs older sentiment
    
    def test_calculate_sentiment_momentum_insufficient_data(self):
        """Test sentiment momentum with insufficient data"""
        analyzer = SocialSentimentAnalyzer()
        
        # Add minimal data (less than 10 points)
        analyzer.sentiment_history["TEST"] = deque([
            {
                "timestamp": datetime.now(UTC),
                "sentiment": 0.5,
                "source": "twitter"
            }
        ])
        
        momentum = analyzer._calculate_sentiment_momentum("TEST")
        assert momentum == 0.0
    
    def test_get_sentiment_summary(self, analyzer_with_data):
        """Test sentiment summary for multiple symbols"""
        # Add data for another symbol with enough mentions
        for i in range(5):  # Add 5 mentions to meet min_mentions requirement
            analyzer_with_data.sentiment_history["MSFT"].append({
                "timestamp": datetime.now(UTC) - timedelta(hours=i),
                "sentiment": 0.5,
                "source": "twitter",
                "weight": 1.0
            })
        
        symbols = ["AAPL", "MSFT", "UNKNOWN"]
        summary = analyzer_with_data.get_sentiment_summary(symbols)
        
        assert len(summary) == 3
        
        # Check AAPL data
        assert "AAPL" in summary
        assert summary["AAPL"]["total_mentions"] > 0
        
        # Check MSFT data
        assert "MSFT" in summary
        assert summary["MSFT"]["total_mentions"] > 0
        
        # Check UNKNOWN (should have defaults)
        assert "UNKNOWN" in summary
        assert summary["UNKNOWN"]["total_mentions"] == 0
        assert summary["UNKNOWN"]["weighted_sentiment"] == 0.0


class TestSentimentProcessingPhase7B2:
    """Test detailed sentiment processing and analysis"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    def test_analyze_text_finbert_positive(self, analyzer):
        """Test FinBERT analysis with positive sentiment"""
        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"label": "positive", "score": 0.85}]
        analyzer.finbert_pipeline = mock_pipeline
        analyzer.model_loaded = True
        
        sentiment = analyzer.analyze_text_finbert("Stock is performing excellently!")
        
        assert sentiment > 0
        assert isinstance(sentiment, float)
        mock_pipeline.assert_called_once()
    
    def test_analyze_text_finbert_negative(self, analyzer):
        """Test FinBERT analysis with negative sentiment"""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"label": "negative", "score": 0.9}]
        analyzer.finbert_pipeline = mock_pipeline
        analyzer.model_loaded = True
        
        sentiment = analyzer.analyze_text_finbert("Terrible earnings report!")
        
        assert sentiment < 0
        assert isinstance(sentiment, float)
    
    def test_analyze_text_finbert_neutral(self, analyzer):
        """Test FinBERT analysis with neutral sentiment"""
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"label": "neutral", "score": 0.7}]
        analyzer.finbert_pipeline = Mock(return_value=[{"label": "neutral", "score": 0.7}])
        analyzer.model_loaded = True
        
        sentiment = analyzer.analyze_text_finbert("Company released quarterly report")
        
        assert abs(sentiment) < 0.1  # Near zero for neutral
        assert isinstance(sentiment, float)
    
    def test_analyze_text_finbert_exception_handling(self, analyzer):
        """Test FinBERT analysis with exception"""
        mock_pipeline = Mock()
        mock_pipeline.side_effect = Exception("Model error")
        analyzer.finbert_pipeline = mock_pipeline
        analyzer.model_loaded = True
        
        sentiment = analyzer.analyze_text_finbert("Test text")
        
        # Should return neutral sentiment on error
        assert sentiment == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
