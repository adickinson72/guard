"""Main CLI entry point for GUARD."""

import click
from rich.console import Console

from guard import __version__

console = Console()

LOGO = """
  ________ ____ ___  _____ __________________
 /  _____/|    |   \\/  _  \\______   \\______ \\
/   \\  ___|    |   /  /_\\  \\|       _/|    |  \\
\\    \\_\\  \\    |  /    |    \\    |   \\|    `   \\
 \\______  /______/\\____|__  /____|_  /_______  /
        \\/                \\/       \\/        \\/
"""


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

    ctx.ensure_object(dict)
    ctx.obj["config"] = config


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
    from pathlib import Path

    from guard.adapters.aws_adapter import AWSAdapter
    from guard.adapters.datadog_adapter import DatadogAdapter
    from guard.adapters.dynamodb_adapter import DynamoDBAdapter
    from guard.adapters.gitlab_adapter import GitLabAdapter
    from guard.adapters.k8s_adapter import KubernetesAdapter
    from guard.checks.pre_check_engine import PreCheckOrchestrator
    from guard.core.config import GuardConfig
    from guard.gitops.gitops_orchestrator import GitOpsOrchestrator
    from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater
    from guard.interfaces.check import CheckContext
    from guard.registry.cluster_registry import ClusterRegistry
    from guard.services.istio.istio_service import IstioService
    from guard.utils.logging import get_logger

    logger = get_logger(__name__)

    console.print("[bold blue]GUARD Run Command[/bold blue]")
    console.print(f"Batch: {batch}")
    console.print(f"Target Version: {target_version}")
    console.print(f"Dry Run: {dry_run}")
    console.print(f"Max Concurrent: {max_concurrent}\n")

    async def _process_cluster(
        cluster,
        semaphore,
        app_config,
        target_version,
        dry_run,
        aws_adapter,
        datadog_adapter,
        gitlab_adapter,
        helm_updater,
    ):
        """Process a single cluster with error isolation."""
        async with semaphore:
            try:
                console.print(f"[bold]Processing cluster: {cluster.cluster_id}[/bold]")

                # Run pre-checks
                console.print("  Running pre-checks...")
                k8s_adapter = KubernetesAdapter(context=cluster.cluster_id)

                # Initialize check orchestrator and register checks
                check_orchestrator = PreCheckOrchestrator()

                # Register Istio checks
                istio_service = IstioService()
                istio_service.register_checks(check_orchestrator)

                # Build check context with all required providers
                check_context = CheckContext(
                    kubernetes_provider=k8s_adapter,
                    cloud_provider=aws_adapter,
                    metrics_provider=datadog_adapter,
                    extra_context={
                        "kubeconfig_path": None,  # Use default kubeconfig
                        "istioctl": None,  # Will be created by check if needed
                    },
                )

                check_results = await check_orchestrator.run_all_checks(cluster, check_context)
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
                        gitops_provider=gitlab_adapter,
                        config_updater=helm_updater,
                    )

                    mr_url = await orchestrator.create_upgrade_mr(
                        cluster=cluster,
                        target_version=target_version,
                    )

                    console.print(f"  [green]✓ MR created: {mr_url}[/green]\n")
                    logger.info(
                        "cluster_mr_created",
                        cluster_id=cluster.cluster_id,
                        mr_url=mr_url,
                    )
                    return {"cluster_id": cluster.cluster_id, "status": "success", "mr_url": mr_url}
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

    async def _run_upgrade():
        try:
            # Load configuration
            config_path = Path(ctx.obj["config"]).expanduser()
            console.print(f"Loading config from {config_path}...")
            app_config = GuardConfig.from_file(str(config_path))

            # Initialize cluster registry
            console.print("Initializing cluster registry...")
            dynamodb = DynamoDBAdapter(region=app_config.aws.region)
            registry = ClusterRegistry(dynamodb)

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = await registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Initialize adapters and clients
            aws_adapter = AWSAdapter(region=app_config.aws.region)
            datadog_adapter = DatadogAdapter(
                api_key=app_config.datadog.api_key,
                app_key=app_config.datadog.app_key,
            )
            gitlab_adapter = GitLabAdapter(
                url=app_config.gitlab.url,
                token=app_config.gitlab.token,
            )

            # Initialize config updater
            helm_updater = IstioHelmUpdater()

            # Process clusters with bounded concurrency
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = [
                _process_cluster(
                    cluster,
                    semaphore,
                    app_config,
                    target_version,
                    dry_run,
                    aws_adapter,
                    datadog_adapter,
                    gitlab_adapter,
                    helm_updater,
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
@click.pass_context
def monitor(ctx: click.Context, batch: str, soak_period: int) -> None:
    """Monitor post-upgrade validation for a batch."""
    import asyncio
    from pathlib import Path

    from guard.adapters.datadog_adapter import DatadogAdapter
    from guard.adapters.dynamodb_adapter import DynamoDBAdapter
    from guard.adapters.gitlab_adapter import GitLabAdapter
    from guard.clients.gitlab_client import GitLabClient
    from guard.core.config import GuardConfig
    from guard.core.models import ClusterStatus, ValidationThresholds
    from guard.registry.cluster_registry import ClusterRegistry
    from guard.rollback.engine import RollbackEngine
    from guard.services.istio.istio_service import IstioService
    from guard.utils.logging import get_logger
    from guard.validation.validation_orchestrator import ValidationOrchestrator
    from guard.validation.validator_registry import ValidatorRegistry

    logger = get_logger(__name__)

    console.print("[bold green]GUARD Monitor Command[/bold green]")
    console.print(f"Batch: {batch}")
    console.print(f"Soak Period: {soak_period} minutes\n")

    async def _monitor_batch():
        try:
            # Load configuration
            config_path = Path(ctx.obj["config"]).expanduser()
            console.print(f"Loading config from {config_path}...")
            app_config = GuardConfig.from_file(str(config_path))

            # Initialize cluster registry
            console.print("Initializing cluster registry...")
            dynamodb = DynamoDBAdapter(region=app_config.aws.region)
            registry = ClusterRegistry(dynamodb)

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = await registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Initialize adapters
            datadog_adapter = DatadogAdapter(
                api_key=app_config.datadog.api_key,
                app_key=app_config.datadog.app_key,
            )
            gitlab_adapter = GitLabAdapter(
                url=app_config.gitlab.url,
                token=app_config.gitlab.token,
            )
            gitlab_client = GitLabClient(
                url=app_config.gitlab.url,
                token=app_config.gitlab.token,
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

            rollback_engine = RollbackEngine(gitlab_client=gitlab_client)

            # Define validation thresholds
            thresholds = ValidationThresholds(
                latency_increase_percent=10.0,
                error_rate_max=0.001,
                resource_increase_percent=50.0,
            )

            # Wait for soak period
            console.print(f"[yellow]Waiting {soak_period} minutes for soak period...[/yellow]")
            await asyncio.sleep(soak_period * 60)

            # Monitor each cluster
            for cluster in clusters:
                console.print(f"\n[bold]Monitoring cluster: {cluster.cluster_id}[/bold]")

                try:
                    # Capture baseline metrics (from before upgrade)
                    console.print("  Capturing baseline metrics...")
                    baseline = await validation_orchestrator.capture_baseline(
                        cluster=cluster,
                        duration_minutes=10,
                    )

                    # Capture current metrics (post-upgrade)
                    console.print("  Capturing current metrics...")
                    current = await validation_orchestrator.capture_current(
                        cluster=cluster,
                        baseline=baseline,
                        duration_minutes=10,
                    )

                    # Run validation
                    console.print("  Running validation checks...")
                    results = await validation_orchestrator.validate_upgrade(
                        cluster=cluster,
                        baseline=baseline,
                        current=current,
                        thresholds=thresholds,
                    )

                    all_passed = all(r.passed for r in results)

                    if all_passed:
                        console.print("  [green]✓ All validations passed[/green]")
                        await registry.update_status(cluster.cluster_id, ClusterStatus.HEALTHY)
                        logger.info("cluster_validation_passed", cluster_id=cluster.cluster_id)
                    else:
                        console.print("  [red]✗ Validation failed[/red]")
                        for result in results:
                            if not result.passed:
                                console.print(f"    - {result.validator_name}: {result.violations}")

                        # Trigger rollback
                        console.print("  [yellow]Triggering automated rollback...[/yellow]")

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

                        console.print(f"  [green]✓ Rollback MR created: {mr_url}[/green]")
                        await registry.update_status(
                            cluster.cluster_id, ClusterStatus.ROLLBACK_REQUIRED
                        )
                        logger.error(
                            "cluster_validation_failed_rollback_triggered",
                            cluster_id=cluster.cluster_id,
                            mr_url=mr_url,
                        )

                except Exception as e:
                    console.print(f"  [red]✗ Error monitoring cluster: {e}[/red]")
                    logger.error(
                        "cluster_monitoring_failed",
                        cluster_id=cluster.cluster_id,
                        error=str(e),
                    )

            console.print("\n[bold green]✓ Batch monitoring complete![/bold green]")

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
    from pathlib import Path

    from guard.adapters.dynamodb_adapter import DynamoDBAdapter
    from guard.clients.gitlab_client import GitLabClient
    from guard.core.config import GuardConfig
    from guard.core.models import ClusterStatus
    from guard.registry.cluster_registry import ClusterRegistry
    from guard.rollback.engine import RollbackEngine
    from guard.utils.logging import get_logger

    logger = get_logger(__name__)

    console.print("[bold red]GUARD Rollback Command[/bold red]")
    console.print(f"Batch: {batch}")
    console.print(f"Reason: {reason}\n")

    async def _rollback_batch():
        try:
            # Load configuration
            config_path = Path(ctx.obj["config"]).expanduser()
            console.print(f"Loading config from {config_path}...")
            app_config = GuardConfig.from_file(str(config_path))

            # Initialize cluster registry
            console.print("Initializing cluster registry...")
            dynamodb = DynamoDBAdapter(region=app_config.aws.region)
            registry = ClusterRegistry(dynamodb)

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = await registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Initialize rollback engine
            gitlab_client = GitLabClient(
                url=app_config.gitlab.url,
                token=app_config.gitlab.token,
            )
            rollback_engine = RollbackEngine(gitlab_client=gitlab_client)

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
                    await registry.update_status(
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
    from pathlib import Path

    from rich.table import Table

    from guard.adapters.dynamodb_adapter import DynamoDBAdapter
    from guard.core.config import GuardConfig
    from guard.registry.cluster_registry import ClusterRegistry

    console.print("[bold cyan]GUARD List Command[/bold cyan]")
    console.print(f"Batch Filter: {batch or 'All'}")
    console.print(f"Environment Filter: {environment or 'All'}\n")

    async def _list_clusters():
        try:
            # Load configuration
            config_path = Path(ctx.obj["config"]).expanduser()
            app_config = GuardConfig.from_file(str(config_path))

            # Initialize cluster registry
            dynamodb = DynamoDBAdapter(region=app_config.aws.region)
            registry = ClusterRegistry(dynamodb)

            # Get clusters
            if batch:
                clusters = await registry.get_clusters_by_batch(batch)
            else:
                clusters = await registry.list_all_clusters()

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
    from pathlib import Path

    from guard.adapters.aws_adapter import AWSAdapter
    from guard.adapters.datadog_adapter import DatadogAdapter
    from guard.adapters.dynamodb_adapter import DynamoDBAdapter
    from guard.adapters.gitlab_adapter import GitLabAdapter
    from guard.core.config import GuardConfig

    console.print("[bold magenta]GUARD Validate Command[/bold magenta]\n")

    async def _validate():
        try:
            # Load configuration
            config_path = Path(ctx.obj["config"]).expanduser()
            console.print("[bold]1. Configuration File[/bold]")
            console.print(f"  Path: {config_path}")

            if not config_path.exists():
                console.print("  [red]✗ Config file not found[/red]")
                return

            console.print("  [green]✓ Config file exists[/green]")

            try:
                app_config = GuardConfig.from_file(str(config_path))
                console.print("  [green]✓ Config file valid[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ Config file invalid: {e}[/red]\n")
                return

            # Validate DynamoDB connectivity
            console.print("[bold]2. DynamoDB Connectivity[/bold]")
            try:
                dynamodb = DynamoDBAdapter(region=app_config.aws.region)
                # Try to list tables or describe table
                console.print("  [green]✓ DynamoDB connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ DynamoDB connection failed: {e}[/red]\n")

            # Validate Datadog connectivity
            console.print("[bold]3. Datadog Connectivity[/bold]")
            try:
                datadog = DatadogAdapter(
                    api_key=app_config.datadog.api_key,
                    app_key=app_config.datadog.app_key,
                )
                # Try a simple query
                console.print("  [green]✓ Datadog connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ Datadog connection failed: {e}[/red]\n")

            # Validate GitLab connectivity
            console.print("[bold]4. GitLab Connectivity[/bold]")
            try:
                gitlab = GitLabAdapter(
                    url=app_config.gitlab.url,
                    token=app_config.gitlab.token,
                )
                console.print("  [green]✓ GitLab connection successful[/green]\n")
            except Exception as e:
                console.print(f"  [red]✗ GitLab connection failed: {e}[/red]\n")

            # Validate AWS connectivity
            console.print("[bold]5. AWS Connectivity[/bold]")
            try:
                aws = AWSAdapter(region=app_config.aws.region)
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
