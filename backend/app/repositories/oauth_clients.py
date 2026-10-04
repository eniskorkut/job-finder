from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.oauth_client import OAuthClientConfig
from app.repositories.base import Repository


class OAuthClientRepository(Repository[OAuthClientConfig]):
    """[LEGACY / DEPRECATED] Repository for per-user OAuth application credentials.

    Kept for backward compatibility. The runtime flow now uses deployment-wide OAuth apps.
    """
    model = OAuthClientConfig

    def get_for_user_provider(
        self, user_id: uuid.UUID, provider: str
    ) -> OAuthClientConfig | None:
        stmt = select(OAuthClientConfig).where(
            OAuthClientConfig.user_id == user_id,
            OAuthClientConfig.provider == provider,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_for_user(self, user_id: uuid.UUID) -> list[OAuthClientConfig]:
        stmt = (
            select(OAuthClientConfig)
            .where(OAuthClientConfig.user_id == user_id)
            .order_by(OAuthClientConfig.provider)
        )
        return list(self.db.execute(stmt).scalars())

    def upsert(
        self,
        user_id: uuid.UUID,
        provider: str,
        *,
        client_id: str,
        client_secret_encrypted: str | None,
        tenant: str | None,
        redirect_uri: str | None,
    ) -> OAuthClientConfig:
        config = self.get_for_user_provider(user_id, provider)
        if config is None:
            config = OAuthClientConfig(
                user_id=user_id,
                provider=provider,
                client_id=client_id,
                client_secret_encrypted=client_secret_encrypted,
                tenant=tenant,
                redirect_uri=redirect_uri,
            )
            self.db.add(config)
        else:
            config.client_id = client_id
            if client_secret_encrypted is not None:
                config.client_secret_encrypted = client_secret_encrypted
            config.tenant = tenant
            config.redirect_uri = redirect_uri
        self.db.flush()
        return config

    def delete_for_user_provider(self, user_id: uuid.UUID, provider: str) -> bool:
        config = self.get_for_user_provider(user_id, provider)
        if config is None:
            return False
        self.db.delete(config)
        self.db.flush()
        return True
