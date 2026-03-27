"""
LLM analysis module using Google Gemini.

Analyses pre-filtered Reddit posts to determine whether they represent a
'High-Value Technical Gap' – a production-level cloud or Python question
where the author is genuinely stuck and would benefit from expert guidance.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

from google import genai
from google.genai import types

from .config import GeminiConfig
from .reddit_monitor import RedditPost

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """
You are an expert cloud architect and Python backend engineer who evaluates
Reddit posts from technical subreddits (r/AWS, r/gcpcloud, r/developersIndia).

Your task is to assess whether a given post represents a 'High-Value Technical Gap':
a situation where a developer is genuinely stuck on a complex, production-relevant
cloud architecture or Python data-engineering problem, and where an expert answer
would meaningfully improve the quality of discourse.

Criteria for HIGH value (score 7-10):
- The author is clearly stuck on a real architectural, performance, or operational issue.
- The problem involves non-trivial AWS/GCP service integrations, IAM policies, networking,
  distributed systems, data pipelines, or Python backend patterns.
- A correct, well-reasoned answer is not trivially Google-able and requires genuine expertise.
- The question is specific and technical (not "which cloud should I learn?").

Criteria for MEDIUM value (score 4-6):
- Moderately complex setup or configuration question.
- Clear technical content but likely answerable with a short documentation reference.

Criteria for LOW value (score 1-3):
- Opinion or career advice question.
- Very basic or introductory question.
- Vague or incomplete problem description.
- Off-topic or spam.

Respond ONLY with valid JSON in the following schema (no markdown, no extra text):
{
  "is_high_value": <true|false>,
  "complexity_score": <integer 1-10>,
  "technical_tags": [<list of specific services/technologies mentioned>],
  "summary": "<one-sentence description of the core technical problem>",
  "reasoning": "<two to three sentences explaining your assessment>"
}
"""


@dataclass
class AnalysisResult:
    """Result of LLM analysis for a single Reddit post."""

    post_id: str
    is_high_value: bool
    complexity_score: int
    technical_tags: list
    summary: str
    reasoning: str
    raw_response: str

    HIGH_VALUE_THRESHOLD = 7

    def __str__(self) -> str:
        return (
            f"Post {self.post_id}: score={self.complexity_score}/10 "
            f"high_value={self.is_high_value}\n"
            f"Summary: {self.summary}\n"
            f"Tags: {', '.join(self.technical_tags)}"
        )


class LLMAnalyzer:
    """
    Uses Google Gemini to evaluate whether a Reddit post is a High-Value
    Technical Gap that warrants expert intervention.
    """

    def __init__(self, config: GeminiConfig):
        self.config = config
        self._client = genai.Client(api_key=config.api_key)
        self._generate_config = types.GenerateContentConfig(
            system_instruction=ANALYSIS_SYSTEM_PROMPT,
            temperature=config.analysis_temperature,
            max_output_tokens=512,
            response_mime_type="application/json",
        )

    def analyze(self, post: RedditPost) -> Optional[AnalysisResult]:
        """
        Analyse *post* with Gemini.

        Returns an :class:`AnalysisResult` on success, or ``None`` if the API
        call fails or the response cannot be parsed.
        """
        prompt = (
            f"Subreddit: r/{post.subreddit}\n"
            f"Title: {post.title}\n\n"
            f"Post body:\n{post.body or '(no body text)'}\n\n"
            f"Pre-identified keywords: {', '.join(post.matched_keywords)}"
        )

        try:
            response = self._client.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=self._generate_config,
            )
            raw = response.text.strip()
            logger.debug("Gemini raw analysis for %s: %s", post.post_id, raw)
        except Exception as exc:
            logger.error("Gemini API error while analysing post %s: %s", post.post_id, exc)
            return None

        try:
            data = json.loads(raw)
            return AnalysisResult(
                post_id=post.post_id,
                is_high_value=bool(data.get("is_high_value", False)),
                complexity_score=int(data.get("complexity_score", 0)),
                technical_tags=list(data.get("technical_tags", [])),
                summary=str(data.get("summary", "")),
                reasoning=str(data.get("reasoning", "")),
                raw_response=raw,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error(
                "Failed to parse Gemini response for post %s: %s\nRaw: %s",
                post.post_id,
                exc,
                raw,
            )
            return None

    def is_high_value(self, post: RedditPost) -> tuple[bool, Optional[AnalysisResult]]:
        """
        Convenience wrapper that returns ``(True, result)`` when the post
        meets the high-value threshold, otherwise ``(False, result)``.
        """
        result = self.analyze(post)
        if result is None:
            return False, None
        return result.is_high_value, result
