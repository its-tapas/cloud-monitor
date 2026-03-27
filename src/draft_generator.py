"""
Draft response generator.

Uses Google Gemini to produce a preliminary expert-level technical answer
for a High-Value post. The draft is deliberately verbose and structured so
that the human reviewer can quickly fact-check and refine it.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from .config import GeminiConfig
from .llm_analyzer import AnalysisResult
from .reddit_monitor import RedditPost

logger = logging.getLogger(__name__)

DRAFT_SYSTEM_PROMPT = """
You are a senior cloud architect and Python backend engineer with deep expertise in:
- AWS (EC2, ECS/EKS, Lambda, RDS/Aurora, DynamoDB, S3, SQS/SNS/Kinesis, Glue, Athena,
  Redshift, IAM, VPC, CloudFormation/CDK/Terraform, API Gateway, CloudFront, Route 53)
- Google Cloud Platform (BigQuery, Cloud Run, GKE, Cloud Functions, Pub/Sub, Dataflow,
  Cloud SQL, Spanner, Vertex AI, Cloud Composer, Cloud Build)
- Python data engineering (FastAPI, Django, Celery, Airflow, Spark/PySpark, Pandas,
  SQLAlchemy, Pydantic, asyncio)

Your task is to write a detailed, production-grade Reddit reply for a developer who is
genuinely stuck on a technical problem. The reply will be reviewed and refined by a human
expert before being posted.

Guidelines for the draft:
1. Start with a brief acknowledgement of the specific issue.
2. Explain the root cause or the architectural consideration that is most relevant.
3. Provide a concrete solution with code snippets, CLI commands, or configuration
   examples where appropriate (use Markdown formatting for code blocks).
4. Reference the relevant official documentation sections by name (e.g.
   "AWS IAM User Guide – Policies and permissions", "GCP Cloud Run docs – Concurrency").
   Do NOT invent or hallucinate URLs.
5. Highlight common pitfalls and how to avoid them.
6. Keep the tone professional but approachable – this is a community reply.
7. End with a short "TL;DR" summary.

Important: produce ONLY the reply text (Markdown). Do not include any meta-commentary
about your role or the review process.
"""


@dataclass
class DraftResponse:
    """A preliminary expert draft for a High-Value Reddit post."""

    post_id: str
    post_title: str
    post_url: str
    analysis_summary: str
    technical_tags: list
    complexity_score: int
    draft_text: str

    def format_for_notification(self) -> str:
        """Return a human-readable string suitable for an email or Telegram message."""
        tags = ", ".join(self.technical_tags) if self.technical_tags else "N/A"
        return (
            f"🚨 HIGH-VALUE TECHNICAL POST DETECTED\n"
            f"{'=' * 60}\n\n"
            f"📌 Title : {self.post_title}\n"
            f"🔗 URL   : {self.post_url}\n"
            f"🏷  Tags  : {tags}\n"
            f"📊 Score : {self.complexity_score}/10\n\n"
            f"📝 Summary:\n{self.analysis_summary}\n\n"
            f"{'=' * 60}\n"
            f"✏️  DRAFT RESPONSE (for your review):\n"
            f"{'=' * 60}\n\n"
            f"{self.draft_text}\n\n"
            f"{'=' * 60}\n"
            f"Please review, fact-check, and post the refined answer on Reddit.\n"
        )


class DraftGenerator:
    """
    Generates a human-reviewable expert draft for a Reddit post flagged as
    High-Value by the :class:`~src.llm_analyzer.LLMAnalyzer`.
    """

    def __init__(self, config: GeminiConfig):
        self.config = config
        self._client = genai.Client(api_key=config.api_key)
        self._generate_config = types.GenerateContentConfig(
            system_instruction=DRAFT_SYSTEM_PROMPT,
            temperature=config.draft_temperature,
            max_output_tokens=config.max_output_tokens,
        )

    def generate(
        self,
        post: RedditPost,
        analysis: AnalysisResult,
    ) -> Optional[DraftResponse]:
        """
        Generate a draft response for *post* using context from *analysis*.

        Returns a :class:`DraftResponse` on success, or ``None`` on API failure.
        """
        prompt = (
            f"Subreddit: r/{post.subreddit}\n"
            f"Post title: {post.title}\n\n"
            f"Post body:\n{post.body or '(no body text)'}\n\n"
            f"Technical analysis:\n"
            f"  - Core issue: {analysis.summary}\n"
            f"  - Technologies: {', '.join(analysis.technical_tags)}\n"
            f"  - Complexity score: {analysis.complexity_score}/10\n\n"
            "Please write the expert Reddit reply as described in your system instructions."
        )

        try:
            response = self._client.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=self._generate_config,
            )
            draft_text = response.text.strip()
            logger.debug("Draft generated for post %s (%d chars)", post.post_id, len(draft_text))
        except Exception as exc:
            logger.error(
                "Gemini API error while generating draft for post %s: %s",
                post.post_id,
                exc,
            )
            return None

        return DraftResponse(
            post_id=post.post_id,
            post_title=post.title,
            post_url=post.url,
            analysis_summary=analysis.summary,
            technical_tags=analysis.technical_tags,
            complexity_score=analysis.complexity_score,
            draft_text=draft_text,
        )
