"""
Phase 7B.2: Social Sentiment Analysis Module Testing
Targeting backend/data/social_sentiment.py for comprehensive coverage
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, UTC, timedelta
from collections import defaultdict, deque
import json

from backend.data.social_sentiment import SocialSentimentAnalyzer


class TestSocialSentimentAnalyzerPhase7B2:
    """Test SocialSentimentAnalyzer initialization and configuration"""
    
    @pytest.fixture
    def twitter_credentials(self):
        return {
            "api_key": "test_api_key",
            "api_secret": "test_api_secret",
            "access_token": "test_access_token",
            "access_token_secret": "test_access_token_secret",
            "bearer_token": "test_bearer_token"
        }
    
    @pytest.fixture
    def reddit_credentials(self):
        return {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "user_agent": "TestSentimentAnalyzer/1.0"
        }
    
    @pytest.fixture
    def sample_subreddits(self):
        return ["StockMarket", "investing", "wallstreetbets"]
    
    def test_analyzer_initialization_default(self):
        """Test analyzer initialization with default parameters"""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer is not None
        assert analyzer.twitter_client is None
        assert analyzer.reddit_client is None
        assert analyzer.finbert_pipeline is None
        assert analyzer.model_loaded is False
        
        # Check default configuration
        assert "StockMarket" in analyzer.subreddit_list
        assert "investing" in analyzer.subreddit_list
        assert "wallstreetbets" in analyzer.subreddit_list
        
        # Check rate limiting configuration
        assert analyzer.request_timeout == 10
        assert analyzer.max_retries == 3
        assert analyzer.retry_delay == 1.0
        assert analyzer.circuit_breaker_threshold == 5
        assert analyzer.circuit_breaker_cooldown == 300
    
    def test_analyzer_initialization_with_custom_subreddits(self, sample_subreddits):
        """Test analyzer initialization with custom subreddit list"""
        analyzer = SocialSentimentAnalyzer(subreddit_list=sample_subreddits)
        
        assert analyzer.subreddit_list == sample_subreddits
        assert len(analyzer.subreddit_list) == 3
        assert "StockMarket" in analyzer.subreddit_list
    
    def test_analyzer_data_structures_initialization(self):
        """Test that all data structures are properly initialized"""
        analyzer = SocialSentimentAnalyzer()
        
        # Check data storage structures
        assert isinstance(analyzer.sentiment_history, defaultdict)
        assert isinstance(analyzer.symbol_mentions, defaultdict)
        assert isinstance(analyzer.last_update, dict)
        assert isinstance(analyzer.failed_requests, defaultdict)
        assert isinstance(analyzer.circuit_open_until, dict)
        
        # Check rate limiting counters
        assert analyzer.twitter_rate_limit == 0
        assert analyzer.reddit_rate_limit == 0
    
    def test_text_patterns_initialization(self):
        """Test that regex patterns are properly initialized"""
        analyzer = SocialSentimentAnalyzer()
        
        assert analyzer.cashtag_pattern is not None
        assert analyzer.crypto_pattern is not None
        
        # Test cashtag pattern
        test_text = "I'm bullish on $AAPL and $MSFT today"
        matches = analyzer.cashtag_pattern.findall(test_text)
        assert "AAPL" in matches
        assert "MSFT" in matches
        
        # Test crypto pattern
        crypto_text = "BTC and ETH are looking strong"
        crypto_matches = analyzer.crypto_pattern.findall(crypto_text)
        assert "BTC" in crypto_matches
        assert "ETH" in crypto_matches


class TestTwitterIntegrationPhase7B2:
    """Test Twitter API integration and initialization"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True)
    @patch('backend.data.social_sentiment.tweepy')
    def test_twitter_initialization_success_v2(self, mock_tweepy, analyzer):
        """Test successful Twitter client initialization with v2 API"""
        # Mock Twitter client
        mock_client = Mock()
        mock_client.get_me.return_value = Mock(username="test_user")
        mock_tweepy.Client.return_value = mock_client
        
        credentials = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "bearer_token": "test_bearer"
        }
        
        analyzer._init_twitter(credentials)
        
        assert analyzer.twitter_client is not None
        mock_tweepy.Client.assert_called_once()
    
    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True)
    @patch('backend.data.social_sentiment.tweepy')
    def test_twitter_initialization_success_v1(self, mock_tweepy, analyzer):
        """Test successful Twitter client initialization with v1.1 API"""
        # Mock Twitter client without bearer token (v1.1 fallback)
        mock_auth = Mock()
        mock_api = Mock()
        mock_api.verify_credentials.return_value = Mock(screen_name="test_user")
        
        mock_tweepy.OAuthHandler.return_value = mock_auth
        mock_tweepy.API.return_value = mock_api
        
        credentials = {
            "api_key": "test_key",
            "api_secret": "test_secret",
            "access_token": "test_token",
            "access_token_secret": "test_token_secret"
        }
        
        analyzer._init_twitter(credentials)
        
        assert analyzer.twitter_client is not None
        mock_tweepy.OAuthHandler.assert_called_once()
    
    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', False)
    def test_twitter_initialization_unavailable(self, analyzer):
        """Test Twitter initialization when tweepy is not available"""
        credentials = {"api_key": "test", "api_secret": "test"}
        
        analyzer._init_twitter(credentials)
        
        assert analyzer.twitter_client is None
    
    def test_twitter_initialization_no_credentials(self, analyzer):
        """Test Twitter initialization with no credentials"""
        analyzer._init_twitter(None)
        
        assert analyzer.twitter_client is None
    
    @patch('backend.data.social_sentiment.TWEEPY_AVAILABLE', True)
    @patch('backend.data.social_sentiment.tweepy')
    def test_twitter_initialization_exception(self, mock_tweepy, analyzer):
        """Test Twitter initialization with exception"""
        mock_tweepy.Client.side_effect = Exception("API Error")
        
        credentials = {"bearer_token": "test_bearer"}
        
        analyzer._init_twitter(credentials)
        
        assert analyzer.twitter_client is None


