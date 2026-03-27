"""
Reddit monitoring module.

Uses PRAW to stream new posts from configured subreddits and applies
keyword-based pre-filtering before deeper LLM analysis.
"""

import logging
from dataclasses import dataclass
from typing import Iterator, List, Optional, Set

import praw

from .config import RedditConfig

logger = logging.getLogger(__name__)

# High-complexity keywords that indicate AWS/GCP/Python technical content
AWS_KEYWORDS: Set[str] = {
    "aws",
    "ec2",
    "s3",
    "lambda",
    "ecs",
    "eks",
    "fargate",
    "cloudformation",
    "terraform",
    "iam",
    "vpc",
    "rds",
    "aurora",
    "dynamodb",
    "sqs",
    "sns",
    "kinesis",
    "glue",
    "athena",
    "redshift",
    "emr",
    "sagemaker",
    "bedrock",
    "cloudwatch",
    "api gateway",
    "load balancer",
    "alb",
    "nlb",
    "cloudfront",
    "route53",
    "elasticache",
    "elasticsearchservice",
    "opensearch",
    "msk",
    "step functions",
    "eventbridge",
    "cdk",
    "sam",
    "serverless",
}

GCP_KEYWORDS: Set[str] = {
    "gcp",
    "google cloud",
    "bigquery",
    "cloud run",
    "cloud functions",
    "gke",
    "compute engine",
    "cloud storage",
    "pubsub",
    "pub/sub",
    "dataflow",
    "dataproc",
    "cloud sql",
    "spanner",
    "firestore",
    "bigtable",
    "vertex ai",
    "cloud build",
    "artifact registry",
    "cloud armor",
    "vpc service controls",
    "cloud composer",
    "looker",
}

PYTHON_KEYWORDS: Set[str] = {
    "python",
    "fastapi",
    "django",
    "flask",
    "pydantic",
    "sqlalchemy",
    "celery",
    "airflow",
    "spark",
    "pyspark",
    "pandas",
    "dask",
    "asyncio",
    "aiohttp",
    "boto3",
    "google-cloud",
    "data engineering",
    "data pipeline",
    "etl",
    "elt",
    "microservices",
    "kubernetes",
    "docker",
}

ALL_TECHNICAL_KEYWORDS: Set[str] = AWS_KEYWORDS | GCP_KEYWORDS | PYTHON_KEYWORDS


@dataclass
class RedditPost:
    """Represents a Reddit post flagged for analysis."""

    post_id: str
    subreddit: str
    title: str
    body: str
    url: str
    author: str
    score: int
    num_comments: int
    matched_keywords: List[str]

    @property
    def full_text(self) -> str:
        return f"{self.title}\n\n{self.body}".strip()


def _extract_keywords(text: str) -> List[str]:
    """Return the technical keywords found in *text* (case-insensitive)."""
    lower = text.lower()
    return [kw for kw in ALL_TECHNICAL_KEYWORDS if kw in lower]


def _submission_text(submission: praw.models.Submission) -> str:
    """Return the combined title and body text of a submission."""
    return f"{submission.title} {submission.selftext or ''}"


def _build_reddit_client(config: RedditConfig) -> praw.Reddit:
    return praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        user_agent=config.user_agent,
        # Read-only mode – no username/password required
    )


def _post_from_submission(
    submission: praw.models.Submission,
    matched_keywords: List[str],
) -> RedditPost:
    body = submission.selftext or ""
    author = str(submission.author) if submission.author else "[deleted]"
    return RedditPost(
        post_id=submission.id,
        subreddit=str(submission.subreddit),
        title=submission.title,
        body=body,
        url=submission.url,
        author=author,
        score=submission.score,
        num_comments=submission.num_comments,
        matched_keywords=matched_keywords,
    )


class RedditMonitor:
    """
    Monitors multiple subreddits for new technical posts.

    Posts are pre-filtered by keyword matching before being yielded for
    deeper LLM analysis.
    """

    def __init__(self, config: RedditConfig, reddit: Optional[praw.Reddit] = None):
        self.config = config
        self._reddit = reddit or _build_reddit_client(config)
        self._seen_ids: Set[str] = set()

    def _subreddit_combined(self) -> praw.models.SubredditHelper:
        combined = "+".join(self.config.subreddits)
        return self._reddit.subreddit(combined)

    def fetch_new_posts(self) -> List[RedditPost]:
        """
        Fetch recent posts from all configured subreddits, apply keyword
        pre-filtering, and return only posts not previously seen.
        """
        subreddit = self._subreddit_combined()
        results: List[RedditPost] = []

        try:
            for submission in subreddit.new(limit=self.config.post_limit):
                if submission.id in self._seen_ids:
                    continue
                self._seen_ids.add(submission.id)

                text = _submission_text(submission)
                keywords = _extract_keywords(text)
                if keywords:
                    post = _post_from_submission(submission, keywords)
                    results.append(post)
                    logger.debug(
                        "Flagged post %s ('%s') with keywords: %s",
                        submission.id,
                        submission.title[:60],
                        keywords,
                    )
        except Exception as exc:
            logger.error("Error fetching posts from Reddit: %s", exc)

        logger.info(
            "Fetched %d technical post(s) from subreddits: %s",
            len(results),
            self.config.subreddits,
        )
        return results

    def stream_new_posts(self) -> Iterator[RedditPost]:
        """
        Yield posts continuously using PRAW's built-in streaming.

        This is an infinite iterator – run in a background thread or process.
        """
        subreddit = self._subreddit_combined()
        logger.info("Starting stream for subreddits: %s", self.config.subreddits)

        for submission in subreddit.stream.submissions(skip_existing=True):
            text = _submission_text(submission)
            keywords = _extract_keywords(text)
            if keywords:
                post = _post_from_submission(submission, keywords)
                logger.debug(
                    "Stream: flagged post %s with keywords: %s",
                    submission.id,
                    keywords,
                )
                yield post
