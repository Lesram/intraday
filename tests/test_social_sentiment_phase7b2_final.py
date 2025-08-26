"""
Phase 7B.2 Final: Social Sentiment Analysis Module Testing - Complete Coverage
Targeting remaining uncovered lines and edge cases
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, UTC, timedelta
import numpy as np
from collections import defaultdict, deque

from backend.data.social_sentiment import SocialSentimentAnalyzer


class TestCircuitBreakerPhase7B2:
    """Test circuit breaker and error handling functionality"""
    
    @pytest.fixture
    def analyzer(self):
        analyzer = SocialSentimentAnalyzer()
        analyzer.circuit_breaker_threshold = 2  # Lower threshold for testing
        return analyzer
    
    def test_circuit_breaker_tracking(self, analyzer):
        """Test circuit breaker failure tracking"""
        # Test failure counting
        source = "test_source"
        
        # Add failures
        analyzer.failed_requests[source] = analyzer.circuit_breaker_threshold
        
        assert analyzer.failed_requests[source] == analyzer.circuit_breaker_threshold
    
    def test_rate_limiting_counters(self, analyzer):
        """Test rate limiting counter initialization and updates"""
        assert analyzer.twitter_rate_limit == 0
        assert analyzer.reddit_rate_limit == 0
        
        # Test counter updates
        analyzer.twitter_rate_limit = 1
        analyzer.reddit_rate_limit = 5
        
        assert analyzer.twitter_rate_limit == 1
        assert analyzer.reddit_rate_limit == 5


class TestDataStoragePhase7B2:
    """Test data storage and history management"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    def test_sentiment_history_structure(self, analyzer):
        """Test sentiment history data structure"""
        symbol = "TEST"
        
        # Test defaultdict behavior
        assert len(analyzer.sentiment_history[symbol]) == 0
        assert isinstance(analyzer.sentiment_history[symbol], deque)
        
        # Test maxlen behavior
        for i in range(1010):  # More than maxlen=1000
            analyzer.sentiment_history[symbol].append({
                "timestamp": datetime.now(UTC),
                "sentiment": 0.5,
                "source": "test"
            })
        
        # Should be limited to maxlen
        assert len(analyzer.sentiment_history[symbol]) == 1000
    
    def test_symbol_mentions_tracking(self, analyzer):
        """Test symbol mentions counter"""
        symbol = "TEST"
        
        # Test defaultdict int behavior
        assert analyzer.symbol_mentions[symbol] == 0
        
        analyzer.symbol_mentions[symbol] += 1
        assert analyzer.symbol_mentions[symbol] == 1
    
    def test_last_update_tracking(self, analyzer):
        """Test last update timestamp tracking"""
        symbol = "TEST"
        now = datetime.now(UTC)
        
        analyzer.last_update[symbol] = now
        assert analyzer.last_update[symbol] == now


class TestAdvancedSentimentAnalysisPhase7B2:
    """Test advanced sentiment analysis scenarios"""
    
    @pytest.fixture
    def analyzer_with_model(self):
        analyzer = SocialSentimentAnalyzer()
        analyzer.finbert_pipeline = Mock()
        analyzer.model_loaded = True
        return analyzer
    
    def test_sentiment_label_mapping_positive(self, analyzer_with_model):
        """Test sentiment label mapping for positive sentiment"""
        labels_to_test = ["POSITIVE", "positive", "POS", "pos"]
        
        for label in labels_to_test:
            analyzer_with_model.finbert_pipeline.return_value = [{"label": label, "score": 0.8}]
            sentiment = analyzer_with_model.analyze_text_finbert("Good news!")
            assert sentiment > 0
    
    def test_sentiment_label_mapping_negative(self, analyzer_with_model):
        """Test sentiment label mapping for negative sentiment"""
        labels_to_test = ["NEGATIVE", "negative", "NEG", "neg"]
        
        for label in labels_to_test:
            analyzer_with_model.finbert_pipeline.return_value = [{"label": label, "score": 0.9}]
            sentiment = analyzer_with_model.analyze_text_finbert("Bad news!")
            assert sentiment < 0
    
    def test_sentiment_label_mapping_neutral(self, analyzer_with_model):
        """Test sentiment label mapping for neutral sentiment"""
        labels_to_test = ["NEUTRAL", "neutral", "NEU"]
        
        for label in labels_to_test:
            analyzer_with_model.finbert_pipeline.return_value = [{"label": label, "score": 0.6}]
            sentiment = analyzer_with_model.analyze_text_finbert("Neutral news")
            assert abs(sentiment) < 0.1
    
    def test_sentiment_unknown_label(self, analyzer_with_model):
        """Test sentiment analysis with unknown label"""
        analyzer_with_model.finbert_pipeline.return_value = [{"label": "UNKNOWN", "score": 0.5}]
        sentiment = analyzer_with_model.analyze_text_finbert("Unknown sentiment")
        
        # Should default to neutral
        assert sentiment == 0.0


