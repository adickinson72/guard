"""Unit tests for FieldUpdate and UpgradeSpec models."""

import pytest
from pydantic import ValidationError

from guard.core.models import FieldUpdate, UpgradeSpec


class TestFieldUpdate:
    """Tests for FieldUpdate model."""

    def test_valid_field_update(self):
        """Test creating a valid FieldUpdate."""
        update = FieldUpdate(path="spec.chart.spec.version", value="1.20.0")
        assert update.path == "spec.chart.spec.version"
        assert update.value == "1.20.0"

    def test_field_update_with_various_types(self):
        """Test FieldUpdate with different value types."""
        # String value
        update1 = FieldUpdate(path="spec.values.tag", value="1.20.0")
        assert update1.value == "1.20.0"

        # Integer value
        update2 = FieldUpdate(path="spec.values.replicas", value=3)
        assert update2.value == 3

        # Boolean value
        update3 = FieldUpdate(path="spec.values.enabled", value=True)
        assert update3.value is True

        # Dict value
        update4 = FieldUpdate(path="spec.values.resources", value={"cpu": "100m"})
        assert update4.value == {"cpu": "100m"}

        # List value
        update5 = FieldUpdate(path="spec.values.tags", value=["tag1", "tag2"])
        assert update5.value == ["tag1", "tag2"]

    def test_validate_path_valid_paths(self):
        """Test validate_path with valid paths."""
        assert FieldUpdate.validate_path("spec.chart.spec.version")
        assert FieldUpdate.validate_path("a.b.c.d")
        assert FieldUpdate.validate_path("spec.values.pilot.autoscaleEnabled")
        assert FieldUpdate.validate_path("single")

    def test_validate_path_invalid_paths(self):
        """Test validate_path rejects invalid paths."""
        # Empty string
        assert not FieldUpdate.validate_path("")

        # Non-string
        assert not FieldUpdate.validate_path(None)  # type: ignore
        assert not FieldUpdate.validate_path(123)  # type: ignore

        # Path with consecutive dots
        assert not FieldUpdate.validate_path("spec..version")
        assert not FieldUpdate.validate_path("a..b..c")

        # Path starting with dot
        assert not FieldUpdate.validate_path(".spec.version")

        # Path ending with dot
        assert not FieldUpdate.validate_path("spec.version.")

        # Path with only whitespace in parts
        assert not FieldUpdate.validate_path("spec. .version")
        assert not FieldUpdate.validate_path("spec.  .version")

        # Path with empty parts
        assert not FieldUpdate.validate_path("spec..chart")

    def test_field_update_missing_required_fields(self):
        """Test that FieldUpdate requires path and value."""
        with pytest.raises(ValidationError) as exc_info:
            FieldUpdate(path="spec.version")  # type: ignore # Missing value

        errors = exc_info.value.errors()
        assert any(err["loc"] == ("value",) for err in errors)

        with pytest.raises(ValidationError) as exc_info:
            FieldUpdate(value="1.20.0")  # type: ignore # Missing path

        errors = exc_info.value.errors()
        assert any(err["loc"] == ("path",) for err in errors)


class TestUpgradeSpec:
    """Tests for UpgradeSpec model."""

    def test_valid_upgrade_spec(self):
        """Test creating a valid UpgradeSpec."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[
                FieldUpdate(path="spec.chart.spec.version", value="1.20.0"),
                FieldUpdate(path="spec.values.global.tag", value="1.20.0"),
            ],
        )
        assert spec.version == "1.20.0"
        assert len(spec.updates) == 2
        assert spec.updates[0].path == "spec.chart.spec.version"
        assert spec.updates[1].path == "spec.values.global.tag"

    def test_upgrade_spec_single_update(self):
        """Test UpgradeSpec with single update."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[FieldUpdate(path="spec.chart.spec.version", value="1.20.0")],
        )
        assert len(spec.updates) == 1

    def test_upgrade_spec_empty_updates_fails(self):
        """Test that UpgradeSpec requires at least one update."""
        with pytest.raises(ValidationError) as exc_info:
            UpgradeSpec(version="1.20.0", updates=[])

        errors = exc_info.value.errors()
        assert any(
            err["loc"] == ("updates",) and "at least 1 item" in err["msg"].lower() for err in errors
        )

    def test_upgrade_spec_missing_version(self):
        """Test that UpgradeSpec requires version."""
        with pytest.raises(ValidationError) as exc_info:
            UpgradeSpec(  # type: ignore
                updates=[FieldUpdate(path="spec.chart.spec.version", value="1.20.0")]
            )

        errors = exc_info.value.errors()
        assert any(err["loc"] == ("version",) for err in errors)

    def test_upgrade_spec_missing_updates(self):
        """Test that UpgradeSpec requires updates."""
        with pytest.raises(ValidationError) as exc_info:
            UpgradeSpec(version="1.20.0")  # type: ignore

        errors = exc_info.value.errors()
        assert any(err["loc"] == ("updates",) for err in errors)

    def test_validate_updates_all_valid(self):
        """Test validate_updates returns True for valid updates."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[
                FieldUpdate(path="spec.chart.spec.version", value="1.20.0"),
                FieldUpdate(path="spec.values.tag", value="1.20.0"),
            ],
        )
        assert spec.validate_updates() is True

    def test_upgrade_spec_complex_values(self):
        """Test UpgradeSpec with complex value types."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[
                FieldUpdate(path="spec.chart.spec.version", value="1.20.0"),
                FieldUpdate(path="spec.values.replicas", value=3),
                FieldUpdate(path="spec.values.autoscale.enabled", value=True),
                FieldUpdate(
                    path="spec.values.resources.requests", value={"cpu": "500m", "memory": "512Mi"}
                ),
                FieldUpdate(
                    path="spec.values.tolerations", value=[{"key": "node", "operator": "Equal"}]
                ),
            ],
        )
        assert len(spec.updates) == 5
        assert isinstance(spec.updates[1].value, int)
        assert isinstance(spec.updates[2].value, bool)
        assert isinstance(spec.updates[3].value, dict)
        assert isinstance(spec.updates[4].value, list)

    def test_upgrade_spec_serialization(self):
        """Test UpgradeSpec can be serialized to dict."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[
                FieldUpdate(path="spec.chart.spec.version", value="1.20.0"),
                FieldUpdate(path="spec.values.tag", value="1.20.0"),
            ],
        )
        spec_dict = spec.model_dump()
        assert spec_dict["version"] == "1.20.0"
        assert len(spec_dict["updates"]) == 2
        assert spec_dict["updates"][0]["path"] == "spec.chart.spec.version"
        assert spec_dict["updates"][0]["value"] == "1.20.0"

    def test_upgrade_spec_from_dict(self):
        """Test UpgradeSpec can be created from dict."""
        spec_dict = {
            "version": "1.20.0",
            "updates": [
                {"path": "spec.chart.spec.version", "value": "1.20.0"},
                {"path": "spec.values.tag", "value": "1.20.0"},
            ],
        }
        spec = UpgradeSpec(**spec_dict)
        assert spec.version == "1.20.0"
        assert len(spec.updates) == 2
