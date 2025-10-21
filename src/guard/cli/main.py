"""Main CLI entry point for GUARD."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from rich.console import Console

from guard import __version__

if TYPE_CHECKING:
    from guard.adapters.aws_adapter import AWSAdapter
    from guard.adapters.datadog_adapter import DatadogAdapter
    from guard.adapters.gitlab_adapter import GitLabAdapter
    from guard.core.config import GuardConfig
    from guard.core.models import ClusterConfig
    from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater
    from guard.registry.cluster_registry import ClusterRegistry
    from guard.registry.lock_manager import LockManager
    from guard.utils.cluster_credentials import ClusterCredentialManager
    from guard.utils.kubeconfig import KubeconfigManager

console = Console()

LOGO = """
  ________ ____ ___  _____ __________________
 /  _____/|    |   \\/  _  \\______   \\______ \\
/   \\  ___|    |   /  /_\\  \\|       _/|    |  \\
\\    \\_\\  \\    |  /    |    \\    |   \\|    `   \\
 \\______  /______/\\____|__  /____|_  /_______  /
        \\/                \\/       \\/        \\/
"""


class GuardContext:
    """Shared context for CLI commands with lazy initialization."""

    def __init__(self, config_path: str):
        """Initialize context with config path.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self._config: GuardConfig | None = None
        self._registry: ClusterRegistry | None = None
        self._datadog_credentials: tuple[str, str] | None = None
        self._gitlab_token: str | None = None
        self._aws_adapter: AWSAdapter | None = None
        self._datadog_adapter: DatadogAdapter | None = None
        self._gitlab_adapter: GitLabAdapter | None = None
        self._helm_updater: IstioHelmUpdater | None = None
        self._kubeconfig_manager: KubeconfigManager | None = None
        self._credential_manager: ClusterCredentialManager | None = None
        self._lock_manager: LockManager | None = None

    @property
    def config(self) -> GuardConfig:
        """Get or create config lazily."""
        if self._config is None:
            from pathlib import Path

            from guard.core.config import GuardConfig

            config_path = Path(self.config_path).expanduser()
            self._config = GuardConfig.from_file(str(config_path))
        return self._config

    @property
    def registry(self) -> ClusterRegistry:
        """Get or create cluster registry lazily."""
        if self._registry is None:
            from guard.registry.cluster_registry import ClusterRegistry

            self._registry = ClusterRegistry(
                table_name=self.config.aws.dynamodb.table_name,
                region=self.config.aws.region,
            )
        return self._registry

    @property
    def datadog_credentials(self) -> tuple[str, str]:
        """Get Datadog credentials from AWS Secrets Manager (cached)."""
        if self._datadog_credentials is None:
            from guard.utils.secrets import SecretsManager

            secrets_manager = SecretsManager(region=self.config.aws.region)
            credentials = secrets_manager.get_secret_json(
                self.config.aws.secrets_manager.datadog_credentials_secret
            )
            self._datadog_credentials = (credentials["api_key"], credentials["app_key"])
        return self._datadog_credentials

    @property
    def gitlab_token(self) -> str:
        """Get GitLab token from AWS Secrets Manager (cached)."""
        if self._gitlab_token is None:
            from guard.utils.secrets import SecretsManager

            secrets_manager = SecretsManager(region=self.config.aws.region)
            self._gitlab_token = secrets_manager.get_secret(
                self.config.aws.secrets_manager.gitlab_token_secret
            )
        return self._gitlab_token

    @property
    def aws_adapter(self) -> AWSAdapter:
        """Get or create AWS adapter lazily."""
        if self._aws_adapter is None:
            from guard.adapters.aws_adapter import AWSAdapter

            self._aws_adapter = AWSAdapter(region=self.config.aws.region)
        return self._aws_adapter

    @property
    def datadog_adapter(self) -> DatadogAdapter:
        """Get or create Datadog adapter lazily."""
        if self._datadog_adapter is None:
            from guard.adapters.datadog_adapter import DatadogAdapter

            api_key, app_key = self.datadog_credentials
            self._datadog_adapter = DatadogAdapter(api_key=api_key, app_key=app_key)
        return self._datadog_adapter

    @property
    def gitlab_adapter(self) -> GitLabAdapter:
        """Get or create GitLab adapter lazily."""
        if self._gitlab_adapter is None:
            from guard.adapters.gitlab_adapter import GitLabAdapter

            self._gitlab_adapter = GitLabAdapter(
                url=self.config.gitlab.url,
                token=self.gitlab_token,
            )
        return self._gitlab_adapter

    @property
    def helm_updater(self) -> IstioHelmUpdater:
        """Get or create Istio Helm updater lazily."""
        if self._helm_updater is None:
            from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater

            self._helm_updater = IstioHelmUpdater()
        return self._helm_updater

    @property
    def kubeconfig_manager(self) -> KubeconfigManager:
        """Get or create kubeconfig manager lazily."""
        if self._kubeconfig_manager is None:
            from guard.utils.kubeconfig import KubeconfigManager

            # Use temporary kubeconfig managed by GUARD
            self._kubeconfig_manager = KubeconfigManager()
        return self._kubeconfig_manager

    @property
    def credential_manager(self) -> ClusterCredentialManager:
        """Get or create cluster credential manager lazily."""
        if self._credential_manager is None:
            from guard.utils.cluster_credentials import ClusterCredentialManager

            self._credential_manager = ClusterCredentialManager(
                aws_adapter=self.aws_adapter,
                kubeconfig_manager=self.kubeconfig_manager,
            )
        return self._credential_manager

    @property
    def lock_manager(self) -> LockManager:
        """Get or create lock manager lazily."""
        if self._lock_manager is None:
            from guard.registry.lock_manager import LockManager

            self._lock_manager = LockManager(
                table_name=self.config.aws.dynamodb.table_name,
                region=self.config.aws.region,
            )
        return self._lock_manager


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default="~/.guard/config.yaml",
    help="Path to configuration file",
)
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """GitOps Upgrade Automation with Rollback Detection (GUARD) - Automate safe Istio upgrades."""
    # Display logo
    console.print(f"[bold cyan]{LOGO}[/bold cyan]", highlight=False)
    console.print(f"[bold]v{__version__}[/bold]\n")

    # Initialize shared context with lazy loading
    ctx.obj = GuardContext(config_path=config)


@cli.command()
@click.option("--batch", required=True, help="Batch name to upgrade")
@click.option("--target-version", required=True, help="Target Istio version")
@click.option("--dry-run", is_flag=True, help="Perform dry run without creating MR")
@click.option("--max-concurrent", type=int, default=5, help="Max concurrent cluster operations")
@click.pass_context
def run(
    ctx: click.Context, batch: str, target_version: str, dry_run: bool, max_concurrent: int
) -> None:
    """Run pre-checks and create upgrade MR for a batch."""
    import asyncio

    from guard.adapters.k8s_adapter import KubernetesAdapter
    from guard.checks.check_orchestrator import CheckOrchestrator
    from guard.checks.check_registry import CheckRegistry
    from guard.gitops.gitops_orchestrator import GitOpsOrchestrator
    from guard.interfaces.check import CheckContext
    from guard.services.istio.istio_service import IstioService
    from guard.utils.logging import get_logger

    logger = get_logger(__name__)

    console.print("[bold blue]GUARD Run Command[/bold blue]")
    console.print(f"Batch: {batch}")
    console.print(f"Target Version: {target_version}")
    console.print(f"Dry Run: {dry_run}")
    console.print(f"Max Concurrent: {max_concurrent}\n")

    async def _process_cluster(
        cluster: ClusterConfig,
        semaphore: asyncio.Semaphore,
        target_version: str,
        dry_run: bool,
        aws_adapter: AWSAdapter,
        datadog_adapter: DatadogAdapter,
        gitlab_adapter: GitLabAdapter,
        helm_updater: IstioHelmUpdater,
        credential_manager: ClusterCredentialManager,
        lock_manager: LockManager,
        registry: ClusterRegistry,
    ) -> dict:
        """Process a single cluster with error isolation."""
        async with semaphore:
            # Acquire cluster lock to prevent concurrent upgrades
            try:
                async with lock_manager.acquire_lock(cluster.cluster_id):  # type: ignore[attr-defined]
                    console.print(f"[bold]Processing cluster: {cluster.cluster_id}[/bold]")

                    # Setup cluster-specific kubeconfig context with fresh credentials
                    console.print("  Setting up cluster authentication...")

                    # Generate fresh credentials and EKS token (auto-refreshes if expired)
                    kubeconfig_path = credential_manager.setup_kubeconfig_context(cluster)

                    console.print("  [green]✓ Cluster authentication configured[/green]")

                    # Run pre-checks
                    console.print("  Running pre-checks...")
                    k8s_adapter = KubernetesAdapter(
                        kubeconfig_path=kubeconfig_path,
                        context=cluster.cluster_id,
                    )

                    # Initialize check registry and orchestrator
                    check_registry = CheckRegistry()

                    # Register Istio checks
                    istio_service = IstioService()
                    istio_service.register_checks(check_registry)

                    # Create orchestrator with registry
                    check_orchestrator = CheckOrchestrator(registry=check_registry)

                    # Build check context with all required providers
                    check_context = CheckContext(
                        kubernetes_provider=k8s_adapter,
                        cloud_provider=aws_adapter,
                        metrics_provider=datadog_adapter,
                        extra_context={
                            "kubeconfig_path": kubeconfig_path,
                            "istioctl": None,  # Will be created by check if needed
                        },
                    )

                    check_results = await check_orchestrator.run_checks(cluster, check_context)
                    all_passed = all(r.passed for r in check_results)

                    if not all_passed:
                        console.print("  [red]✗ Pre-checks failed[/red]")
                        for result in check_results:
                            if not result.passed:
                                console.print(f"    - {result.check_name}: {result.message}")
                        logger.error(
                            "cluster_pre_check_failed",
                            cluster_id=cluster.cluster_id,
                            batch_id=batch,
                        )
                        return {"cluster_id": cluster.cluster_id, "status": "pre_check_failed"}

                    console.print("  [green]✓ All pre-checks passed[/green]")

                    # Create upgrade MR
                    if not dry_run:
                        console.print("  Creating GitLab MR...")
                        orchestrator = GitOpsOrchestrator(
                            git_provider=gitlab_adapter,
                            config_updater=helm_updater,
                        )

                        mr = await orchestrator.create_upgrade_mr(
                            cluster=cluster,
                            target_version=target_version,
                        )

                        # Update cluster metadata with MR information
                        cluster.metadata.mr_created_at = mr.created_at
                        cluster.metadata.mr_url = mr.web_url
                        cluster.target_istio_version = target_version
                        registry.put_cluster(cluster)

                        console.print(f"  [green]✓ MR created: {mr.web_url}[/green]")
                        console.print(
                            f"  [yellow]→ After MR is merged, wait {60} minutes before running: guard monitor --batch {batch}[/yellow]\n"
                        )
                        logger.info(
                            "cluster_mr_created",
                            cluster_id=cluster.cluster_id,
                            mr_url=mr.web_url,
                        )
                        return {
                            "cluster_id": cluster.cluster_id,
                            "status": "success",
                            "mr_url": mr.web_url,
                        }
                    else:
                        console.print("  [yellow]Dry-run: Skipping MR creation[/yellow]\n")
                        return {"cluster_id": cluster.cluster_id, "status": "dry_run_success"}

            except Exception as e:
                console.print(f"  [red]✗ Error processing cluster: {e}[/red]\n")
                logger.error(
                    "cluster_processing_failed",
                    cluster_id=cluster.cluster_id,
                    batch_id=batch,
                    error=str(e),
                )
                return {"cluster_id": cluster.cluster_id, "status": "error", "error": str(e)}

    async def _run_upgrade() -> None:
        try:
            # Access shared context objects
            guard_ctx = ctx.obj
            console.print(f"Loading config from {guard_ctx.config_path}...")

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = guard_ctx.registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Get adapters from context (lazy-loaded with caching)
            aws_adapter = guard_ctx.aws_adapter
            datadog_adapter = guard_ctx.datadog_adapter
            gitlab_adapter = guard_ctx.gitlab_adapter
            helm_updater = guard_ctx.helm_updater
            credential_manager = guard_ctx.credential_manager
            lock_manager = guard_ctx.lock_manager
            registry = guard_ctx.registry

            # Process clusters with bounded concurrency
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = [
                _process_cluster(
                    cluster,
                    semaphore,
                    target_version,
                    dry_run,
                    aws_adapter,
                    datadog_adapter,
                    gitlab_adapter,
                    helm_updater,
                    credential_manager,
                    lock_manager,
                    registry,
                )
                for cluster in clusters
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Summarize results
            console.print("\n[bold]Batch Processing Summary[/bold]")
            success_count = sum(
                1
                for r in results
                if isinstance(r, dict) and r.get("status") in ["success", "dry_run_success"]
            )
            failed_count = len(results) - success_count

            console.print(f"  Total: {len(results)}")
            console.print(f"  [green]Success: {success_count}[/green]")
            console.print(f"  [red]Failed: {failed_count}[/red]\n")

            logger.info(
                "batch_processing_complete",
                batch_id=batch,
                total=len(results),
                success=success_count,
                failed=failed_count,
            )

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback

            traceback.print_exc()
            logger.error("batch_processing_error", batch_id=batch, error=str(e))
            raise

    asyncio.run(_run_upgrade())


@cli.command()
@click.option("--batch", required=True, help="Batch name to monitor")
@click.option("--soak-period", type=int, default=60, help="Soak period in minutes")
@click.option("--max-concurrent", type=int, default=5, help="Max concurrent cluster monitoring")
@click.pass_context
def monitor(ctx: click.Context, batch: str, soak_period: int, max_concurrent: int) -> None:
    """Monitor post-upgrade validation for a batch."""
    import asyncio

    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    from guard.core.models import ClusterStatus, ValidationThresholds
    from guard.rollback.engine import RollbackEngine
    from guard.services.istio.istio_service import IstioService
    from guard.utils.logging import get_logger
    from guard.validation.validation_orchestrator import ValidationOrchestrator
    from guard.validation.validator_registry import ValidatorRegistry

    logger = get_logger(__name__)

    console.print("[bold green]GUARD Monitor Command[/bold green]")
    console.print(f"Batch: {batch}")
    console.print(f"Soak Period: {soak_period} minutes")
    console.print(f"Max Concurrent: {max_concurrent}\n")

    async def _monitor_batch() -> None:
        try:
            # Access shared context objects
            guard_ctx = ctx.obj
            console.print(f"Loading config from {guard_ctx.config_path}...")

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = guard_ctx.registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Get adapters from context (lazy-loaded with caching)
            datadog_adapter = guard_ctx.datadog_adapter

            # Create GitLab client for rollback
            from guard.clients.gitlab_client import GitLabClient

            gitlab_client = GitLabClient(
                url=guard_ctx.config.gitlab.url,
                token=guard_ctx.gitlab_token,
            )

            # Initialize validation components
            validator_registry = ValidatorRegistry()
            istio_service = IstioService()
            istio_service.register_validators(validator_registry)

            validation_orchestrator = ValidationOrchestrator(
                registry=validator_registry,
                metrics_provider=datadog_adapter,
                fail_fast=False,
            )

            rollback_engine = RollbackEngine(
                gitlab_client=gitlab_client,
                config_updater=guard_ctx.helm_updater,
            )

            # Define validation thresholds
            thresholds = ValidationThresholds(
                latency_increase_percent=10.0,
                error_rate_max=0.001,
                resource_increase_percent=50.0,
            )

            # Wait for soak period
            console.print(f"[yellow]Waiting {soak_period} minutes for soak period...[/yellow]")
            await asyncio.sleep(soak_period * 60)

            # Monitor each cluster in parallel with progress tracking
            async def _monitor_cluster(
                cluster: ClusterConfig,
                semaphore: asyncio.Semaphore,
                progress: Progress,
                task_id: int,
            ) -> dict:
                """Monitor a single cluster with error isolation."""
                async with semaphore:
                    try:
                        progress.update(
                            task_id,  # type: ignore[arg-type]
                            description=f"[cyan]{cluster.cluster_id}[/cyan]: Capturing baseline metrics...",
                        )

                        # Capture baseline metrics (from before upgrade)
                        baseline = await validation_orchestrator.capture_baseline(
                            cluster=cluster,
                            duration_minutes=10,
                        )

                        # Capture current metrics (post-upgrade)
                        progress.update(
                            task_id,  # type: ignore[arg-type]
                            description=f"[cyan]{cluster.cluster_id}[/cyan]: Capturing current metrics...",
                        )
                        current = await validation_orchestrator.capture_current(
                            cluster=cluster,
                            baseline=baseline,
                            duration_minutes=10,
                        )

                        # Run validation
                        progress.update(
                            task_id,  # type: ignore[arg-type]
                            description=f"[cyan]{cluster.cluster_id}[/cyan]: Running validation checks...",
                        )
                        results = await validation_orchestrator.validate_upgrade(
                            cluster=cluster,
                            baseline=baseline,
                            current=current,
                            thresholds=thresholds,
                        )

                        all_passed = all(r.passed for r in results)

                        if all_passed:
                            progress.update(
                                task_id,  # type: ignore[arg-type]
                                description=f"[green]✓ {cluster.cluster_id}: All validations passed[/green]",
                            )
                            guard_ctx.registry.update_cluster_status(
                                cluster.cluster_id, ClusterStatus.HEALTHY
                            )
                            logger.info("cluster_validation_passed", cluster_id=cluster.cluster_id)
                            return {"cluster_id": cluster.cluster_id, "status": "passed"}
                        else:
                            # Trigger rollback
                            progress.update(
                                task_id,  # type: ignore[arg-type]
                                description=f"[yellow]{cluster.cluster_id}: Triggering rollback...[/yellow]",
                            )

                            failure_metrics = {
                                result.validator_name: result.violations
                                for result in results
                                if not result.passed
                            }

                            mr_url = await rollback_engine.create_rollback_mr(
                                cluster=cluster,
                                current_version=cluster.target_istio_version or "unknown",
                                previous_version=cluster.current_istio_version,
                                failure_reason="Post-upgrade validation failed",
                                failure_metrics=failure_metrics,
                            )

                            progress.update(
                                task_id,  # type: ignore[arg-type]
                                description=f"[red]✗ {cluster.cluster_id}: Validation failed, rollback MR created[/red]",
                            )
                            guard_ctx.registry.update_cluster_status(
                                cluster.cluster_id, ClusterStatus.ROLLBACK_REQUIRED
                            )
                            logger.error(
                                "cluster_validation_failed_rollback_triggered",
                                cluster_id=cluster.cluster_id,
                                mr_url=mr_url,
                            )
                            return {
                                "cluster_id": cluster.cluster_id,
                                "status": "failed",
                                "mr_url": mr_url,
                            }

                    except Exception as e:
                        progress.update(
                            task_id,  # type: ignore[arg-type]
                            description=f"[red]✗ {cluster.cluster_id}: Error - {str(e)[:50]}[/red]",
                        )
                        logger.error(
                            "cluster_monitoring_failed",
                            cluster_id=cluster.cluster_id,
                            error=str(e),
                        )
                        return {
                            "cluster_id": cluster.cluster_id,
                            "status": "error",
                            "error": str(e),
                        }

            # Create progress display
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                # Create tasks for each cluster
                semaphore = asyncio.Semaphore(max_concurrent)
                task_ids = [
                    progress.add_task(f"[cyan]{cluster.cluster_id}[/cyan]: Queued...", total=None)
                    for cluster in clusters
                ]

                # Monitor clusters in parallel
                monitor_tasks = [
                    _monitor_cluster(cluster, semaphore, progress, task_id)
                    for cluster, task_id in zip(clusters, task_ids, strict=False)
                ]

                results = await asyncio.gather(*monitor_tasks, return_exceptions=True)

            # Summarize results
            console.print("\n[bold]Batch Monitoring Summary[/bold]")
            passed_count = sum(
                1 for r in results if isinstance(r, dict) and r.get("status") == "passed"
            )
            failed_count = sum(
                1 for r in results if isinstance(r, dict) and r.get("status") == "failed"
            )
            error_count = sum(
                1 for r in results if isinstance(r, dict) and r.get("status") == "error"
            )

            console.print(f"  Total: {len(results)}")
            console.print(f"  [green]Passed: {passed_count}[/green]")
            console.print(f"  [red]Failed (Rollback Triggered): {failed_count}[/red]")
            console.print(f"  [yellow]Errors: {error_count}[/yellow]\n")

            logger.info(
                "batch_monitoring_complete",
                batch_id=batch,
                total=len(results),
                passed=passed_count,
                failed=failed_count,
                errors=error_count,
            )

            console.print("[bold green]✓ Batch monitoring complete![/bold green]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback

            traceback.print_exc()
            logger.error("batch_monitoring_error", batch_id=batch, error=str(e))
            raise

    asyncio.run(_monitor_batch())


@cli.command()
@click.option("--batch", required=True, help="Batch name to rollback")
@click.option("--reason", required=True, help="Reason for manual rollback")
@click.pass_context
def rollback(ctx: click.Context, batch: str, reason: str) -> None:
    """Trigger manual rollback for a batch."""
    import asyncio

    from guard.core.models import ClusterStatus
    from guard.rollback.engine import RollbackEngine
    from guard.utils.logging import get_logger

    logger = get_logger(__name__)

    console.print("[bold red]GUARD Rollback Command[/bold red]")
    console.print(f"Batch: {batch}")
    console.print(f"Reason: {reason}\n")

    async def _rollback_batch() -> None:
        try:
            # Access shared context objects
            guard_ctx = ctx.obj
            console.print(f"Loading config from {guard_ctx.config_path}...")

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = guard_ctx.registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Initialize rollback engine
            from guard.clients.gitlab_client import GitLabClient

            gitlab_client = GitLabClient(
                url=guard_ctx.config.gitlab.url,
                token=guard_ctx.gitlab_token,
            )
            rollback_engine = RollbackEngine(
                gitlab_client=gitlab_client,
                config_updater=guard_ctx.helm_updater,
            )

            # Rollback each cluster
            for cluster in clusters:
                console.print(f"[bold]Rolling back cluster: {cluster.cluster_id}[/bold]")

                try:
                    mr_url = await rollback_engine.create_rollback_mr(
                        cluster=cluster,
                        current_version=cluster.target_istio_version
                        or cluster.current_istio_version,
                        previous_version=cluster.current_istio_version,
                        failure_reason=f"Manual rollback: {reason}",
                        failure_metrics=None,
                    )

                    console.print(f"  [green]✓ Rollback MR created: {mr_url}[/green]\n")
                    guard_ctx.registry.update_cluster_status(
                        cluster.cluster_id, ClusterStatus.ROLLBACK_REQUIRED
                    )
                    logger.info(
                        "manual_rollback_triggered",
                        cluster_id=cluster.cluster_id,
                        mr_url=mr_url,
                        reason=reason,
                    )

                except Exception as e:
                    console.print(f"  [red]✗ Error creating rollback MR: {e}[/red]\n")
                    logger.error(
                        "rollback_failed",
                        cluster_id=cluster.cluster_id,
                        error=str(e),
                    )

            console.print("[bold green]✓ Batch rollback complete![/bold green]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback

            traceback.print_exc()
            logger.error("batch_rollback_error", batch_id=batch, error=str(e))
            raise

    asyncio.run(_rollback_batch())


@cli.command(name="list")
@click.option("--batch", help="Filter by batch name")
@click.option("--environment", help="Filter by environment")
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def list_clusters(
    ctx: click.Context, batch: str | None, environment: str | None, format: str
) -> None:
    """List clusters and their status."""
    import asyncio
    import json

    from rich.table import Table

    console.print("[bold cyan]GUARD List Command[/bold cyan]")
    console.print(f"Batch Filter: {batch or 'All'}")
    console.print(f"Environment Filter: {environment or 'All'}\n")

    async def _list_clusters() -> None:
        try:
            # Access shared context objects
            guard_ctx = ctx.obj

            # Get clusters
            if batch:
                clusters = guard_ctx.registry.get_clusters_by_batch(batch)
            else:
                clusters = guard_ctx.registry.list_all_clusters()

            # Filter by environment if specified
            if environment:
                clusters = [c for c in clusters if c.environment == environment]

            if not clusters:
                console.print("[yellow]No clusters found matching the filters[/yellow]")
                return

            # Display results
            if format == "json":
                cluster_dicts = [c.model_dump() for c in clusters]
                print(json.dumps(cluster_dicts, indent=2, default=str))
            else:
                table = Table(title=f"GUARD Clusters ({len(clusters)} total)")
                table.add_column("Cluster ID", style="cyan")
                table.add_column("Batch", style="magenta")
                table.add_column("Environment", style="blue")
                table.add_column("Current Version", style="green")
                table.add_column("Target Version", style="yellow")
                table.add_column("Status", style="bold")

                for cluster in clusters:
                    status_color = "green" if cluster.status == "healthy" else "yellow"
                    table.add_row(
                        cluster.cluster_id,
                        cluster.batch_id,
                        cluster.environment,
                        cluster.current_istio_version,
                        cluster.target_istio_version or "-",
                        f"[{status_color}]{cluster.status}[/{status_color}]",
                    )

                console.print(table)

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback

            traceback.print_exc()
            raise

    asyncio.run(_list_clusters())


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate configuration and connectivity."""
    import asyncio

    console.print("[bold magenta]GUARD Validate Command[/bold magenta]\n")

    async def _validate() -> None:
        try:
            # Access shared context objects
            guard_ctx = ctx.obj
            from pathlib import Path

            config_path = Path(guard_ctx.config_path).expanduser()
            console.print("[bold]1. Configuration File[/bold]")
            console.print(f"  Path: {config_path}")

            if not config_path.exists():
                console.print("  [red]✗ Config file not found[/red]")
                return

            console.print("  [green]✓ Config file exists[/green]")

            try:
                # Access config to trigger validation
                _ = guard_ctx.config
                console.print("  [green]✓ Config file valid[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ Config file invalid: {e}[/red]\n")
                return

            # Validate DynamoDB connectivity
            console.print("[bold]2. DynamoDB Connectivity[/bold]")
            try:
                # Access registry to test DynamoDB
                _ = guard_ctx.registry
                console.print("  [green]✓ DynamoDB connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ DynamoDB connection failed: {e}[/red]\n")

            # Validate Datadog connectivity
            console.print("[bold]3. Datadog Connectivity[/bold]")
            try:
                _ = guard_ctx.datadog_adapter
                console.print("  [green]✓ Datadog connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ Datadog connection failed: {e}[/red]\n")

            # Validate GitLab connectivity
            console.print("[bold]4. GitLab Connectivity[/bold]")
            try:
                _ = guard_ctx.gitlab_adapter
                console.print("  [green]✓ GitLab connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ GitLab connection failed: {e}[/red]\n")

            # Validate AWS connectivity
            console.print("[bold]5. AWS Connectivity[/bold]")
            try:
                _ = guard_ctx.aws_adapter
                console.print("  [green]✓ AWS connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ AWS connection failed: {e}[/red]\n")

            console.print("[bold green]✓ Validation complete![/bold green]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback

            traceback.print_exc()
            raise

    asyncio.run(_validate())


if __name__ == "__main__":
    cli()
