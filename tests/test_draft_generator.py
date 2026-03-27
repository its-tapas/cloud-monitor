"""
Tests for src/draft_generator.py
"""

import pytest
from unittest.mock import MagicMock, patch

from src.config import GeminiConfig
from src.draft_generator import DraftGenerator, DraftResponse
from src.llm_analyzer import AnalysisResult
from src.reddit_monitor import RedditPost


@pytest.fixture
def gemini_config():
    return GeminiConfig(api_key="test-key", model="gemini-1.5-flash", max_output_tokens=512)


@pytest.fixture
def sample_post():
    return RedditPost(
        post_id="post99",
        subreddit="aws",
        title="ECS task cannot access Secrets Manager",
        body=(
            "My ECS Fargate task is throwing AccessDeniedException when "
            "trying to retrieve secrets from Secrets Manager. "
            "The task role has the right policy but it still fails."
        ),
        url="https://reddit.com/r/aws/post99",
        author="clouddev",
        score=8,
        num_comments=3,
        matched_keywords=["ecs", "fargate"],
    )


@pytest.fixture
def sample_analysis():
    return AnalysisResult(
        post_id="post99",
        is_high_value=True,
        complexity_score=8,
        technical_tags=["ECS", "Fargate", "Secrets Manager", "IAM"],
        summary="ECS Fargate task cannot access Secrets Manager due to IAM issue.",
        reasoning="Likely a missing resource-based policy or VPC endpoint issue.",
        raw_response="{}",
    )


DRAFT_TEXT = (
    "## ECS Fargate + Secrets Manager AccessDeniedException\n\n"
    "This is usually caused by one of three things...\n\n"
    "```json\n{}\n```\n\n"
    "**TL;DR**: Check the task role and VPC endpoint configuration."
)


def _make_client_mock(response_text: str):
    mock_response = MagicMock()
    mock_response.text = response_text

    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response

    mock_client = MagicMock()
    mock_client.models = mock_models
    return mock_client


@patch("src.draft_generator.genai")
def test_generate_returns_draft_response(
    mock_genai, gemini_config, sample_post, sample_analysis
):
    mock_genai.Client.return_value = _make_client_mock(DRAFT_TEXT)
    mock_genai.types = MagicMock()

    gen = DraftGenerator(gemini_config)
    draft = gen.generate(sample_post, sample_analysis)

    assert draft is not None
    assert isinstance(draft, DraftResponse)
    assert draft.post_id == "post99"
    assert draft.post_title == sample_post.title
    assert draft.post_url == sample_post.url
    assert draft.draft_text == DRAFT_TEXT
    assert draft.complexity_score == 8


@patch("src.draft_generator.genai")
def test_generate_returns_none_on_api_error(
    mock_genai, gemini_config, sample_post, sample_analysis
):
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("Gemini down")
    mock_genai.Client.return_value = mock_client
    mock_genai.types = MagicMock()

    gen = DraftGenerator(gemini_config)
    draft = gen.generate(sample_post, sample_analysis)

    assert draft is None


@patch("src.draft_generator.genai")
def test_generate_passes_correct_context(
    mock_genai, gemini_config, sample_post, sample_analysis
):
    mock_client = _make_client_mock(DRAFT_TEXT)
    mock_genai.Client.return_value = mock_client
    mock_genai.types = MagicMock()

    gen = DraftGenerator(gemini_config)
    gen.generate(sample_post, sample_analysis)

    call_args = mock_client.models.generate_content.call_args.kwargs["contents"]
    assert "ECS task cannot access" in call_args
    assert "ECS" in call_args
    assert "Fargate" in call_args


def test_draft_response_format_for_notification():
    draft = DraftResponse(
        post_id="p1",
        post_title="My AWS Lambda question",
        post_url="https://reddit.com/r/aws/p1",
        analysis_summary="Lambda cold start affecting response time.",
        technical_tags=["Lambda", "CloudFront"],
        complexity_score=7,
        draft_text="Here is the expert answer...",
    )
    notification = draft.format_for_notification()

    assert "HIGH-VALUE TECHNICAL POST DETECTED" in notification
    assert "My AWS Lambda question" in notification
    assert "https://reddit.com/r/aws/p1" in notification
    assert "Lambda" in notification
    assert "7/10" in notification
    assert "Here is the expert answer" in notification
    assert "review" in notification.lower()


def test_draft_response_format_title_truncation():
    long_title = "A" * 100
    draft = DraftResponse(
        post_id="p2",
        post_title=long_title,
        post_url="https://reddit.com",
        analysis_summary="summary",
        technical_tags=[],
        complexity_score=8,
        draft_text="draft",
    )
    notification = draft.format_for_notification()
    # Title in the notification header should be truncated but the full title appears in body
    assert "A" * 60 in notification
