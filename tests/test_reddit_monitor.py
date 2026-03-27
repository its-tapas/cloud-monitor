"""
Tests for src/reddit_monitor.py
"""

from unittest.mock import MagicMock, patch

import pytest

from src.reddit_monitor import (
    RedditMonitor,
    RedditPost,
    _extract_keywords,
    AWS_KEYWORDS,
    GCP_KEYWORDS,
    PYTHON_KEYWORDS,
)
from src.config import RedditConfig


@pytest.fixture
def reddit_config():
    return RedditConfig(
        client_id="cid",
        client_secret="csecret",
        user_agent="test-agent/1.0",
        subreddits=["aws", "gcpcloud", "developersIndia"],
        post_limit=10,
        poll_interval_seconds=60,
    )


# ---------------------------------------------------------------------------
# Keyword extraction tests
# ---------------------------------------------------------------------------


def test_extract_keywords_aws():
    text = "How do I configure an IAM role for an EC2 instance to access S3?"
    keywords = _extract_keywords(text)
    assert "iam" in keywords
    assert "ec2" in keywords
    assert "s3" in keywords


def test_extract_keywords_gcp():
    text = "BigQuery vs Redshift – which is better for analytics at scale?"
    keywords = _extract_keywords(text)
    assert "bigquery" in keywords
    assert "redshift" in keywords


def test_extract_keywords_python():
    text = "Building an async data pipeline with FastAPI and Celery."
    keywords = _extract_keywords(text)
    assert "fastapi" in keywords
    assert "celery" in keywords


def test_extract_keywords_case_insensitive():
    text = "AWS Lambda triggered by SQS"
    keywords = _extract_keywords(text)
    assert "lambda" in keywords
    assert "sqs" in keywords


def test_extract_keywords_no_match():
    text = "What should I have for lunch today?"
    assert _extract_keywords(text) == []


def test_extract_keywords_combined():
    text = "Deploying a Python FastAPI app on AWS ECS with Terraform and RDS Aurora."
    keywords = _extract_keywords(text)
    for kw in ["python", "fastapi", "ecs", "terraform", "rds", "aurora"]:
        assert kw in keywords


# ---------------------------------------------------------------------------
# RedditPost tests
# ---------------------------------------------------------------------------


def test_reddit_post_full_text():
    post = RedditPost(
        post_id="abc123",
        subreddit="aws",
        title="Lambda cold starts",
        body="My Lambda function takes 3s to cold start.",
        url="https://reddit.com/r/aws/abc123",
        author="devguy",
        score=5,
        num_comments=2,
        matched_keywords=["lambda"],
    )
    assert "Lambda cold starts" in post.full_text
    assert "3s to cold start" in post.full_text


def test_reddit_post_full_text_no_body():
    post = RedditPost(
        post_id="abc",
        subreddit="aws",
        title="Help with VPC",
        body="",
        url="https://reddit.com",
        author="user",
        score=0,
        num_comments=0,
        matched_keywords=["vpc"],
    )
    assert post.full_text == "Help with VPC"


# ---------------------------------------------------------------------------
# RedditMonitor tests
# ---------------------------------------------------------------------------


def _make_submission(
    sid="post1",
    title="AWS Lambda cold start issue",
    selftext="My function takes too long to start.",
    score=10,
    num_comments=3,
    subreddit_name="aws",
    author="testuser",
):
    submission = MagicMock()
    submission.id = sid
    submission.title = title
    submission.selftext = selftext
    submission.score = score
    submission.num_comments = num_comments
    submission.url = f"https://reddit.com/r/{subreddit_name}/{sid}"
    submission.author = MagicMock()
    submission.author.__str__ = lambda self: author
    submission.subreddit = MagicMock()
    submission.subreddit.__str__ = lambda self: subreddit_name
    return submission


def test_fetch_new_posts_returns_matching(reddit_config):
    aws_submission = _make_submission(title="AWS Lambda cold start issue", selftext="Lambda ecs fargate")
    non_technical_submission = _make_submission(sid="post2", title="What to eat today?", selftext="pizza or pasta")
    gcp_submission = _make_submission(
        sid="post3", title="GCP BigQuery performance", selftext="bigquery slow query"
    )

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value.new.return_value = [
        aws_submission,
        non_technical_submission,
        gcp_submission,
    ]

    monitor = RedditMonitor(reddit_config, reddit=mock_reddit)
    posts = monitor.fetch_new_posts()

    # non_technical_submission has no technical keywords → filtered out
    assert len(posts) == 2
    ids = [p.post_id for p in posts]
    assert "post1" in ids
    assert "post3" in ids
    assert "post2" not in ids


def test_fetch_new_posts_deduplication(reddit_config):
    duplicate_submission = _make_submission()

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value.new.return_value = [duplicate_submission]

    monitor = RedditMonitor(reddit_config, reddit=mock_reddit)

    first = monitor.fetch_new_posts()
    second = monitor.fetch_new_posts()

    assert len(first) == 1
    assert len(second) == 0  # already seen


def test_fetch_new_posts_handles_api_error(reddit_config):
    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value.new.side_effect = Exception("Reddit API down")

    monitor = RedditMonitor(reddit_config, reddit=mock_reddit)
    posts = monitor.fetch_new_posts()

    assert posts == []


def test_fetch_new_posts_deleted_author(reddit_config):
    deleted_author_submission = _make_submission()
    deleted_author_submission.author = None

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value.new.return_value = [deleted_author_submission]

    monitor = RedditMonitor(reddit_config, reddit=mock_reddit)
    posts = monitor.fetch_new_posts()

    assert posts[0].author == "[deleted]"


def test_fetch_new_posts_uses_combined_subreddits(reddit_config):
    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value.new.return_value = []

    monitor = RedditMonitor(reddit_config, reddit=mock_reddit)
    monitor.fetch_new_posts()

    mock_reddit.subreddit.assert_called_once_with("aws+gcpcloud+developersIndia")
