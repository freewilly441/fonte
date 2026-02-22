# Release Readiness Notes

## Third-Pass Additions
- Durable runtime state (`data/app_state.json`) for QA draft, last tab, and docs page.
- In-flight request coordination and cancellation gates for async UI safety.
- Document list pagination (`DOCS_PAGE_SIZE=200`) with freshness indicator.
- Mutation lock for destructive actions to prevent duplicate submissions.
- Feature flag and premium gating hooks (config-driven, lightweight).
- Crash hook writing structured crash events to `data/crash.log`.
- Analytics payload redaction for sensitive fields.

## Scaling Pattern
1. Add a `RequestCoordinator` per screen with async operations.
2. Add `UiStateMachine` transitions for every user-visible state.
3. Use cache/page metadata to avoid full-list rendering.
4. Persist draft inputs and lightweight navigation context in `app_state`.
5. Track `screen_view`, `primary_action_tap`, `action_outcome`, `api_error`, `retry`, `time_to_value`.

## Operational Diagnostics
- Product telemetry: `data/analytics.log`
- Crash events: `data/crash.log`
- Runtime state snapshot: `data/app_state.json`

## Follow-up Rollout
- Apply pagination and request coordination to Search results if corpus volume grows.
- Add optional remote-config source while preserving local config fallback.
- Add support tooling for exporting diagnostics bundles from `data/`.
