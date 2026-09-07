"""Central policy for data that must never leave StudyOS in portable exports."""

from app.services import account_data

_SENSITIVE_INTEGRATION_TABLES = {
    "spotify_connections",
    "spotify_oauth_states",
}

# Integration credentials and transient OAuth state are account infrastructure,
# not portable academic data. Keep them out of both JSON exports and migration ZIPs.
account_data._EXPORT_EXCLUDED_TABLES.update(_SENSITIVE_INTEGRATION_TABLES)
account_data._MIGRATION_EXCLUDED_TABLES.update(_SENSITIVE_INTEGRATION_TABLES)
