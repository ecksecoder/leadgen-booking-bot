"""Context triage engine for LeadGen & Booking Bot.

This module provides an isolated classification pipeline that evaluates incoming
lead context (free-form client commentary and requested service) against
niche-specific triage rules configured in 'business_profile.json'. It also supports
an extensible hook for optional LLM-driven categorization.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Default path to the external business configuration file
DEFAULT_PROFILE_PATH: Path = Path(__file__).resolve().parent / "business_profile.json"

# Type alias for custom LLM classification hook callable
# Callable signature: (comment_text: str, service: Optional[str]) -> Optional[str] (returning tag name)
LLMClassifierHook = Callable[[str, Optional[str]], Optional[str]]

# Module-level registry for optional LLM classifier hook
_CUSTOM_LLM_HOOK: Optional[LLMClassifierHook] = None

# Fallback configuration in case business_profile.json is absent or malformed
FALLBACK_DEFAULT_RULE: Dict[str, str] = {
    "tag": "STANDARD",
    "admin_alert_prefix": "📋 STANDARD",
    "custom_user_reply": (
        "✅ <b>Заявка принята (STANDARD)</b>\n"
        "Спасибо за предоставленную информацию! Наш специалист свяжется с вами "
        "в ближайшее рабочее время для уточнения деталей."
    ),
}


def register_llm_classifier(hook: Optional[LLMClassifierHook]) -> None:
    """Register or deregister an extensible LLM classification hook.

    Args:
        hook: Callable receiving (comment_text, service) and returning a tag string,
            or None to disable LLM classification.
    """
    global _CUSTOM_LLM_HOOK
    _CUSTOM_LLM_HOOK = hook
    if hook is not None:
        logger.info("Custom LLM classification hook registered successfully.")
    else:
        logger.info("Custom LLM classification hook cleared.")


def load_business_profile(
    profile_path: Union[str, Path] = DEFAULT_PROFILE_PATH,
) -> Dict[str, Any]:
    """Load and parse the external business profile JSON configuration.

    Args:
        profile_path: Filesystem path to business_profile.json.

    Returns:
        Dict[str, Any]: Parsed configuration dictionary. Returns an empty dict
        on read or deserialization failure to preserve bot uptime.
    """
    path_obj = Path(profile_path).resolve()
    if not path_obj.is_file():
        logger.warning(
            "Business profile configuration not found at '%s'. Using fallback rules.",
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
    comment_text: Optional[str],
    service: Optional[str] = None,
    profile_path: Union[str, Path] = DEFAULT_PROFILE_PATH,
) -> Dict[str, str]:
    """Evaluate client commentary and requested service against business rules.

    Checks optional LLM classification first, followed by pattern/keyword matching
    against priority-ordered rules in 'business_profile.json'. Falls back to the
    default triage specification if no match is identified or comment is empty.

    Args:
        comment_text: Free-form text provided by the client, or None if skipped.
        service: Name of the service selected by the client.
        profile_path: Filesystem path to the business profile configuration.

    Returns:
        Dict[str, str]: Structured categorization payload containing:
            - 'context_tag': String identifier ('URGENT_VIP', 'PRICE_INQUIRY', etc.)
            - 'custom_user_reply': Tailored reply message for the client.
            - 'admin_alert_prefix': Urgent badge/prefix for administrator notifications.
    """
    profile = load_business_profile(profile_path)
    triage_config: Dict[str, Any] = profile.get("context_triage", {})
    rules: List[Dict[str, Any]] = triage_config.get("rules", [])
    default_config: Dict[str, str] = triage_config.get(
        "default", FALLBACK_DEFAULT_RULE
    )

    default_result: Dict[str, str] = {
        "context_tag": str(default_config.get("tag", "STANDARD")),
        "custom_user_reply": str(
            default_config.get(
                "custom_user_reply",
                FALLBACK_DEFAULT_RULE["custom_user_reply"],
            )
        ),
        "admin_alert_prefix": str(
            default_config.get(
                "admin_alert_prefix",
                FALLBACK_DEFAULT_RULE["admin_alert_prefix"],
            )
        ),
    }

    # Handle empty or skipped commentary
    cleaned_comment = (comment_text or "").strip()
    if not cleaned_comment:
        return default_result

    # 1. Extensible Hook: Optional LLM-driven classification
    if _CUSTOM_LLM_HOOK is not None:
        try:
            llm_tag = _CUSTOM_LLM_HOOK(cleaned_comment, service)
            if llm_tag:
                normalized_llm_tag = llm_tag.strip().upper()
                for rule in rules:
                    if str(rule.get("tag", "")).upper() == normalized_llm_tag:
                        logger.info(
                            "LLM classifier hook categorized comment as '%s'.",
                            normalized_llm_tag,
                        )
                        return {
                            "context_tag": str(rule.get("tag", normalized_llm_tag)),
                            "custom_user_reply": str(
                                rule.get("custom_user_reply", default_result["custom_user_reply"])
                            ),
                            "admin_alert_prefix": str(
                                rule.get("admin_alert_prefix", default_result["admin_alert_prefix"])
                            ),
                        }
        except Exception as llm_exc:
            logger.warning(
                "Custom LLM classification hook execution failed: %s. Falling back to rule engine.",
                llm_exc,
            )

    # 2. Rule Engine: Priority-ordered keyword and regex pattern matching
    # Sort rules ascending by priority (1 is highest priority)
    sorted_rules = sorted(rules, key=lambda item: item.get("priority", 999))
    lowered_comment = cleaned_comment.lower()

    for rule in sorted_rules:
        tag = str(rule.get("tag", "STANDARD"))
        keywords: List[str] = rule.get("keywords", [])
        for kw in keywords:
            cleaned_kw = kw.strip().lower()
            if not cleaned_kw:
                continue

            # Check boundary match or substring inclusion for multi-word or punctuation expressions
            pattern = rf"(?i)\b{re.escape(cleaned_kw)}\b"
            if re.search(pattern, cleaned_comment) or cleaned_kw in lowered_comment:
                logger.info(
                    "Lead context matched triage rule '%s' via keyword '%s'.",
                    tag,
                    cleaned_kw,
                )
                return {
                    "context_tag": tag,
                    "custom_user_reply": str(
                        rule.get("custom_user_reply", default_result["custom_user_reply"])
                    ),
                    "admin_alert_prefix": str(
                        rule.get("admin_alert_prefix", default_result["admin_alert_prefix"])
                    ),
                }

    # 3. Fallback: Default STANDARD categorization
    return default_result
