"""
Tests for src/llm_analyzer.py
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.config import GeminiConfig
from src.llm_analyzer import LLMAnalyzer, AnalysisResult
from src.reddit_monitor import RedditPost


@pytest.fixture
def gemini_config():
    return GeminiConfig(api_key="test-key", model="gemini-1.5-flash")


@pytest.fixture
def sample_post():
    return RedditPost(
        post_id="abc123",
        subreddit="aws",
        title="Lambda@Edge cold start causing 3s latency – how to fix?",
        body=(
            "I'm running a Lambda@Edge function at CloudFront to do JWT validation. "
            "The cold start is adding ~3 seconds to my response time. "
            "I'm using Node.js 18, the function is 15MB. Any tips?"
        ),
        url="https://reddit.com/r/aws/abc123",
        author="devguy",
        score=15,
        num_comments=4,
        matched_keywords=["lambda", "cloudfront"],
    )


HIGH_VALUE_RESPONSE = json.dumps(
    {
        "is_high_value": True,
        "complexity_score": 8,
        "technical_tags": ["Lambda@Edge", "CloudFront", "JWT", "cold start"],
        "summary": "Developer experiencing Lambda@Edge cold start latency affecting JWT validation.",
        "reasoning": "This is a real production performance issue requiring knowledge of Lambda@Edge constraints.",
    }
)

LOW_VALUE_RESPONSE = json.dumps(
    {
        "is_high_value": False,
        "complexity_score": 2,
        "technical_tags": ["aws"],
        "summary": "General question about which cloud provider to learn.",
        "reasoning": "This is an opinion-based career question, not a technical gap.",
    }
)


def _make_client_mock(response_text: str):
    """Return a mock genai.Client whose models.generate_content returns response_text."""
    mock_response = MagicMock()
    mock_response.text = response_text

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response

    mock_client = MagicMock()
    mock_client.models = mock_models
    return mock_client


@patch("src.llm_analyzer.genai")
def test_analyze_high_value_post(mock_genai, gemini_config, sample_post):
    mock_genai.Client.return_value = _make_client_mock(HIGH_VALUE_RESPONSE)
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    result = analyzer.analyze(sample_post)

    assert result is not None
    assert result.is_high_value is True
    assert result.complexity_score == 8
    assert "Lambda@Edge" in result.technical_tags
    assert "cold start" in result.summary.lower()
    assert result.post_id == "abc123"


@patch("src.llm_analyzer.genai")
def test_analyze_low_value_post(mock_genai, gemini_config, sample_post):
    mock_genai.Client.return_value = _make_client_mock(LOW_VALUE_RESPONSE)
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    result = analyzer.analyze(sample_post)

    assert result is not None
    assert result.is_high_value is False
    assert result.complexity_score == 2


@patch("src.llm_analyzer.genai")
def test_analyze_returns_none_on_api_error(mock_genai, gemini_config, sample_post):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API error")
    mock_genai.Client.return_value = mock_client
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    result = analyzer.analyze(sample_post)

    assert result is None


@patch("src.llm_analyzer.genai")
def test_analyze_returns_none_on_invalid_json(mock_genai, gemini_config, sample_post):
    mock_genai.Client.return_value = _make_client_mock("this is not json")
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    result = analyzer.analyze(sample_post)

    assert result is None


@patch("src.llm_analyzer.genai")
def test_is_high_value_returns_true_for_high_value(mock_genai, gemini_config, sample_post):
    mock_genai.Client.return_value = _make_client_mock(HIGH_VALUE_RESPONSE)
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    is_hv, result = analyzer.is_high_value(sample_post)

    assert is_hv is True
    assert result is not None


@patch("src.llm_analyzer.genai")
def test_is_high_value_returns_false_for_low_value(mock_genai, gemini_config, sample_post):
    mock_genai.Client.return_value = _make_client_mock(LOW_VALUE_RESPONSE)
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    is_hv, result = analyzer.is_high_value(sample_post)

    assert is_hv is False


@patch("src.llm_analyzer.genai")
def test_is_high_value_returns_false_none_on_api_failure(mock_genai, gemini_config, sample_post):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API failure")
    mock_genai.Client.return_value = mock_client
    mock_genai.types = MagicMock()

    analyzer = LLMAnalyzer(gemini_config)
    is_hv, result = analyzer.is_high_value(sample_post)

    assert is_hv is False
    assert result is None


def test_analysis_result_str():
    result = AnalysisResult(
        post_id="xyz",
        is_high_value=True,
        complexity_score=9,
        technical_tags=["ECS", "Fargate"],
        summary="Container orchestration issue",
        reasoning="Complex multi-service architecture.",
        raw_response="{}",
    )
    s = str(result)
    assert "xyz" in s
    assert "9/10" in s
    assert "True" in s
