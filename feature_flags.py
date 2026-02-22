from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FeatureFlags:
    push_notifications_hook: bool = False
    deep_linking_hook: bool = False
    referral_hook: bool = False
    ab_testing_hook: bool = False
    premium_gating_hook: bool = False


def from_config(cfg: dict) -> FeatureFlags:
    def as_bool(key: str) -> bool:
        return str(cfg.get(key, "false")).strip().lower() == "true"

    return FeatureFlags(
        push_notifications_hook=as_bool("feature_push_notifications"),
        deep_linking_hook=as_bool("feature_deep_linking"),
        referral_hook=as_bool("feature_referrals"),
        ab_testing_hook=as_bool("feature_ab_testing"),
        premium_gating_hook=as_bool("feature_premium_gating"),
    )


def can_access_feature(*, cfg: dict, feature_key: str) -> bool:
    allowed = str(cfg.get(f"feature_{feature_key}_enabled", "true")).strip().lower()
    return allowed != "false"
