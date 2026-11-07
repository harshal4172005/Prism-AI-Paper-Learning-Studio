# Isolated Oracle deployment

URL: https://prism.140.245.195.222.sslip.io/

The temporary hostname resolves to the user's Oracle server. HTTPS has its own certificate named `prism-learning`. Existing nginx site configuration files were preserved; the deployment adds a new virtual host and gracefully reloads nginx after a successful configuration test.

## Files belonging to this app

- `/opt/prism-learning`: application, virtual environment and release ownership marker.
- `/var/lib/prism-learning`: private SQLite library, original PDFs and bounded page-preview cache.
- `/etc/prism-learning.env`: root-only environment, provider keys and resource limits.
- `/etc/systemd/system/prism-learning.service`: dedicated service with CPU/memory controls.
- `/etc/nginx/sites-available/prism-learning`: new virtual host, linked from sites-enabled.
- `/etc/letsencrypt/renewal/prism-learning.conf`: new certificate renewal configuration.

The service runs as the non-login user `prism-learning`, listens on loopback port 8176 and has write access only to its data directory and private temporary space. It uses one Uvicorn worker and permits two AI generations concurrently. Authentication cookies are Secure and HttpOnly on the hosted origin. Production requests with a different Origin are rejected.

## Routine commands

```sh
sudo systemctl status prism-learning
sudo systemctl restart prism-learning
sudo journalctl -u prism-learning --since '10 minutes ago'
sudo systemctl show prism-learning -p MemoryCurrent -p MemoryPeak
sudo du -sh /opt/prism-learning /var/lib/prism-learning
```

Change limits or provider credentials in the root-only environment file, then restart only Prism. Do not edit another application's environment, database, service or nginx virtual host.

## Updating this release

Routine updates now go through GitHub Actions. Push a feature branch for CI, then merge/push to main for tested deployment. Follow `deploy/CI-CD.md` for the workflow, secrets, access boundaries and rollback behavior. Do not extract updates over the old top-level app directory; the live service reads `/opt/prism-learning/current`.

The current and previous releases live under `/opt/prism-learning/releases`. `/opt/prism-learning/current-venv` selects the dependency environment. A Prism-only systemd drop-in supplies these paths and the release SHA. The public health endpoint reports that SHA, so it can be compared to the successful Actions run.

For an operator-built artifact, use `python deploy/package.py <archive.tgz> --commit <full-commit-sha>` from a clean source checkout. The packager excludes credentials, PDFs, databases, SSH keys and local environments. The restricted receiver validates the digest and commit before switching releases. The bootstrap script is for initial provisioning only.

## Storage and durability

The SQLite database uses WAL and a small checkpoint interval. PDFs are physically deduplicated while access remains account-specific. Previews are JPEGs generated on demand and evicted above a 32 MB cache cap. Application upload, account, conversation, notebook and daily question limits bound growth.

Each deployment retains one root-only SQLite snapshot at `/var/lib/prism-learning/deploy-backups/predeploy.sqlite`. Automatic rollback restores code and dependency pointers, not live data. There is no off-server automated backup. Before significant maintenance, use SQLite's backup API to create a consistent database snapshot and back up original PDFs separately. Account exports contain chats, notes and document metadata, not the PDF binaries. Do not copy a live SQLite database without its WAL or the backup API. No unrelated server backup configuration was changed.

Users recover accounts with a one-time recovery key saved at signup. Recovery rotates that key and revokes sessions. Email delivery and email verification are not configured. Never send account passwords, recovery keys or API credentials in public issue reports.

For long-term hosting, replace the temporary third-party DNS hostname with a domain you control, update only Prism's virtual host and public-origin setting, issue the replacement certificate, and validate before reloading.
