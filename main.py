#!/usr/bin/env python3
"""
cloud-monitor – main entry point.

Orchestrates Reddit monitoring → LLM analysis → draft generation →
developer notification in a continuous polling loop.
"""

import logging
import time

from src.config import load_config
from src.draft_generator import DraftGenerator
from src.llm_analyzer import LLMAnalyzer
from src.notifier import Notifier, NotificationError
from src.reddit_monitor import RedditMonitor


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_once(
    monitor: RedditMonitor,
    analyzer: LLMAnalyzer,
    generator: DraftGenerator,
    notifier: Notifier,
) -> int:
    """
    Execute a single monitoring cycle.

    Returns the number of high-value posts processed in this cycle.
    """
    logger = logging.getLogger(__name__)
    posts = monitor.fetch_new_posts()
    processed = 0

    for post in posts:
        logger.info(
            "Analysing post %s from r/%s: '%s'",
            post.post_id,
            post.subreddit,
            post.title[:80],
        )

        is_hv, analysis = analyzer.is_high_value(post)
        if not is_hv or analysis is None:
            logger.info(
                "Post %s scored %s – not high-value, skipping.",
                post.post_id,
                analysis.complexity_score if analysis else "N/A",
            )
            continue

        logger.info(
            "Post %s is HIGH-VALUE (score=%d). Generating draft…",
            post.post_id,
            analysis.complexity_score,
        )

        draft = generator.generate(post, analysis)
        if draft is None:
            logger.error("Draft generation failed for post %s.", post.post_id)
            continue

        try:
            notifier.send_high_value_alert(draft)
            processed += 1
        except NotificationError as exc:
            logger.error("Notification error: %s", exc)

    return processed


def main() -> None:
    config = load_config()
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    logger.info("cloud-monitor starting up.")
    logger.info("Monitoring subreddits: %s", config.reddit.subreddits)
    logger.info("Poll interval: %d seconds", config.reddit.poll_interval_seconds)

    monitor = RedditMonitor(config.reddit)
    analyzer = LLMAnalyzer(config.gemini)
    generator = DraftGenerator(config.gemini)
    notifier = Notifier(config.notifier)

    while True:
        try:
            n = run_once(monitor, analyzer, generator, notifier)
            logger.info("Cycle complete. High-value posts processed: %d", n)
        except KeyboardInterrupt:
            logger.info("Shutdown requested – exiting.")
            break
        except Exception as exc:
            logger.exception("Unexpected error in monitoring cycle: %s", exc)

        logger.debug("Sleeping for %d seconds.", config.reddit.poll_interval_seconds)
        time.sleep(config.reddit.poll_interval_seconds)


if __name__ == "__main__":
    main()
