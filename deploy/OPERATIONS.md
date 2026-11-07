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

Create an archive using `python deploy/package.py <archive.tgz>`. The packager includes only `app`, `deploy` and the server requirements. It excludes credentials, data, SSH keys, virtual environments and bytecode caches. Transfer the archive, verify `/opt/prism-learning/.prism-owned` exists, extract into that directory, and restart only the Prism service. Preserve the data directory and environment file.

The exact tested ARM dependency versions are in `deploy/requirements-server.lock`. For reproducible fresh installs, install that lock file. The bootstrap script rejects an unrelated application directory, but it is intended for initial provisioning, not routine updates.

## Storage and durability

The SQLite database uses WAL and a small checkpoint interval. PDFs are physically deduplicated while access remains account-specific. Previews are JPEGs generated on demand and evicted above a 32 MB cache cap. Application upload, account, conversation, notebook and daily question limits bound growth.

There is no external automated backup configured. Before significant maintenance, use SQLite's backup API to create a consistent database snapshot and back up original PDFs separately. Account exports contain chats, notes and document metadata, not the PDF binaries. Do not copy a live SQLite database without its WAL or the backup API. No unrelated server backup configuration was changed.

Users recover accounts with a one-time recovery key saved at signup. Recovery rotates that key and revokes sessions. Email delivery and email verification are not configured. Never send account passwords, recovery keys or API credentials in public issue reports.

For long-term hosting, replace the temporary third-party DNS hostname with a domain you control, update only Prism's virtual host and public-origin setting, issue the replacement certificate, and validate before reloading.
