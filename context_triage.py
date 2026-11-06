"""Context triage engine for LeadGen & Booking Bot.

Provides a deterministic rule-based lead scoring and classification pipeline that
evaluates incoming client commentary and requested services against niche-specific
scoring rules configured in 'business_profile.json'. Returns structured triage tags,
numeric qualification scores, localized auto-replies, and administrator urgency badges.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from locales import get_text

logger = logging.getLogger(__name__)

# Default path to external business configuration file
DEFAULT_PROFILE_PATH: Path = Path(__file__).resolve().parent / "business_profile.json"

DEFAULT_TIERS: Dict[str, Dict[str, Any]] = {
    "URGENT_VIP": {
        "priority": 1,
        "score": 100,
        "admin_alert_prefix": "🔥 URGENT_VIP",
        "keywords": [
            "срочно", "urgent", "asap", "горит", "сегодня", "сейчас", "быстро",
            "авария", "vip", "критично", "critical", "не работает", "поломка",
            "упал", "emergency", "sos", "deadline", "терміново", "термінова",
            "не працює", "зламалося", "швидко", "сьогодні", "зараз",
        ],
    },
    "PRICE_INQUIRY": {
        "priority": 2,
        "score": 70,
        "admin_alert_prefix": "💰 PRICE_INQUIRY",
        "keywords": [
            "цена", "стоимость", "сколько стоит", "прайс", "расценки", "price",
            "cost", "how much", "rate", "quote", "бюджет", "budget", "тариф",
            "скидка", "расчет", "смета", "калькуляция", "ціна", "вартість",
            "скільки коштує", "кошторис", "знижка", "розрахунок",
        ],
    },
    "LOW_PRIORITY": {
        "priority": 3,
        "score": 30,
        "admin_alert_prefix": "⏳ LOW_PRIORITY",
        "keywords": [
            "не к спеху", "потом", "на будущее", "просто спросить", "любопытно",
            "later", "low priority", "just asking", "someday", "не срочно",
            "когда-нибудь", "на следующий месяц", "не горит", "планирую позже",
            "не до поспіху", "пізніше", "на майбутнє", "просто запитати",
            "колись", "не терміново",
        ],
    },
    "STANDARD": {
        "priority": 4,
        "score": 10,
        "admin_alert_prefix": "📋 STANDARD",
        "keywords": [],
    },
}


def load_business_profile(
    profile_path: Union[str, Path] = DEFAULT_PROFILE_PATH,
) -> Dict[str, Any]:
    """Load and parse the external business profile JSON configuration.

    Args:
        profile_path: Filesystem path to business_profile.json.

    Returns:
        Dict[str, Any]: Parsed configuration dictionary. Returns fallback structure
        on read or deserialization failure to preserve uptime.
    """
    path_obj = Path(profile_path).resolve()
    if not path_obj.is_file():
        logger.warning(
            "Business profile configuration not found at '%s'. Using built-in default rules.",
            path_obj,
        )
        return {}

    try:
        with open(path_obj, mode="r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
            if not isinstance(data, dict):
                logger.error("Root element of '%s' is not a JSON object.", path_obj)
                return {}
            return data
    except Exception as exc:
        logger.error(
            "Failed to load business profile configuration from '%s': %s",
            path_obj,
            exc,
            exc_info=True,
        )
        return {}


def analyze_lead_context(
    comment_text: Optional[str] = None,
    service: Optional[str] = None,
    profile_path: Union[str, Path] = DEFAULT_PROFILE_PATH,
    lang: str = "en",
    *,
    comment: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Evaluate client commentary and requested service against business rules.

    Performs deterministic pattern/keyword matching against priority-ordered rules
    in 'business_profile.json', returning structured categorization tags
    (URGENT_VIP, PRICE_INQUIRY, LOW_PRIORITY, STANDARD) and numeric qualification scores.
    Resolves custom user reply strings trilingually based on the client's locale.

    Supports both (comment_text, service, profile_path, lang) and
    (comment, lang='en') invocation forms for API compatibility.

    Args:
        comment_text: Free-form commentary text provided by client (or None).
        service: Name of the service selected by client.
        profile_path: Filesystem path to business_profile.json.
        lang: Target locale code ('en', 'uk', 'ru') for auto-replies.
        comment: Keyword alias for commentary text.
        **kwargs: Optional additional parameters (e.g. lang override).

    Returns:
        Dict[str, Any]: Structured triage payload:
            - 'context_tag': Category string ('URGENT_VIP', 'PRICE_INQUIRY', etc.)
            - 'score': Numeric score integer (e.g., 100, 70, 30, 10).
            - 'priority': Priority ranking integer (1, 2, 3, 4).
            - 'custom_user_reply': Localized reply message formatted for client.
            - 'admin_alert_prefix': Urgent badge/prefix for administrator notifications.
    """
    raw_comment = comment if comment is not None else comment_text
    actual_lang = lang

    if isinstance(service, str) and service in ("en", "uk", "ru") and "lang" not in kwargs and lang == "en":
        actual_lang = service
        service = None

    if "lang" in kwargs:
        actual_lang = str(kwargs["lang"])

    profile = load_business_profile(profile_path)
    triage_config: Dict[str, Any] = profile.get("context_triage", {})
    configured_rules: List[Dict[str, Any]] = triage_config.get("rules", [])
    default_config: Dict[str, str] = triage_config.get("default", {})

    default_tag = str(default_config.get("tag", "STANDARD"))
    default_tier = DEFAULT_TIERS.get(default_tag, DEFAULT_TIERS["STANDARD"])
    default_alert_prefix = str(
        default_config.get("admin_alert_prefix", default_tier["admin_alert_prefix"])
    )
    default_reply = get_text(f"triage_{default_tag}", lang=actual_lang)

    default_result: Dict[str, Any] = {
        "context_tag": default_tag,
        "score": int(default_tier["score"]),
        "priority": int(default_tier["priority"]),
        "custom_user_reply": default_reply,
        "admin_alert_prefix": default_alert_prefix,
    }

    cleaned_comment = (raw_comment or "").strip()
    if not cleaned_comment:
        return default_result

    # Merge configured rules with built-in fallbacks if rule definitions are sparse
    rules_to_evaluate: List[Dict[str, Any]] = []
    if configured_rules:
        rules_to_evaluate = sorted(configured_rules, key=lambda r: r.get("priority", 999))
    else:
        for tag_name, meta in sorted(DEFAULT_TIERS.items(), key=lambda i: i[1]["priority"]):
            if tag_name != "STANDARD":
                rules_to_evaluate.append(
                    {
                        "tag": tag_name,
                        "priority": meta["priority"],
                        "score": meta["score"],
                        "keywords": meta["keywords"],
                        "admin_alert_prefix": meta["admin_alert_prefix"],
                    }
                )

    lowered_comment = cleaned_comment.lower()

    for rule in rules_to_evaluate:
        tag = str(rule.get("tag", "STANDARD"))
        rule_tier = DEFAULT_TIERS.get(tag, DEFAULT_TIERS.get("STANDARD", {}))
        priority_val = int(rule.get("priority", rule_tier.get("priority", 4)))
        score_val = int(rule.get("score", rule_tier.get("score", 10)))
        alert_prefix = str(rule.get("admin_alert_prefix", rule_tier.get("admin_alert_prefix", f"📋 {tag}")))

        keywords: List[str] = rule.get("keywords", [])
        matched_count = 0

        for kw in keywords:
            cleaned_kw = kw.strip().lower()
            if not cleaned_kw:
                continue

            pattern = rf"(?i)\b{re.escape(cleaned_kw)}\b"
            if re.search(pattern, cleaned_comment) or cleaned_kw in lowered_comment:
                matched_count += 1

        if matched_count > 0:
            logger.info(
                "Lead context matched triage tier '%s' (%d hits, score=%d, lang=%s).",
                tag,
                matched_count,
                score_val,
                actual_lang,
            )
            custom_reply = get_text(f"triage_{tag}", lang=actual_lang)
            if custom_reply == f"triage_{tag}":
                custom_reply = str(rule.get("custom_user_reply", default_reply))

            return {
                "context_tag": tag,
                "score": score_val,
                "priority": priority_val,
                "custom_user_reply": custom_reply,
                "admin_alert_prefix": alert_prefix,
            }

    return default_result
