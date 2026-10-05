"""Tests for Beszel integration setup and migration."""

import unittest
from uuid import uuid4

from support import FakeHomeAssistant

from custom_components.beszel import async_migrate_entry
from custom_components.beszel.const import DOMAIN


class MockConfigEntry:
    """Minimal config entry used by migration tests."""

    def __init__(self, *, data, domain, unique_id, version):
        self.data = data
        self.domain = domain
        self.entry_id = uuid4().hex
        self.unique_id = unique_id
        self.version = version


class BeszelMigrationTests(unittest.IsolatedAsyncioTestCase):
    """Exercise Beszel config-entry migrations."""

    async def test_future_config_version_is_rejected(self):
        """A downgrade must not accept an unknown config-entry schema."""
        entry = MockConfigEntry(
            data={"future": "value"},
            domain=DOMAIN,
            unique_id="future",
            version=3,
        )

        self.assertFalse(await async_migrate_entry(FakeHomeAssistant(), entry))
        self.assertEqual(entry.data, {"future": "value"})
        self.assertEqual(entry.version, 3)

    async def test_current_config_version_is_unchanged(self):
        """Current config entries need no migration."""
        entry = MockConfigEntry(
            data={"host": "http://beszel.local"},
            domain=DOMAIN,
            unique_id="current",
            version=2,
        )

        self.assertTrue(await async_migrate_entry(FakeHomeAssistant(), entry))
        self.assertEqual(entry.data, {"host": "http://beszel.local"})

    async def test_migrate_legacy_config_and_identifiers(self):
        """Version one entries retain entities with scoped identifiers."""
        hass = FakeHomeAssistant()
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "Host": "beszel.local/",
                "Password": "password",
                "Username": "user",
            },
            unique_id="beszel.local/_user",
            version=1,
        )
        entity_registry = hass.entity_registry
        entity = entity_registry.async_get_or_create(
            "sensor",
            DOMAIN,
            "beszel_system_stats_cpu",
            config_entry=entry,
        )
        device_registry = hass.device_registry
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, "system")},
        )

        self.assertTrue(await async_migrate_entry(hass, entry))

        migrated_entity = entity_registry.async_get(entity.entity_id)
        migrated_device = device_registry.async_get(device.id)
        self.assertEqual(
            entry.data,
            {
                "host": "http://beszel.local",
                "password": "password",
                "username": "user",
            },
        )
        self.assertEqual(entry.unique_id, "http://beszel.local_user")
        self.assertEqual(entry.version, 2)
        self.assertEqual(
            migrated_entity.unique_id,
            f"beszel_{entry.entry_id}_system_stats_cpu",
        )
        self.assertEqual(
            migrated_device.identifiers,
            {(DOMAIN, f"{entry.entry_id}_system")},
        )
