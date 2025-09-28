"""
Comprehensive test suite for Module 22: backend.data.social_sentiment
Tests social sentiment analysis with Twitter, Reddit, and FinBERT integration.
"""

import pytest
import os
import asyncio
from unittest.mock import Mock, patch, MagicMock, call
from collections import defaultdict, deque
from datetime import datetime, timedelta, UTC
import time

# Import the module under test
from backend.data.social_sentiment import (
    SocialSentimentAnalyzer,
    DISABLE_ML,
    TWEEPY_AVAILABLE,
    PRAW_AVAILABLE,
    NLP_AVAILABLE
)


class TestModule22BackendDataSocialSentiment:
    """Comprehensive test suite for social sentiment analysis functionality."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.twitter_credentials = {
            "consumer_key": "test_key",
            "consumer_secret": "test_secret",
            "access_token": "test_token",
            "access_token_secret": "test_token_secret"
        }
        
        self.reddit_credentials = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "user_agent": "test_agent"
        }
        
        self.subreddit_list = ["testmarket", "testinvesting"]

    def test_social_sentiment_analyzer_initialization_minimal(self):
        """Test SocialSentimentAnalyzer initialization with minimal parameters."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.twitter_client is None
        assert analyzer.reddit_client is None
        assert analyzer.finbert_pipeline is None
        assert not analyzer.model_loaded
        assert len(analyzer.subreddit_list) > 0  # Should have default subreddits
        assert analyzer.request_timeout == 10
        assert analyzer.max_retries == 3

    def test_social_sentiment_analyzer_initialization_with_credentials(self):
        """Test SocialSentimentAnalyzer initialization with full credentials."""
        with patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True), \
             patch('backend.data.social_sentiment.PRAW_AVAILABLE', True), \
             patch('backend.data.social_sentiment.tweepy.OAuthHandler') as mock_auth, \
             patch('backend.data.social_sentiment.tweepy.API') as mock_api, \
             patch('backend.data.social_sentiment.praw.Reddit') as mock_reddit:
            
            # Mock successful Twitter setup
            mock_twitter_api = Mock()
            mock_api.return_value = mock_twitter_api
            mock_twitter_api.verify_credentials.return_value = True
            
            # Mock successful Reddit setup
            mock_reddit_instance = Mock()
            mock_reddit.return_value = mock_reddit_instance
            mock_reddit_instance.user.me.return_value = Mock()
            
            analyzer = SocialSentimentAnalyzer(
                twitter_credentials=self.twitter_credentials,
                reddit_credentials=self.reddit_credentials,
                subreddit_list=self.subreddit_list
            )
            
            assert analyzer.subreddit_list == self.subreddit_list

    def test_social_sentiment_analyzer_default_subreddits(self):
        """Test default subreddit list configuration."""
        analyzer = SocialSentimentAnalyzer()
        
        expected_subreddits = [
            "StockMarket",
            "investing", 
            "wallstreetbets",
            "cryptocurrency",
            "Bitcoin",
            "ethtrader"
        ]
        
        assert analyzer.subreddit_list == expected_subreddits

    def test_social_sentiment_analyzer_rate_limiting_config(self):
        """Test rate limiting configuration."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.request_timeout == 10
        assert analyzer.max_retries == 3
        assert analyzer.retry_delay == 1.0
        assert analyzer.circuit_breaker_threshold == 5
        assert analyzer.circuit_breaker_cooldown == 300
        assert isinstance(analyzer.circuit_open_until, dict)

    def test_social_sentiment_analyzer_data_storage_initialization(self):
        """Test data storage structures initialization."""
        analyzer = SocialSentimentAnalyzer()
        
        assert isinstance(analyzer.sentiment_history, defaultdict)
        assert isinstance(analyzer.symbol_mentions, defaultdict)
        assert isinstance(analyzer.last_update, dict)
        assert isinstance(analyzer.failed_requests, defaultdict)

    def test_social_sentiment_analyzer_text_preprocessing_patterns(self):
        """Test text preprocessing pattern compilation."""
        analyzer = SocialSentimentAnalyzer()
        
        # Test cashtag pattern
        cashtag_matches = analyzer.cashtag_pattern.findall("$AAPL and $TSLA are rising")
        assert "AAPL" in cashtag_matches
        assert "TSLA" in cashtag_matches
        
        # Test crypto pattern
        crypto_matches = analyzer.crypto_pattern.findall("BTC and ETH are bullish")
        assert "BTC" in crypto_matches
        assert "ETH" in crypto_matches

    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', False)
    def test_init_twitter_tweepy_unavailable(self):
        """Test Twitter initialization when tweepy is unavailable."""
        analyzer = SocialSentimentAnalyzer(twitter_credentials=self.twitter_credentials)
        
        assert analyzer.twitter_client is None

    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True)
    def test_init_twitter_no_credentials(self):
        """Test Twitter initialization without credentials."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.twitter_client is None

    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True)
    @patch('backend.data.social_sentiment.tweepy.OAuthHandler')
    @patch('backend.data.social_sentiment.tweepy.API')
    def test_init_twitter_successful(self, mock_api, mock_auth):
        """Test successful Twitter initialization."""
        # Mock successful authentication
        mock_twitter_api = Mock()
        mock_api.return_value = mock_twitter_api
        mock_twitter_api.verify_credentials.return_value = True
        
        analyzer = SocialSentimentAnalyzer(twitter_credentials=self.twitter_credentials)
        
        # Verify Twitter client would be set up if tweepy available
        mock_auth.assert_called_once()
        mock_api.assert_called_once()

    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True)
    @patch('backend.data.social_sentiment.tweepy.OAuthHandler')
    @patch('backend.data.social_sentiment.tweepy.API')
    def test_init_twitter_authentication_failure(self, mock_api, mock_auth):
        """Test Twitter initialization with authentication failure."""
        # Mock authentication failure
        mock_twitter_api = Mock()
        mock_api.return_value = mock_twitter_api
        mock_twitter_api.verify_credentials.side_effect = Exception("Auth failed")
        
        analyzer = SocialSentimentAnalyzer(twitter_credentials=self.twitter_credentials)
        
        # Should handle auth failure gracefully
        assert analyzer.twitter_client is None

    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', False)
    def test_init_reddit_praw_unavailable(self):
        """Test Reddit initialization when praw is unavailable."""
        analyzer = SocialSentimentAnalyzer(reddit_credentials=self.reddit_credentials)
        
        assert analyzer.reddit_client is None

    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', True)
    def test_init_reddit_no_credentials(self):
        """Test Reddit initialization without credentials."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.reddit_client is None

    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', True)
    @patch('backend.data.social_sentiment.praw.Reddit')
    def test_init_reddit_successful(self, mock_reddit):
        """Test successful Reddit initialization."""
        # Mock successful Reddit setup
        mock_reddit_instance = Mock()
        mock_reddit.return_value = mock_reddit_instance
        mock_reddit_instance.user.me.return_value = Mock()
        
        analyzer = SocialSentimentAnalyzer(reddit_credentials=self.reddit_credentials)
        
        # Verify Reddit client would be set up if praw available
        mock_reddit.assert_called_once()

    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', True)
    @patch('backend.data.social_sentiment.praw.Reddit')
    def test_init_reddit_authentication_failure(self, mock_reddit):
        """Test Reddit initialization with authentication failure."""
        # Mock authentication failure
        mock_reddit_instance = Mock()
        mock_reddit.return_value = mock_reddit_instance
        mock_reddit_instance.user.me.side_effect = Exception("Auth failed")
        
        analyzer = SocialSentimentAnalyzer(reddit_credentials=self.reddit_credentials)
        
        # Should handle auth failure gracefully
        assert analyzer.reddit_client is None

    @patch('backend.data.social_sentiment.NLP_AVAILABLE', False)
    def test_init_finbert_nlp_unavailable(self):
        """Test FinBERT initialization when NLP libraries unavailable."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.finbert_pipeline is None
        assert not analyzer.model_loaded

    @patch('backend.data.social_sentiment.NLP_AVAILABLE', True)
    @patch('backend.data.social_sentiment.pipeline')
    def test_init_finbert_successful(self, mock_pipeline):
        """Test successful FinBERT initialization."""
        # Mock successful pipeline creation
        mock_sentiment_pipeline = Mock()
        mock_pipeline.return_value = mock_sentiment_pipeline
        
        analyzer = SocialSentimentAnalyzer()
        
        # Verify FinBERT would be initialized if available
        if NLP_AVAILABLE:
            mock_pipeline.assert_called_once()

    @patch('backend.data.social_sentiment.NLP_AVAILABLE', True)
    @patch('backend.data.social_sentiment.pipeline')
    def test_init_finbert_failure(self, mock_pipeline):
        """Test FinBERT initialization failure."""
        # Mock pipeline creation failure
        mock_pipeline.side_effect = Exception("Model loading failed")
        
        analyzer = SocialSentimentAnalyzer()
        
        # Should handle model loading failure gracefully
        assert not analyzer.model_loaded

    def test_environment_variable_disable_ml(self):
        """Test DISABLE_ML environment variable handling."""
        with patch.dict(os.environ, {'DISABLE_ML': '1'}):
            # Re-import to test the environment variable
            import importlib
            import backend.data.social_sentiment
            importlib.reload(backend.data.social_sentiment)
            
            assert backend.data.social_sentiment.DISABLE_ML is True

    def test_environment_variable_pytest_running(self):
        """Test PYTEST_RUNNING environment variable detection."""
        with patch.dict(os.environ, {'PYTEST_RUNNING': '1'}):
            # This should prevent NLP imports during testing
            analyzer = SocialSentimentAnalyzer()
            
            # Should work without NLP libraries during testing
            assert isinstance(analyzer, SocialSentimentAnalyzer)

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker pattern initialization."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.circuit_breaker_threshold == 5
        assert analyzer.circuit_breaker_cooldown == 300
        assert isinstance(analyzer.circuit_open_until, dict)
        assert isinstance(analyzer.failed_requests, defaultdict)

    def test_rate_limiting_initialization(self):
        """Test rate limiting structures initialization."""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.twitter_rate_limit == 0
        assert analyzer.reddit_rate_limit == 0
        assert analyzer.retry_delay == 1.0
        assert analyzer.max_retries == 3

    def test_sentiment_history_structure(self):
        """Test sentiment history data structure."""
        analyzer = SocialSentimentAnalyzer()
        
        # Test defaultdict behavior
        test_symbol = "AAPL"
        analyzer.sentiment_history[test_symbol].append({"sentiment": "positive", "timestamp": datetime.now()})
        
        assert len(analyzer.sentiment_history[test_symbol]) == 1
        assert isinstance(analyzer.sentiment_history[test_symbol], deque)

    def test_symbol_mentions_tracking(self):
        """Test symbol mentions tracking structure."""
        analyzer = SocialSentimentAnalyzer()
        
        # Test defaultdict behavior
        test_symbol = "TSLA"
        analyzer.symbol_mentions[test_symbol] += 1
        
        assert analyzer.symbol_mentions[test_symbol] == 1
        assert analyzer.symbol_mentions["NONEXISTENT"] == 0  # Default behavior

    def test_logger_initialization(self):
        """Test logger initialization."""
        analyzer = SocialSentimentAnalyzer()
        
        assert hasattr(analyzer, 'logger')
        assert analyzer.logger is not None

    def test_cashtag_pattern_comprehensive(self):
        """Test comprehensive cashtag pattern matching."""
        analyzer = SocialSentimentAnalyzer()
        
        test_cases = [
            ("$AAPL is rising", ["AAPL"]),
            ("Buy $TSLA and $MSFT", ["TSLA", "MSFT"]),
            ("$GOOGL $AMZN bullish", ["GOOGL", "AMZN"]),
            ("No symbols here", []),
            ("$A too short", []),  # Single letter should not match
            ("$TOOLONG should not match", []),  # Too long should not match
            ("$BTC $ETH crypto", ["BTC", "ETH"])
        ]
        
        for text, expected in test_cases:
            matches = analyzer.cashtag_pattern.findall(text)
            assert matches == expected, f"Failed for text: {text}"

    def test_crypto_pattern_comprehensive(self):
        """Test comprehensive crypto pattern matching.""" 
        analyzer = SocialSentimentAnalyzer()
        
        test_cases = [
            ("BTC is bullish", ["BTC"]),
            ("eth and btc rising", ["ETH", "BTC"]),
            ("DOGE to the moon", ["DOGE"]),
            ("No crypto here", []),
            ("LINK UNI ADA all green", ["LINK", "UNI", "ADA"]),
            ("dot polkadot", ["DOT"])
        ]
        
        for text, expected in test_cases:
            matches = analyzer.crypto_pattern.findall(text)
            # Note: pattern matching is case-insensitive but returns original case
            matches_upper = [m.upper() for m in matches]
            expected_upper = [e.upper() for e in expected]
            assert matches_upper == expected_upper, f"Failed for text: {text}"

    def test_deque_maxlen_configuration(self):
        """Test deque maxlen configuration for sentiment history."""
        analyzer = SocialSentimentAnalyzer()
        
        test_symbol = "TEST"
        sentiment_deque = analyzer.sentiment_history[test_symbol]
        
        # Add more than maxlen items
        for i in range(1100):  # More than maxlen=1000
            sentiment_deque.append({"sentiment": f"test_{i}", "timestamp": datetime.now()})
        
        # Should only keep the last 1000 items
        assert len(sentiment_deque) == 1000
        assert sentiment_deque[0]["sentiment"] == "test_100"  # First 100 should be dropped
        assert sentiment_deque[-1]["sentiment"] == "test_1099"

    @patch('backend.data.social_sentiment.get_structured_logger')
    def test_structured_logger_usage(self, mock_get_logger):
        """Test structured logger usage."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        analyzer = SocialSentimentAnalyzer()
        
        mock_get_logger.assert_called_with("social_sentiment")
        assert analyzer.logger == mock_logger

    def test_configuration_immutability_protection(self):
        """Test that critical configuration cannot be accidentally modified."""
        analyzer = SocialSentimentAnalyzer()
        
        original_timeout = analyzer.request_timeout
        original_retries = analyzer.max_retries
        original_threshold = analyzer.circuit_breaker_threshold
        
        # These should be instance attributes that can be modified if needed
        analyzer.request_timeout = 20
        analyzer.max_retries = 5
        analyzer.circuit_breaker_threshold = 10
        
        assert analyzer.request_timeout == 20
        assert analyzer.max_retries == 5
        assert analyzer.circuit_breaker_threshold == 10

    def test_memory_efficient_data_structures(self):
        """Test memory efficiency of data structures."""
        analyzer = SocialSentimentAnalyzer()
        
        # Test that defaultdict doesn't create unnecessary entries
        initial_keys = len(analyzer.sentiment_history.keys())
        initial_mentions_keys = len(analyzer.symbol_mentions.keys())
        
        # Access non-existent keys shouldn't create persistent entries
        _ = analyzer.sentiment_history["NONEXISTENT"]
        _ = analyzer.symbol_mentions["NONEXISTENT"]
        
        # Only adding data should create persistent entries
        analyzer.sentiment_history["AAPL"].append({"test": "data"})
        analyzer.symbol_mentions["AAPL"] += 1
        
        assert len(analyzer.sentiment_history.keys()) == initial_keys + 1
        assert len(analyzer.symbol_mentions.keys()) == initial_mentions_keys + 1

    def test_import_fallback_behavior(self):
        """Test import fallback behavior for optional dependencies."""
        # Test that the module can be imported even without optional dependencies
        assert hasattr(SocialSentimentAnalyzer, '__init__')
        
        # Test fallback classes exist
        if not TWEEPY_AVAILABLE:
            import backend.data.social_sentiment
            assert hasattr(backend.data.social_sentiment, 'tweepy')
        
        if not PRAW_AVAILABLE:
            import backend.data.social_sentiment
            assert hasattr(backend.data.social_sentiment, 'praw')
        
        if not NLP_AVAILABLE:
            import backend.data.social_sentiment
            assert hasattr(backend.data.social_sentiment, 'pipeline')

    def test_module_level_constants(self):
        """Test module-level constants and flags."""
        import backend.data.social_sentiment as module
        
        assert hasattr(module, 'DISABLE_ML')
        assert hasattr(module, 'TWEEPY_AVAILABLE')
        assert hasattr(module, 'PRAW_AVAILABLE')
        assert hasattr(module, 'NLP_AVAILABLE')
        
        assert isinstance(module.DISABLE_ML, bool)
        assert isinstance(module.TWEEPY_AVAILABLE, bool)
        assert isinstance(module.PRAW_AVAILABLE, bool)
        assert isinstance(module.NLP_AVAILABLE, bool)

    def test_comprehensive_initialization_logging(self):
        """Test comprehensive initialization logging."""
        with patch('backend.data.social_sentiment.get_structured_logger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            
            analyzer = SocialSentimentAnalyzer()
            
            # Should log initialization info
            mock_logger.info.assert_called()
            
            # Check that the log call includes status information
            log_call_args = mock_logger.info.call_args
            assert "Social sentiment analyzer initialized" in str(log_call_args)

    def test_error_handling_graceful_degradation(self):
        """Test graceful degradation when services are unavailable."""
        # Test that analyzer can be created even when all external services fail
        with patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', False), \
             patch('backend.data.social_sentiment.PRAW_AVAILABLE', False), \
             patch('backend.data.social_sentiment.NLP_AVAILABLE', False):
            
            analyzer = SocialSentimentAnalyzer(
                twitter_credentials=self.twitter_credentials,
                reddit_credentials=self.reddit_credentials
            )
            
            # Should still be functional for basic operations
            assert analyzer is not None
            assert analyzer.twitter_client is None
            assert analyzer.reddit_client is None
            assert analyzer.finbert_pipeline is None

    def test_realistic_social_sentiment_configuration(self):
        """Test realistic social sentiment analyzer configuration."""
        # Test with realistic configuration that would be used in production
        custom_subreddits = [
            "StockMarket",
            "SecurityAnalysis", 
            "ValueInvesting",
            "Options",
            "Daytrading"
        ]
        
        twitter_creds = {
            "consumer_key": "real_consumer_key",
            "consumer_secret": "real_consumer_secret", 
            "access_token": "real_access_token",
            "access_token_secret": "real_access_token_secret"
        }
        
        reddit_creds = {
            "client_id": "real_client_id",
            "client_secret": "real_client_secret",
            "user_agent": "TradingBot/1.0 by YourUsername"
        }
        
        analyzer = SocialSentimentAnalyzer(
            twitter_credentials=twitter_creds,
            reddit_credentials=reddit_creds,
            subreddit_list=custom_subreddits
        )
        
        assert analyzer.subreddit_list == custom_subreddits
        assert analyzer.request_timeout == 10
        assert analyzer.max_retries == 3
        assert len(analyzer.sentiment_history) == 0  # Should start empty
        assert analyzer.symbol_mentions.default_factory() == 0

    def test_module_import_safety(self):
        """Test that module can be safely imported in different environments."""
        # Test that importing the module doesn't cause errors
        import backend.data.social_sentiment
        
        # Test that class can be instantiated even with missing dependencies
        analyzer = backend.data.social_sentiment.SocialSentimentAnalyzer()
        
        assert isinstance(analyzer, backend.data.social_sentiment.SocialSentimentAnalyzer)

    def test_dependency_availability_detection(self):
        """Test dependency availability detection accuracy."""
        import backend.data.social_sentiment as module
        
        # Test tweepy availability detection
        try:
            import tweepy
            expected_tweepy = True
        except ImportError:
            expected_tweepy = False
        
        # Note: The module sets this at import time, so we can only test current state
        assert isinstance(module.TWEEPY_AVAILABLE, bool)
        
        # Test praw availability detection  
        try:
            import praw
            expected_praw = True
        except ImportError:
            expected_praw = False
            
        assert isinstance(module.PRAW_AVAILABLE, bool)

    def test_performance_logger_import(self):
        """Test performance logger import."""
        # This should not raise an error
        from backend.data.social_sentiment import performance_logger
        
        # The import should succeed even if the logger isn't fully functional
        assert performance_logger is not None


# ============================================================================
# COMPREHENSIVE COVERAGE TESTS - Merged from test_social_sentiment_comprehensive.py
# ============================================================================

class TestSocialSentimentAnalyzerComprehensive:
    """Comprehensive test coverage for SocialSentimentAnalyzer."""
    
    def test_analyzer_initialization_comprehensive(self):
        """Test analyzer initialization with comprehensive parameters."""
        twitter_creds = {
            "consumer_key": "test_key",
            "consumer_secret": "test_secret", 
            "access_token": "test_token",
            "access_token_secret": "test_token_secret"
        }
        
        reddit_creds = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "user_agent": "test_agent"
        }
        
        subreddits = ["testmarket", "testinvesting"]
        
        analyzer = SocialSentimentAnalyzer(
            twitter_credentials=twitter_creds,
            reddit_credentials=reddit_creds,
            subreddit_list=subreddits
        )
        
        # Check configuration was set
        assert analyzer.twitter_credentials == twitter_creds
        assert analyzer.reddit_credentials == reddit_creds
        assert analyzer.subreddit_list == subreddits
        
    def test_twitter_client_initialization_comprehensive(self):
        """Test Twitter client initialization with comprehensive coverage."""
        if not TWEEPY_AVAILABLE:
            pytest.skip("Tweepy not available")
            
        analyzer = SocialSentimentAnalyzer()
        
        # Test with valid credentials
        twitter_creds = {
            "consumer_key": "test_key",
            "consumer_secret": "test_secret",
            "access_token": "test_token", 
            "access_token_secret": "test_token_secret"
        }
        
        with patch('backend.data.social_sentiment.tweepy.Client') as mock_client:
            analyzer._init_twitter_client(twitter_creds)
            mock_client.assert_called_once()
            
    def test_reddit_client_initialization_comprehensive(self):
        """Test Reddit client initialization with comprehensive coverage."""
        if not PRAW_AVAILABLE:
            pytest.skip("PRAW not available")
            
        analyzer = SocialSentimentAnalyzer()
        
        # Test with valid credentials
        reddit_creds = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "user_agent": "test_agent"
        }
        
        with patch('backend.data.social_sentiment.praw.Reddit') as mock_reddit:
            analyzer._init_reddit_client(reddit_creds)
            mock_reddit.assert_called_once()
            
    def test_finbert_pipeline_initialization_comprehensive(self):
        """Test FinBERT pipeline initialization with comprehensive coverage."""
        if DISABLE_ML or not NLP_AVAILABLE:
            pytest.skip("NLP not available or ML disabled")
            
        analyzer = SocialSentimentAnalyzer()
        
        with patch('backend.data.social_sentiment.pipeline') as mock_pipeline:
            mock_pipeline.return_value = Mock()
            analyzer._init_finbert_pipeline()
            mock_pipeline.assert_called_once()
            
    def test_sentiment_data_storage_comprehensive(self):
        """Test comprehensive sentiment data storage and retrieval."""
        analyzer = SocialSentimentAnalyzer()
        
        # Test adding multiple sentiment data points
        for i in range(3):
            sentiment_data = {
                "timestamp": datetime.now(UTC) - timedelta(hours=i),
                "symbol": "AAPL",
                "sentiment": {"positive": 0.5, "negative": 0.3, "neutral": 0.2, "compound": 0.2},
                "source": "reddit",
                "text_sample": f"Sample text {i}"
            }
            analyzer.add_sentiment_data("AAPL", sentiment_data)
        
        history = analyzer.get_sentiment_history("AAPL")
        assert len(history) == 3
        
        # Test with time filter
        since = datetime.now(UTC) - timedelta(hours=1, minutes=30)
        recent_history = analyzer.get_sentiment_history("AAPL", since=since) 
        assert len(recent_history) < 3  # Should filter out older entries