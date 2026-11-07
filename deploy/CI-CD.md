# Prism CI/CD

The workflow in `.github/workflows/prism.yml` tests pushes and pull requests. Only a successful main-branch push or manual run on main can deploy to the protected `prism-production` environment. Feature branches and pull requests never receive production credentials.

## Pipeline

1. Run Python tests on Python 3.11 and 3.12, numerical JavaScript checks, JavaScript/Python/shell syntax checks and a tracked-source credential/runtime-file scan. Tests use mocks, not billable model API calls.
2. Build a deterministic, validated source archive and SHA-256 checksum. Upload the tested artifact with seven-day retention.
3. Download that artifact in the deployment job. Connect using a separate, restricted Ed25519 key and a pinned server host key.
4. The root-owned receiver verifies the archive checksum, commit, paths, file types and size limits. It rejects traversal, links, secrets/data file paths and unpinned dependency URLs/options.
5. Reuse the existing dependency environment when the lock matches. New locks build wheels in an unprivileged account, without pip caching. Dependency environments have a 256 MB limit; unused environments are pruned after successful release switching.
6. Save one consistent pre-deployment SQLite snapshot, switch release/environment links, and restart only `prism-learning.service` with graceful shutdown enabled.
7. Check loopback health against the exact tested commit. A failed application health check restores the previous code and dependency links. Verify the public HTTPS health endpoint separately.

Actions are pinned to full commit SHAs. Main deployments are serialized. No server-side Git checkout, broad admin key, local model, Docker build or nginx reload is required for routine deployment. User uploads and `/etc/prism-learning.env` are outside releases and preserved.

## Deployment access

GitHub environment `prism-production` permits only the main branch.

Environment secrets:

- `PRISM_SSH_PRIVATE_KEY`: dedicated deployment key, not the user's Oracle admin key.
- `PRISM_SSH_KNOWN_HOSTS`: pinned host key obtained through the existing trusted admin connection.

Environment variables:

- `PRISM_HOST`: the Oracle hostname/IP.
- `PRISM_DEPLOY_USER`: `prism-deploy`.
- `PRISM_URL`: the public HTTPS origin.

The deployment account's authorized key has forwarding/PTY restrictions and a forced entry point. It can submit only a checksummed Prism deployment command. The sudo rule permits only the fixed Prism release receiver. Root policy helpers are installed separately under `/usr/local/lib/prism-cicd`; application artifacts cannot overwrite them. The application continues to run as its existing unprivileged service account.

## Server layout and retention

- `/opt/prism-learning/current`: active source release.
- `/opt/prism-learning/current-venv`: active dependency environment.
- `/opt/prism-learning/releases`: current and previous successful releases.
- `/opt/prism-learning/venvs`: environments needed by the retained releases, reused by lock hash.
- `/var/lib/prism-learning/deploy-backups/predeploy.sqlite`: one root-only pre-deployment database snapshot, replaced each deployment. PDFs are not duplicated.
- `/etc/systemd/system/prism-learning.service.d/ci.conf`: Prism-only service overrides.

The original environment is reused for the first deployment, keeping storage small. The SQLite snapshot is for operator recovery; automatic rollback restores code, not the live database, to avoid discarding concurrent user data. Schema changes must remain backward compatible until a separate migration plan is implemented. There is no off-server backup or zero-downtime multi-instance deployment.

## Use it

Push a feature branch to run CI. Merge/push changes to main to run CI and deploy automatically. In GitHub Actions, run this workflow manually on main to redeploy the same commit. An already healthy identical release is a no-op.

To revert a release after a successful deployment, revert its Git commit on main and let CI test/deploy the revert. Automatic rollback covers failed application startup/health checks. A public HTTPS-only failure is reported for operator inspection; an unrelated DNS issue does not blindly revert a healthy app.

Dependency updates should update `deploy/requirements-server.lock` with tested Python 3.12 Linux-compatible package pins. Root policy, service-level permissions or nginx changes require the existing server operator connection; CI cannot make those changes.

## One-time setup

The server operator installs `archive.py`, `receiver.py` and `ssh_entry.py` as root-owned helpers, then runs `sudo python3 deploy/provision_ci.py <dedicated-public-key-file>`. The provisioner checks Prism ownership markers, creates separate deployment/build accounts, adopts a rollback baseline and reloads systemd configuration. It does not modify another website, database or service. Rotate keys by updating the dedicated authorized key and its GitHub environment secret together.