class TestRedditIntegrationPhase7B2:
    """Test Reddit API integration and initialization"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', True)
    @patch('backend.data.social_sentiment.praw')
    def test_reddit_initialization_success(self, mock_praw, analyzer):
        """Test successful Reddit client initialization"""
        mock_reddit = Mock()
        mock_reddit.auth.limits = {}
        mock_praw.Reddit.return_value = mock_reddit
        
        credentials = {
            "client_id": "test_id",
            "client_secret": "test_secret",
            "user_agent": "TestAgent/1.0"
        }
        
        analyzer._init_reddit(credentials)
        
        assert analyzer.reddit_client is not None
        mock_praw.Reddit.assert_called_once_with(
            client_id="test_id",
            client_secret="test_secret",
            user_agent="TestAgent/1.0"
        )
    
    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', False)
    def test_reddit_initialization_unavailable(self, analyzer):
        """Test Reddit initialization when praw is not available"""
        credentials = {"client_id": "test", "client_secret": "test"}
        
        analyzer._init_reddit(credentials)
        
        assert analyzer.reddit_client is None
    
    def test_reddit_initialization_no_credentials(self, analyzer):
        """Test Reddit initialization with no credentials"""
        analyzer._init_reddit(None)
        
        assert analyzer.reddit_client is None
    
    @patch('backend.data.social_sentiment.PRAW_AVAILABLE', True)
    @patch('backend.data.social_sentiment.praw')
    def test_reddit_initialization_exception(self, mock_praw, analyzer):
        """Test Reddit initialization with exception"""
        mock_praw.Reddit.side_effect = Exception("Reddit API Error")
        
        credentials = {"client_id": "test", "client_secret": "test"}
        
        analyzer._init_reddit(credentials)
        
        assert analyzer.reddit_client is None


class TestFinBERTIntegrationPhase7B2:
    """Test FinBERT model initialization and sentiment analysis"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    @patch('backend.data.social_sentiment.NLP_AVAILABLE', False)
    def test_finbert_initialization_unavailable(self, analyzer):
        """Test FinBERT initialization when transformers is not available"""
        analyzer._init_finbert()
        
        assert analyzer.finbert_pipeline is None
        assert analyzer.model_loaded is False
    
    @patch('backend.data.social_sentiment.NLP_AVAILABLE', True)
    @patch('backend.data.social_sentiment.pipeline')
    def test_finbert_initialization_success_gpu(self, mock_pipeline, analyzer):
        """Test successful FinBERT initialization with GPU"""
        # Mock torch availability
        with patch.dict('sys.modules', {'torch': Mock()}):
            mock_torch = Mock()
            mock_torch.cuda.is_available.return_value = True
            
            mock_finbert_pipeline = Mock()
            mock_pipeline.return_value = mock_finbert_pipeline
            
            # Temporarily set NLP available and patch torch
            with patch('backend.data.social_sentiment.torch', mock_torch, create=True):
                analyzer._init_finbert()
            
            assert analyzer.finbert_pipeline is not None
            assert analyzer.model_loaded is True
    
    @patch('backend.data.social_sentiment.NLP_AVAILABLE', True)
    @patch('backend.data.social_sentiment.pipeline')
    def test_finbert_initialization_success_cpu(self, mock_pipeline, analyzer):
        """Test successful FinBERT initialization with CPU"""
        # Mock torch availability
        with patch.dict('sys.modules', {'torch': Mock()}):
            mock_torch = Mock()
            mock_torch.cuda.is_available.return_value = False
            
            mock_finbert_pipeline = Mock()
            mock_pipeline.return_value = mock_finbert_pipeline
            
            # Temporarily set torch and run init
            with patch('backend.data.social_sentiment.torch', mock_torch, create=True):
                analyzer._init_finbert()
            
            assert analyzer.finbert_pipeline is not None
            assert analyzer.model_loaded is True
    
    @patch('backend.data.social_sentiment.NLP_AVAILABLE', True)
    @patch('backend.data.social_sentiment.pipeline')
    def test_finbert_initialization_fallback_model(self, mock_pipeline, analyzer):
        """Test FinBERT initialization with fallback model"""
        # First call fails, second succeeds
        mock_pipeline.side_effect = [
            Exception("FinBERT model failed"),
            Mock()  # Fallback model succeeds
        ]
        
        # Mock torch availability
        with patch.dict('sys.modules', {'torch': Mock()}):
            mock_torch = Mock()
            mock_torch.cuda.is_available.return_value = False
            
            with patch('backend.data.social_sentiment.torch', mock_torch, create=True):
                analyzer._init_finbert()
        
        assert analyzer.finbert_pipeline is not None
        assert analyzer.model_loaded is True
        assert mock_pipeline.call_count == 2


