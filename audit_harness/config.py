# -*- coding: utf-8 -*-
"""
config.py — env/paths shared by every audit_harness script.

Loads /home/voiceagent/voice-ai/.env directly (no dependency on the running
service's process env) so this harness can run standalone, any time, without
needing voiceai.service to be up.

Note on the Supabase credential: enrich.py connects with AUDIT_HARNESS_DB_URL,
a direct Postgres connection string for the audit_readonly role -- GRANT
SELECT only, no INSERT/UPDATE/DELETE ever granted, verified live with a write
attempt that correctly raised InsufficientPrivilege. This is enforced by
Postgres itself, not application code, unlike the old approach of hitting the
REST API with SUPABASE_SERVICE_KEY and just not writing by discipline.
"""
import os

_ENV_PATH = "/home/voiceagent/voice-ai/.env"


def _load_env() -> dict:
    env = dict(os.environ)
    if os.path.exists(_ENV_PATH):
        for line in open(_ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k, v)
    return env


_env = _load_env()

AUDIT_HARNESS_DB_URL = _env.get("AUDIT_HARNESS_DB_URL", "")
TENANT_ID    = _env.get("TENANT_ID", "krishna_furniture")

HARNESS_DIR   = "/home/voiceagent/voice-ai/audit_harness"
DB_PATH       = os.path.join(HARNESS_DIR, "audit.db")
AUDIT_LOG_PATH = "/home/voiceagent/voice-ai/logs/audit.jsonl"

CALL_START_HOUR_IST = 10
CALL_END_HOUR_BY_FUNNEL_IST = {
    "fresh_cta": 22,
}
CALL_END_HOUR_DEFAULT_IST = 20