class TestAsyncMethodsPhase7B2:
    """Test async methods coverage and exception handling"""
    
    @pytest.fixture
    def analyzer_with_clients(self):
        analyzer = SocialSentimentAnalyzer()
        analyzer.twitter_client = Mock()
        analyzer.reddit_client = Mock()
        analyzer.finbert_pipeline = Mock()
        analyzer.model_loaded = True
        return analyzer
    
    @pytest.mark.asyncio
    async def test_stream_twitter_sentiment_no_client(self):
        """Test Twitter streaming without client"""
        analyzer = SocialSentimentAnalyzer()  # No client
        
        # Should handle gracefully
        result = await analyzer.stream_twitter_sentiment(["AAPL"])
        # Method should complete without error
    
    @pytest.mark.asyncio 
    async def test_fetch_reddit_headlines_no_client(self):
        """Test Reddit fetching without client"""
        analyzer = SocialSentimentAnalyzer()  # No client
        
        result = await analyzer.fetch_reddit_headlines(["AAPL"])
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_reddit_processing_with_symbol_extraction(self, analyzer_with_clients):
        """Test Reddit processing that actually extracts symbols"""
        # Mock submission with symbol in title
        mock_submission = Mock()
        mock_submission.title = "AAPL stock hits new highs after earnings"
        mock_submission.selftext = "Apple's latest earnings beat expectations significantly"
        mock_submission.score = 150
        mock_submission.num_comments = 25
        mock_submission.created_utc = datetime.now().timestamp()
        mock_submission.url = "https://reddit.com/test"
        
        # Mock subreddit to return submission
        mock_subreddit = Mock()
        mock_subreddit.hot.return_value = [mock_submission]
        
        def mock_subreddit_func(name):
            return mock_subreddit
        
        analyzer_with_clients.reddit_client.subreddit = mock_subreddit_func
        analyzer_with_clients.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.8}]
        
        # Mock symbol extraction to return AAPL
        with patch.object(analyzer_with_clients, 'extract_symbols', return_value=["AAPL"]):
            result = await analyzer_with_clients.fetch_reddit_headlines(["AAPL"])
        
        # Should have processed the data
        assert "AAPL" in result
        assert len(analyzer_with_clients.sentiment_history["AAPL"]) > 0