class TestTextProcessingPhase7B2:
    """Test text processing and sentiment analysis functionality"""
    
    @pytest.fixture
    def analyzer(self):
        return SocialSentimentAnalyzer()
    
    def test_clean_text_basic(self, analyzer):
        """Test basic text cleaning functionality"""
        # Test with URLs
        text_with_url = "Check out this stock https://example.com $AAPL"
        cleaned = analyzer._clean_text(text_with_url)
        assert "https://example.com" not in cleaned
        assert "$AAPL" in cleaned
        
        # Test with mentions
        text_with_mention = "@user thinks $MSFT is good"
        cleaned = analyzer._clean_text(text_with_mention)
        assert "@user" not in cleaned
        assert "$MSFT" in cleaned
    
    def test_clean_text_edge_cases(self, analyzer):
        """Test text cleaning with edge cases"""
        # Empty string
        assert analyzer._clean_text("") == ""
        
        # Only whitespace
        assert analyzer._clean_text("   \n\t  ").strip() == ""
        
        # Special characters
        text = "Stock is up! 📈 $AAPL to the moon 🚀"
        cleaned = analyzer._clean_text(text)
        assert "$AAPL" in cleaned
        assert len(cleaned) > 0
    
    def test_extract_symbols_cashtags(self, analyzer):
        """Test symbol extraction from cashtags"""
        text = "Bullish on $AAPL and $MSFT, but $TSLA concerns me"
        symbols = analyzer.extract_symbols(text)
        
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "TSLA" in symbols
        assert len(symbols) == 3
    
    def test_extract_symbols_crypto(self, analyzer):
        """Test symbol extraction for crypto"""
        text = "BTC and ETH are looking strong, ADA might follow"
        symbols = analyzer.extract_symbols(text)
        
        assert "BTC" in symbols
        assert "ETH" in symbols
        assert "ADA" in symbols
    
    def test_extract_symbols_mixed(self, analyzer):
        """Test symbol extraction with mixed cashtags and crypto"""
        text = "$AAPL earnings strong, BTC breaking resistance"
        symbols = analyzer.extract_symbols(text)
        
        assert "AAPL" in symbols
        assert "BTC" in symbols
        assert len(symbols) == 2
    
    def test_extract_symbols_empty(self, analyzer):
        """Test symbol extraction with no symbols"""
        text = "General market commentary without specific mentions"
        symbols = analyzer.extract_symbols(text)
        
        assert len(symbols) == 0
        assert symbols == []
    
    @patch('backend.data.social_sentiment.NLP_AVAILABLE', False)
    def test_analyze_text_finbert_mock_fallback(self, analyzer):
        """Test sentiment analysis with mock fallback when FinBERT unavailable"""
        analyzer.model_loaded = False
        
        # Should return mock sentiment
        sentiment = analyzer.analyze_text_finbert("This is a positive statement")
        
        # Mock fallback should return a reasonable value
        assert isinstance(sentiment, float)
        assert -1.0 <= sentiment <= 1.0
    
    @patch('backend.data.social_sentiment.NLP_AVAILABLE', True)
    def test_analyze_text_finbert_with_model(self, analyzer):
        """Test sentiment analysis with actual model"""
        # Mock the pipeline
        mock_pipeline = Mock()
        mock_pipeline.return_value = [{"label": "POSITIVE", "score": 0.8}]
        analyzer.finbert_pipeline = mock_pipeline
        analyzer.model_loaded = True
        
        sentiment = analyzer.analyze_text_finbert("Great stock performance!")
        
        assert isinstance(sentiment, float)
        mock_pipeline.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
