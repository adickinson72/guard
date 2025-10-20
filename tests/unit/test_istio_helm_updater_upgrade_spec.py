"""Unit tests for IstioHelmUpdater upgrade spec functionality."""

import tempfile
from pathlib import Path

import pytest
import yaml

from guard.core.models import FieldUpdate, UpgradeSpec
from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater
from guard.interfaces.exceptions import ConfigUpdaterError


@pytest.fixture
def updater():
    """Create IstioHelmUpdater instance."""
    return IstioHelmUpdater()


@pytest.fixture
def sample_helmrelease():
    """Create sample HelmRelease YAML."""
    return {
        "apiVersion": "helm.toolkit.fluxcd.io/v2beta1",
        "kind": "HelmRelease",
        "metadata": {"name": "istio-base", "namespace": "istio-system"},
        "spec": {
            "chart": {"spec": {"chart": "base", "version": "1.19.0"}},
            "values": {
                "global": {"tag": "1.19.0"},
                "pilot": {
                    "autoscaleEnabled": False,
                    "autoscaleMin": 1,
                    "autoscaleMax": 5,
                    "resources": {"requests": {"cpu": "500m", "memory": "512Mi"}},
                },
            },
        },
    }


@pytest.fixture
def temp_helmrelease_file(sample_helmrelease):
    """Create temporary HelmRelease file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_helmrelease, f, default_flow_style=False, sort_keys=False)
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()
    # Also cleanup backup if created
    backup_path = Path(str(temp_path) + ".bak")
    if backup_path.exists():
        backup_path.unlink()


class TestSetNestedValue:
    """Tests for _set_nested_value static method."""

    def test_set_simple_path(self):
        """Test setting a simple path."""
        data = {"spec": {"version": "1.0.0"}}
        IstioHelmUpdater._set_nested_value(data, "spec.version", "2.0.0")
        assert data["spec"]["version"] == "2.0.0"

    def test_set_deeply_nested_path(self):
        """Test setting a deeply nested path."""
        data = {"spec": {"chart": {"spec": {"version": "1.0.0"}}}}
        IstioHelmUpdater._set_nested_value(data, "spec.chart.spec.version", "2.0.0")
        assert data["spec"]["chart"]["spec"]["version"] == "2.0.0"

    def test_set_with_various_value_types(self):
        """Test setting values of different types."""
        data = {"spec": {"values": {}}}

        # String
        IstioHelmUpdater._set_nested_value(data, "spec.values.tag", "1.20.0")
        assert data["spec"]["values"]["tag"] == "1.20.0"

        # Integer
        IstioHelmUpdater._set_nested_value(data, "spec.values.replicas", 3)
        assert data["spec"]["values"]["replicas"] == 3

        # Boolean
        IstioHelmUpdater._set_nested_value(data, "spec.values.enabled", True)
        assert data["spec"]["values"]["enabled"] is True

        # Dict
        IstioHelmUpdater._set_nested_value(data, "spec.values.resources", {"cpu": "100m"})
        assert data["spec"]["values"]["resources"] == {"cpu": "100m"}

        # List
        IstioHelmUpdater._set_nested_value(data, "spec.values.tags", ["a", "b"])
        assert data["spec"]["values"]["tags"] == ["a", "b"]

    def test_set_missing_path_without_create(self):
        """Test that missing paths raise error when create_missing=False."""
        data = {"spec": {"chart": {}}}

        with pytest.raises(ValueError) as exc_info:
            IstioHelmUpdater._set_nested_value(
                data, "spec.chart.spec.version", "2.0.0", create_missing=False
            )

        assert "missing key 'spec'" in str(exc_info.value).lower()
        assert "create_missing=True" in str(exc_info.value)

    def test_set_missing_path_with_create(self):
        """Test that missing paths are created when create_missing=True."""
        data = {"spec": {"chart": {}}}

        IstioHelmUpdater._set_nested_value(
            data, "spec.chart.spec.version", "2.0.0", create_missing=True
        )

        assert data["spec"]["chart"]["spec"]["version"] == "2.0.0"

    def test_set_path_with_non_dict_intermediate(self):
        """Test error when intermediate value is not a dict."""
        data = {"spec": {"chart": "not-a-dict"}}

        with pytest.raises(ValueError) as exc_info:
            IstioHelmUpdater._set_nested_value(data, "spec.chart.version", "2.0.0")

        assert "not a dictionary" in str(exc_info.value).lower()

    def test_overwrite_existing_value(self):
        """Test overwriting existing values."""
        data = {"spec": {"version": "1.0.0", "other": "value"}}

        IstioHelmUpdater._set_nested_value(data, "spec.version", "2.0.0")

        assert data["spec"]["version"] == "2.0.0"
        assert data["spec"]["other"] == "value"  # Other values preserved

    def test_create_intermediate_dicts_multiple_levels(self):
        """Test creating multiple levels of intermediate dicts."""
        data = {}

        IstioHelmUpdater._set_nested_value(data, "a.b.c.d.e.f", "value", create_missing=True)

        assert data["a"]["b"]["c"]["d"]["e"]["f"] == "value"


class TestApplyUpgradeSpec:
    """Tests for apply_upgrade_spec method."""

    @pytest.mark.asyncio
    async def test_apply_single_update(self, updater, temp_helmrelease_file):
        """Test applying a single field update."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[FieldUpdate(path="spec.chart.spec.version", value="1.20.0")],
        )

        result = await updater.apply_upgrade_spec(temp_helmrelease_file, spec)

        assert result is True

        # Verify the file was updated
        with open(temp_helmrelease_file) as f:
            updated_config = yaml.safe_load(f)

        assert updated_config["spec"]["chart"]["spec"]["version"] == "1.20.0"

    @pytest.mark.asyncio
    async def test_apply_multiple_updates(self, updater, temp_helmrelease_file):
        """Test applying multiple field updates."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[
                FieldUpdate(path="spec.chart.spec.version", value="1.20.0"),
                FieldUpdate(path="spec.values.global.tag", value="1.20.0"),
                FieldUpdate(path="spec.values.pilot.autoscaleEnabled", value=True),
                FieldUpdate(path="spec.values.pilot.autoscaleMin", value=2),
            ],
        )

        result = await updater.apply_upgrade_spec(temp_helmrelease_file, spec)

        assert result is True

        # Verify all updates were applied
        with open(temp_helmrelease_file) as f:
            updated_config = yaml.safe_load(f)

        assert updated_config["spec"]["chart"]["spec"]["version"] == "1.20.0"
        assert updated_config["spec"]["values"]["global"]["tag"] == "1.20.0"
        assert updated_config["spec"]["values"]["pilot"]["autoscaleEnabled"] is True
        assert updated_config["spec"]["values"]["pilot"]["autoscaleMin"] == 2

    @pytest.mark.asyncio
    async def test_apply_with_backup(self, updater, temp_helmrelease_file):
        """Test that backup file is created when backup=True."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[FieldUpdate(path="spec.chart.spec.version", value="1.20.0")],
        )

        result = await updater.apply_upgrade_spec(temp_helmrelease_file, spec, backup=True)

        assert result is True

        # Verify backup was created with correct name
        backup_path = Path(str(temp_helmrelease_file) + ".bak")
        assert backup_path.exists()

        # Verify backup contains original content
        with open(backup_path) as f:
            backup_config = yaml.safe_load(f)

        assert backup_config["spec"]["chart"]["spec"]["version"] == "1.19.0"

    @pytest.mark.asyncio
    async def test_apply_without_backup(self, updater, temp_helmrelease_file):
        """Test that backup file is not created when backup=False."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[FieldUpdate(path="spec.chart.spec.version", value="1.20.0")],
        )

        result = await updater.apply_upgrade_spec(temp_helmrelease_file, spec, backup=False)

        assert result is True

        # Verify backup was not created
        backup_path = Path(str(temp_helmrelease_file) + ".bak")
        assert not backup_path.exists()

    @pytest.mark.asyncio
    async def test_apply_invalid_spec_fails(self, updater, temp_helmrelease_file):
        """Test that invalid upgrade spec raises error during model validation."""
        from pydantic import ValidationError

        # Creating an UpgradeSpec with invalid paths should raise ValidationError
        # due to the model_validator
        with pytest.raises(ValidationError) as exc_info:
            spec = UpgradeSpec(
                version="1.20.0",
                updates=[FieldUpdate(path="spec..version", value="1.20.0")],  # Invalid path
            )

        # Verify the error message mentions invalid paths
        assert "invalid field paths" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_apply_nonexistent_path_fails(self, updater, temp_helmrelease_file):
        """Test that nonexistent paths fail (default behavior)."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[FieldUpdate(path="spec.nonexistent.field", value="value")],
        )

        with pytest.raises(ConfigUpdaterError) as exc_info:
            await updater.apply_upgrade_spec(temp_helmrelease_file, spec)

        assert "failed to update field" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_apply_empty_file_fails(self, updater):
        """Test that empty file raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_path = Path(f.name)

        try:
            spec = UpgradeSpec(
                version="1.20.0",
                updates=[FieldUpdate(path="spec.version", value="1.20.0")],
            )

            with pytest.raises(ConfigUpdaterError) as exc_info:
                await updater.apply_upgrade_spec(temp_path, spec)

            assert "empty or invalid" in str(exc_info.value).lower()

        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_apply_preserves_yaml_formatting(self, updater, temp_helmrelease_file):
        """Test that YAML formatting is preserved (no sorting)."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[FieldUpdate(path="spec.chart.spec.version", value="1.20.0")],
        )

        await updater.apply_upgrade_spec(temp_helmrelease_file, spec)

        # Read updated content
        with open(temp_helmrelease_file) as f:
            updated_content = f.read()

        # Check that keys are not sorted (apiVersion should still come first)
        assert updated_content.startswith("apiVersion:")
        # Version should have changed (may be quoted or unquoted)
        assert (
            "version: '1.20.0'" in updated_content
            or 'version: "1.20.0"' in updated_content
            or "version: 1.20.0" in updated_content
        )

    @pytest.mark.asyncio
    async def test_apply_complex_nested_updates(self, updater, temp_helmrelease_file):
        """Test applying updates to deeply nested structures."""
        spec = UpgradeSpec(
            version="1.20.0",
            updates=[
                FieldUpdate(path="spec.values.pilot.resources.requests.cpu", value="1000m"),
                FieldUpdate(path="spec.values.pilot.resources.requests.memory", value="1Gi"),
            ],
        )

        result = await updater.apply_upgrade_spec(temp_helmrelease_file, spec)

        assert result is True

        with open(temp_helmrelease_file) as f:
            updated_config = yaml.safe_load(f)

        assert updated_config["spec"]["values"]["pilot"]["resources"]["requests"]["cpu"] == "1000m"
        assert updated_config["spec"]["values"]["pilot"]["resources"]["requests"]["memory"] == "1Gi"