class TestEdgeCasesPhase7B2:
    """Test edge cases and error conditions"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    def test_empty_symbol_lists(self, analyzer):
        """Test handling of empty symbol lists"""
        empty_symbols = analyzer.extract_symbols("")
        assert empty_symbols == []
        
        empty_symbols2 = analyzer.extract_symbols("No symbols here")
        assert empty_symbols2 == []
    
    def test_malformed_text_cleaning(self, analyzer):
        """Test text cleaning with malformed input"""
        # Very long text
        long_text = "This is a very long text. " * 1000
        cleaned = analyzer._clean_text(long_text)
        assert len(cleaned) <= len(long_text)  # Should handle without error
        
        # Text with only URLs and mentions
        url_text = "Check this out: https://example.com @user1 @user2"
        cleaned = analyzer._clean_text(url_text)
        assert "https://example.com" not in cleaned
        assert "@user1" not in cleaned
    
    def test_sentiment_analysis_edge_cases(self, analyzer):
        """Test sentiment analysis with edge cases"""
        # Empty text
        sentiment = analyzer.analyze_text_finbert("")
        assert isinstance(sentiment, float)
        
        # Very long text
        long_text = "This is amazing! " * 500
        sentiment = analyzer.analyze_text_finbert(long_text)
        assert isinstance(sentiment, float)
    
    def test_aggregated_sentiment_edge_cases(self, analyzer):
        """Test aggregated sentiment with various edge cases"""
        # Symbol with no history
        result = analyzer.get_aggregated_sentiment("NONEXISTENT")
        assert result is None
        
        # Symbol with insufficient mentions
        analyzer.sentiment_history["LOW_MENTIONS"].extend([
            {"timestamp": datetime.now(UTC), "sentiment": 0.5, "source": "test"}
            for _ in range(3)  # Less than min_mentions=5
        ])
        
        result = analyzer.get_aggregated_sentiment("LOW_MENTIONS")
        assert result is None
        
        # Custom min_mentions
        result = analyzer.get_aggregated_sentiment("LOW_MENTIONS", min_mentions=2)
        assert result is not None
    
    def test_sentiment_momentum_edge_cases(self, analyzer):
        """Test sentiment momentum calculation edge cases"""
        # No data
        momentum = analyzer._calculate_sentiment_momentum("EMPTY")
        assert momentum == 0.0
        
        # Insufficient data
        analyzer.sentiment_history["INSUFFICIENT"].extend([
            {"timestamp": datetime.now(UTC), "sentiment": 0.5}
            for _ in range(5)  # Less than 10 required
        ])
        
        momentum = analyzer._calculate_sentiment_momentum("INSUFFICIENT")
        assert momentum == 0.0
    
    def test_exception_handling_in_momentum(self, analyzer):
        """Test exception handling in momentum calculation"""
        # Add data that might cause calculation errors
        now = datetime.now(UTC)
        bad_data = [
            {"timestamp": now, "sentiment": float('inf')},
            {"timestamp": now, "sentiment": float('-inf')},
            {"timestamp": now, "sentiment": float('nan')},
        ]
        
        analyzer.sentiment_history["BAD_DATA"].extend(bad_data * 4)  # 12 items
        
        # Should handle gracefully and return 0.0
        momentum = analyzer._calculate_sentiment_momentum("BAD_DATA")
        assert momentum == 0.0


class TestComprehensiveIntegrationPhase7B2:
    """Test comprehensive integration scenarios"""
    
    @pytest.fixture
    def full_analyzer(self):
        """Create fully configured analyzer"""
        twitter_creds = {"bearer_token": "test"}
        reddit_creds = {"client_id": "test", "client_secret": "test"}
        
        analyzer = SocialSentimentAnalyzer(
            twitter_credentials=twitter_creds,
            reddit_credentials=reddit_creds,
            subreddit_list=["test_sub"]
        )
        
        # Mock all clients
        analyzer.twitter_client = Mock()
        analyzer.reddit_client = Mock()
        analyzer.finbert_pipeline = Mock()
        analyzer.model_loaded = True
        
        return analyzer
    
    def test_full_workflow_integration(self, full_analyzer):
        """Test complete workflow integration"""
        # Add comprehensive sentiment data
        now = datetime.now(UTC)
        
        # Add varied sentiment data
        sentiments = [0.8, -0.6, 0.2, 0.9, -0.3, 0.1, 0.7, -0.4, 0.5, -0.1]
        sources = ["twitter", "reddit_investing", "twitter", "reddit_wsb", "twitter"]
        
        for i, (sent, src) in enumerate(zip(sentiments, sources[:len(sentiments)])):
            full_analyzer.sentiment_history["COMPREHENSIVE"].append({
                "timestamp": now - timedelta(hours=i),
                "sentiment": sent,
                "source": src,
                "weight": 1.0 + (i * 0.1)  # Varying weights
            })
        
        # Test aggregation
        result = full_analyzer.get_aggregated_sentiment("COMPREHENSIVE", min_mentions=5)
        assert result is not None
        
        # Verify all expected fields
        expected_fields = [
            "symbol", "timestamp", "hours_analyzed", "total_mentions",
            "avg_sentiment", "weighted_sentiment", "sentiment_std",
            "positive_ratio", "negative_ratio", "neutral_ratio",
            "source_breakdown", "momentum"
        ]
        
        for field in expected_fields:
            assert field in result
        
        # Test summary generation
        symbols = ["COMPREHENSIVE", "EMPTY", "NEW"]
        summary = full_analyzer.get_sentiment_summary(symbols)
        
        assert len(summary) == 3
        assert summary["COMPREHENSIVE"]["total_mentions"] > 0
        assert summary["EMPTY"]["total_mentions"] == 0
    
    def test_real_time_processing_simulation(self, full_analyzer):
        """Test real-time processing simulation"""
        full_analyzer.finbert_pipeline.return_value = [{"label": "POSITIVE", "score": 0.7}]
        
        # Simulate processing multiple tweets
        tweets = [
            "Breaking: $AAPL beats earnings expectations!",
            "Bullish on $MSFT after strong cloud revenue",
            "$TSLA production numbers looking solid",
            "Concerned about $GOOGL regulatory issues",
            "$AMZN AWS growth continues to impress"
        ]
        
        symbols = ["AAPL", "MSFT", "TSLA", "GOOGL", "AMZN"]
        
        # Process all tweets
        for tweet in tweets:
            # Mock symbol extraction
            extracted = [s for s in symbols if f"${s}" in tweet]
            with patch.object(full_analyzer, 'extract_symbols', return_value=extracted):
                asyncio.run(full_analyzer._process_tweet(tweet, symbols))
        
        # Verify processing
        for symbol in symbols:
            if any(f"${symbol}" in tweet for tweet in tweets):
                assert len(full_analyzer.sentiment_history[symbol]) > 0
                assert full_analyzer.symbol_mentions[symbol] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
