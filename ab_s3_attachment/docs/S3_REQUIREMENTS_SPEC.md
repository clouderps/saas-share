You are working on an existing production Odoo SaaS platform.

The current SaaS deployment module is already implemented and partially working, but the S3 integration is not reliable or complete.

Your task is NOT to blindly rewrite the module.

First inspect the existing implementation, understand the current architecture, identify what is working, identify what is broken or incomplete, and then improve the existing implementation into a production-grade Odoo SaaS storage and backup architecture.

Target environment:

* Odoo 18
* Multi-database SaaS architecture
* Each customer has a separate Odoo database
* Multiple Odoo application servers may exist behind a Load Balancer
* PostgreSQL is separate from the Odoo application servers
* AWS infrastructure
* Amazon S3 is the object storage layer
* Existing SaaS provisioning/deployment module already exists
* Existing backup and snapshot functionality already exists
* Do not destroy existing working functionality
* Preserve backward compatibility wherever possible
* New custom modules must follow the existing project naming conventions
* Use ab_ prefix for any new custom addon if a new addon is genuinely required

MAIN OBJECTIVE

Create a reliable centralized storage architecture for the SaaS platform where:

1. Odoo tenant filestore uses S3 as durable shared storage.
2. Multiple Odoo application servers can access the same tenant files safely.
3. Tenant storage is isolated.
4. Existing local filestore data can migrate to S3 without data loss.
5. Backup operations store PostgreSQL backups in S3.
6. Snapshots store the exact recoverable state of a tenant.
7. Snapshot retention and backup retention are configurable.
8. Old backup and snapshot data is automatically cleaned according to retention policies.
9. Filestore cleanup never removes data still required by a retained snapshot.
10. Session storage is redesigned correctly for a multi-node SaaS environment.
11. Backup and restore operations are verifiable.
12. S3 failures do not silently corrupt tenant data.
13. The system provides monitoring, logs, retry handling and health checks.
14. The architecture works correctly behind AWS Load Balancer.
15. The system remains maintainable for hundreds of tenants.

IMPORTANT ENGINEERING RULE

Do not assume the current implementation is correct.

Before changing anything:

* Inspect all existing addons related to SaaS.
* Inspect all S3-related Python code.
* Inspect all backup-related code.
* Inspect all snapshot-related code.
* Inspect all filestore-related code.
* Inspect session handling.
* Inspect cron jobs.
* Inspect configuration models.
* Inspect security access rules.
* Inspect AWS configuration.
* Inspect deployment scripts.
* Inspect PostgreSQL backup logic.
* Inspect restore logic.
* Inspect tenant lifecycle operations.
* Inspect database creation/deletion logic.
* Inspect any code that copies, moves, deletes, archives or restores files.
* Inspect nginx configuration if it is part of the current architecture.
* Inspect Docker/systemd deployment if applicable.

Search the entire repository for:

* filestore
* data_dir
* session_dir
* sessions
* ir.attachment
* _file_write
* _file_read
* _file_delete
* attachment
* backup
* snapshot
* pg_dump
* pg_restore
* tar
* zip
* boto3
* s3
* delete_object
* put_object
* get_object
* upload_file
* download_file
* presigned
* retention
* cron
* database creation
* database deletion

Produce an architecture and code audit before implementation.

AUDIT REPORT

Create a technical report named:

S3_SAAS_ARCHITECTURE_AUDIT.md

The report must contain:

1. Current architecture.
2. Current data flow.
3. Current filestore implementation.
4. Current session implementation.
5. Current backup implementation.
6. Current snapshot implementation.
7. Current retention implementation.
8. Current S3 implementation.
9. Current tenant isolation implementation.
10. Current failure handling.
11. Current concurrency handling.
12. Current migration functionality.
13. Security issues.
14. Performance issues.
15. Data consistency risks.
16. Backup and restore risks.
17. Recommended architecture.
18. Files/modules that must change.
19. Files/modules that should remain unchanged.
20. Risks and mitigation.

Do not begin large refactoring before this audit is complete.

S3 ARCHITECTURE

Design the S3 architecture around clear logical separation.

Recommended structure:

Bucket:
ghaima-saas-prod

Prefix structure:

tenants/ <tenant-id>/
filestore/
metadata/

backups/
postgres/
manifests/

snapshots/ <snapshot-id>/
database/
manifests/
metadata/

sessions/
active/
archived/

staging/
uploads/

or use separate buckets where this is more secure or operationally appropriate.

Do not expose customer database names directly in public URLs or bucket keys if the database name contains customer-identifying information.

Prefer an internal immutable tenant identifier.

Tenant object key example:

tenants/<tenant_uuid>/filestore/<odoo-filestore-relative-path>

Tenant isolation must be enforced in application code.

Never trust a bucket key supplied by the HTTP client.

S3 must never become a direct authorization bypass.

FILESTORE REQUIREMENTS

The Odoo filestore must become a durable shared storage layer.

The implementation must preserve normal Odoo attachment behavior.

Required operations:

* create file
* read file
* update file
* delete file
* existence check
* checksum validation
* migration
* restore
* garbage collection

Do not store large binary content inside PostgreSQL unless Odoo already requires it.

Use S3 for durable file content.

Preserve Odoo attachment checksum semantics.

Where possible, use content-addressable storage.

For example:

filestore/<checksum-derived-path>

Do not overwrite an existing content-addressed object with different data.

Implement idempotent uploads.

If an object already exists with the expected checksum:

* verify it
* reuse it
* do not upload it again

For uploads:

* calculate checksum
* upload
* verify upload
* persist the Odoo attachment record
* handle failure without leaving inconsistent database references

Do not create an Odoo database reference before the S3 object is safely available unless the existing transaction design explicitly supports pending uploads.

Implement a safe staged upload flow if required.

Example:

staging/<tenant>/<upload-id>

then finalize:

tenants/<tenant>/filestore/<key>

A failed upload must not leave unbounded orphan objects.

Implement orphan detection.

FILESTORE DOWNLOAD

Downloads must preserve Odoo security.

Do not expose raw public S3 URLs.

The user must still pass Odoo access control checks before retrieving an attachment.

Preferred architecture:

Browser
|
v
Odoo authorization
|
v
short-lived S3 presigned GET URL
|
v
S3

Presigned URLs must:

* expire quickly
* never expose AWS credentials
* only point to the requested object
* only be generated after Odoo validates access
* use Content-Disposition correctly
* support large files

If presigned URLs conflict with existing Odoo behavior, keep the existing Odoo download route and stream through the backend.

Optimize large file transfers without loading the full file into Python memory.

Do not use memory-heavy base64 conversions for large files.

MULTI-NODE REQUIREMENTS

The application must work correctly when:

Odoo Node A
Odoo Node B
Odoo Node C

all access the same SaaS tenants.

No tenant file must depend on a local server filesystem.

The architecture must not require sticky sessions for correctness.

Local filesystem usage should be limited to:

* temporary files
* temporary uploads
* cache
* logs
* runtime data

Persistent tenant files must use S3.

SESSION ARCHITECTURE

Treat sessions separately from filestore.

Do not blindly store live sessions in S3 without evaluating performance and concurrency.

Inspect the current Odoo session implementation and determine the correct backend.

Preferred architecture for production multi-node runtime:

Odoo
|
v
Redis session backend
|
v
shared Redis

S3 should be treated as durable object storage, not as a high-frequency session database.

If the existing business requirement explicitly requires S3 as the session backend, implement an S3-backed session store safely.

Requirements for S3 session mode:

* custom session backend
* short TTL
* read-through local cache
* controlled writes
* retry handling
* corrupted session handling
* missing session handling
* logout invalidation
* session expiration
* garbage collection
* tenant isolation
* protection against stale overwrites
* no inclusion of active sessions in normal database snapshots
* no long-term retention
* no Object Lock
* aggressive lifecycle policy

Do not use S3 versioning as unlimited storage for high-frequency session writes.

Make session backend configurable:

session_backend = redis
or
session_backend = s3
or
session_backend = local

Default production recommendation should be Redis if Redis is already available.

BACKUP ARCHITECTURE

Backups must be application-consistent.

A tenant backup must contain enough information to restore the tenant independently.

Required backup components:

1. PostgreSQL database dump.
2. Filestore state or filestore manifest.
3. Tenant metadata.
4. Odoo version.
5. Installed module versions.
6. SaaS tenant identifier.
7. Backup timestamp.
8. Backup type.
9. Database checksum.
10. Filestore manifest checksum.
11. Backup format/version.
12. Restore metadata.

Do not consider "pg_dump completed successfully" as a complete SaaS backup.

A backup is successful only when all required components are uploaded and verified.

BACKUP FORMAT

Use a structured layout.

Example:

backups/postgres/<tenant_uuid>/<YYYY>/<MM>/<DD>/<backup_id>.dump

backups/manifests/<tenant_uuid>/<backup_id>.json

The manifest must contain:

* backup_id
* tenant_id
* database name
* database UUID if available
* Odoo version
* module version
* creation timestamp
* PostgreSQL dump object key
* PostgreSQL dump size
* PostgreSQL checksum
* filestore manifest key
* filestore object count
* total filestore size
* manifest checksum
* retention class
* expiration timestamp
* status
* encryption information
* software version that created the backup

Use atomic backup states:

STARTED
UPLOADING
VERIFYING
COMPLETED
FAILED
RESTORING
RESTORED
EXPIRED
DELETING
DELETED

Never mark a backup COMPLETED before verification succeeds.

DATABASE BACKUP

Use pg_dump in a reliable format suitable for restore.

Do not run large backup operations synchronously inside an HTTP request.

Use background processing or controlled cron/worker execution.

Implement:

* timeout
* retries
* disk space check
* PostgreSQL connectivity check
* pg_dump exit-code verification
* output file existence check
* checksum
* upload retry
* S3 verification
* cleanup

For large database backups:

* use multipart S3 upload where appropriate
* avoid loading the entire dump into RAM
* stream or use temporary disk files
* clean temporary files after success/failure

FILESTORE SNAPSHOT DESIGN

A snapshot must represent a recoverable point-in-time tenant state.

Do not blindly copy the entire filestore for every snapshot if the filestore uses content-addressed immutable objects.

Use manifests and object references where possible.

For each snapshot:

snapshot_id
tenant_id
database_backup
filestore_manifest
configuration
module_versions
created_at
status
retention_policy
expires_at

The filestore manifest should identify the exact objects required for restoration.

Example:

{
"tenant_id": "...",
"snapshot_id": "...",
"created_at": "...",
"objects": [
{
"key": "...",
"size": 123456,
"checksum": "...",
"s3_version_id": "...",
"etag": "..."
}
]
}

Use S3 VersionId when available and useful.

Do not depend only on ETag as a cryptographic checksum.

Prefer SHA-256 or S3 checksum metadata for integrity validation.

SNAPSHOT CONSISTENCY

The backup process must prevent a mismatch between PostgreSQL state and filestore state.

Design and document one of these approaches:

1. controlled maintenance/read-only mode during snapshot
2. application-level write freeze
3. transaction-aware snapshot strategy
4. delayed filestore deletion with retention grace period
5. immutable content-addressed object strategy
6. manifest strategy with consistency guarantees

Choose the approach that fits the existing SaaS architecture.

Do not claim a snapshot is point-in-time consistent unless the implementation proves it.

FILESTORE GARBAGE COLLECTION

This is extremely important.

Never delete an S3 filestore object only because it is no longer referenced by the current database.

A retained snapshot might still reference it.

Implement reference-aware garbage collection.

An object is eligible for deletion only when:

* it is not referenced by the active tenant filestore
* it is not referenced by any retained backup
* it is not referenced by any retained snapshot
* it is outside the configured grace period

Example:

current DB references
+
retained snapshot references
+
retained backup references
+
grace period
============

safe deletion decision

Implement a dry-run garbage collector.

Example result:

Found objects: 10,000
Active references: 8,900
Snapshot references: 700
Backup references: 200
Safe to delete: 200
Unsafe objects: 9,800

Do not delete anything in dry-run mode.

RETENTION ENGINE

Retention must be configurable.

Do not hardcode retention periods.

Support policies such as:

Session retention:
1 to 7 days

Daily backup retention:
7 days

Weekly backup retention:
4 weeks

Monthly backup retention:
12 months

Snapshot retention:
custom per tenant or global policy

Retention configuration must support:

* global default
* per SaaS tenant override
* backup type
* snapshot type
* enabled/disabled
* retention days
* retention count
* schedule
* timezone
* deletion grace period

Use both application-level retention logic and S3 lifecycle rules.

Application logic must make the business decision about whether an object is safe to delete.

S3 lifecycle rules should provide infrastructure-level cleanup for objects such as:

* expired staging files
* abandoned multipart uploads
* old noncurrent versions
* expired temporary files

Do not rely on S3 Lifecycle alone for coordinated snapshot deletion.

S3 VERSIONING

Evaluate S3 Versioning.

Recommended usage:

* backups
* backup manifests
* snapshot manifests
* critical recovery objects

For filestore, evaluate cost versus recovery requirements.

For session storage, do not retain unlimited versions.

If Versioning is enabled, configure noncurrent version lifecycle policies.

Avoid creating excessive versions for frequently overwritten objects.

S3 security guidance recommends Versioning and lifecycle controls for recovery and cost management. Apply them selectively according to workload.

S3 OBJECT LOCK

Use Object Lock only where immutable backup protection is required.

Recommended:

Backups:
Object Lock optional and configurable

Snapshot manifests:
Object Lock optional

Live filestore:
do not enable immutable retention behavior unless explicitly required

Sessions:
never use Object Lock

Object Lock requires S3 Versioning.

Do not make normal application file deletion impossible through Object Lock.

ENCRYPTION

Use server-side encryption.

Preferred production option:

SSE-KMS

Configuration:

s3_encryption_enabled
s3_encryption_type
s3_kms_key_id

Support:

SSE-S3
SSE-KMS

Do not hardcode encryption configuration.

AWS CREDENTIALS

Never store AWS access keys in source code.

Never commit:

AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY

Use IAM Role / Instance Profile / Task Role wherever possible.

The Odoo runtime role should have only the minimum required permissions.

Separate permissions logically:

Application:
read/write tenant filestore

Backup worker:
write backups
read backups
manage manifests

Restore worker:
read backups
read snapshots
write restored tenant files

Do not give the main application unrestricted S3 permissions if they are unnecessary.

IAM POLICY

Create an example least-privilege IAM policy in:

docs/aws-iam-policy.json

Separate the permissions for:

* runtime
* backup
* restore
* administration

Do not use s3:*

unless there is a documented reason.

S3 DATA INTEGRITY

Every important object must have integrity validation.

Use:

* SHA-256
* S3 checksum
* object size
* expected key
* optional VersionId
* manifest checksum

After upload:

1. confirm upload completed
2. validate size
3. validate checksum
4. persist metadata
5. mark object as verified

If verification fails:

* mark operation FAILED
* retry
* do not report success
* keep diagnostic information

RETRY POLICY

Implement controlled retries for AWS failures.

Handle:

* timeout
* connection reset
* throttling
* temporary AWS errors
* 5xx
* incomplete multipart upload

Use exponential backoff with jitter.

Do not retry:

* authorization errors
* invalid bucket
* invalid credentials
* malformed object key
* permanent validation failures

Do not retry forever.

S3 HEALTH CHECK

Create an S3 health service.

Checks:

* credentials
* bucket access
* region
* put
* get
* delete where safe
* checksum
* encryption configuration

Do not delete production objects during a health check.

Use a temporary test prefix:

healthcheck/<instance>/<uuid>

Write
Read
Verify
Delete

Then record result.

S3 HEALTH STATUS:

HEALTHY
DEGRADED
FAILED

Do not automatically switch to local filestore silently when S3 fails.

Silent fallback creates inconsistent multi-node data.

FAILURE MODE

Define behavior when S3 becomes unavailable.

For example:

Upload:
fail clearly and keep the transaction safe

Download:
return controlled error

Backup:
mark FAILED and retry later

Snapshot:
mark FAILED and do not report completion

Garbage collection:
pause safely

Health checks:
mark DEGRADED or FAILED

Do not silently report successful operations when S3 is unavailable.

MIGRATION FROM LOCAL FILESTORE TO S3

Create a migration command.

Example:

odoo-bin s3-migrate-filestore --database <db>

It must support:

--dry-run
--verify
--resume
--batch-size
--delete-local
--keep-local
--tenant
--max-workers

Migration flow:

1. inspect local filestore
2. calculate files
3. calculate sizes
4. calculate checksums
5. upload to S3
6. verify
7. record migration state
8. continue
9. support resume
10. only delete local files after successful verification

Never delete local data before verification.

Migration must be idempotent.

If migration stops at 65 percent, running again must continue from 65 percent.

Provide progress:

Total files
Processed
Uploaded
Skipped
Failed
Bytes transferred
Percentage
Estimated remaining workload

RESTORE SYSTEM

Build a reliable restore flow.

Restore must support:

* restore to original tenant
* restore to a new tenant/database
* restore from full backup
* restore from snapshot
* verify before activation

Recommended flow:

1. locate backup/snapshot
2. verify manifest
3. verify PostgreSQL dump
4. create target database
5. restore PostgreSQL
6. restore required filestore objects
7. verify object count
8. verify checksums
9. update database configuration
10. run Odoo initialization/update checks
11. verify login
12. verify attachments
13. verify basic business operations
14. mark RESTORED

Do not replace a production database immediately.

Support a restore-to-test flow.

RESTORE VALIDATION

After restore, automatically check:

* Odoo starts
* database opens
* login works
* web UI responds
* attachments open
* images load
* PDF attachments load
* documents load
* company configuration exists
* users exist
* installed modules match expected versions
* filestore references are valid
* missing attachments count
* orphan attachments count

Produce:

RESTORE_VERIFICATION.md

FAILURE RECOVERY

Simulate:

* S3 unavailable
* PostgreSQL unavailable
* upload interrupted
* backup process killed
* Odoo worker killed
* server reboot
* network timeout
* partially uploaded snapshot
* deleted S3 object
* corrupted manifest
* corrupted database backup
* application running on another node
* two backup jobs starting simultaneously

The system must remain recoverable.

CONCURRENCY

Prevent two backup jobs for the same tenant from running simultaneously.

Prevent two snapshot jobs for the same tenant from conflicting.

Prevent backup retention and backup creation from racing.

Use database locks or another reliable distributed locking mechanism.

Do not rely on Python process-local locks in a multi-node environment.

Possible lock key:

s3_backup:<tenant_uuid>

snapshot lock:

s3_snapshot:<tenant_uuid>

Migration lock:

s3_migration:<tenant_uuid>

Make lock timeout configurable.

CRON DESIGN

Review every existing cron job.

Avoid multiple cron workers executing the same operation.

Required jobs:

* backup scheduler
* snapshot scheduler
* retention cleanup
* orphan cleanup
* multipart upload cleanup
* backup verification
* restore verification if applicable
* S3 health monitoring

Long jobs must support resume.

Each job must have:

* started_at
* finished_at
* duration
* tenant
* operation
* status
* error
* retry_count
* bytes processed
* files processed

ADMIN UI

Create a clean admin interface.

Global S3 configuration:

AWS Region
Bucket
Prefix
Encryption
KMS Key
Storage Class
Multipart Threshold
Multipart Chunk Size
Maximum Concurrency
Timeout
Retry Count

Filestore configuration:

Backend
Migration Status
Current Storage
Default Storage
Cache settings

Session configuration:

Backend
TTL
Cache settings
S3 session prefix if applicable

Backup configuration:

Frequency
Retention
Storage class
Encryption
Verification enabled
Compression
Maximum concurrent backups

Snapshot configuration:

Frequency
Retention
Immutable retention if enabled
Verification

Tenant-level view:

Tenant
Database
Storage usage
Attachment count
S3 status
Last backup
Last successful backup
Last snapshot
Last successful snapshot
Next backup
Next snapshot
Backup health
Restore test status

BACKUP DASHBOARD

Display:

Last successful backup
Last failed backup
Backup size
Duration
Number of files
Filestore size
Database size
Snapshot count
Retention status
S3 health
Last verification
Last restore test

ALERTING

Generate alerts for:

* no successful backup within expected window
* backup failure
* snapshot failure
* S3 unavailable
* restore verification failure
* unusual storage growth
* unusually large backup
* orphan object growth
* failed migration
* repeated upload failures

Do not generate alerts for harmless retryable transient errors unless the retry threshold is exceeded.

LOGGING

Use structured logs.

Every operation must include:

tenant_id
operation_id
backup_id
snapshot_id
database
S3 bucket
S3 key
status
duration
size
exception type

Do not log:

AWS secret keys
session contents
passwords
tokens
private customer data

PERFORMANCE

The implementation must avoid:

* loading large files into memory
* copying the entire filestore for every snapshot
* repeated checksum calculations where unnecessary
* unnecessary S3 HEAD requests
* excessive S3 LIST operations
* synchronous long-running HTTP operations
* one-request-per-file architecture where a batch operation is more appropriate

Use:

* streaming
* multipart upload
* controlled concurrency
* caching
* batching
* pagination
* resumable operations

Do not blindly increase concurrency.

Make concurrency configurable.

CACHING

Use local cache where appropriate for frequently accessed files.

Cache must never become the source of truth.

Invalidation must be safe.

If a cached object is missing or invalid:

retrieve from S3.

Never permanently depend on local cache.

TENANT DELETION

When a SaaS tenant is deleted:

Do not immediately delete all S3 data.

Implement a lifecycle:

ACTIVE
SUSPENDED
DELETION_PENDING
DELETED

On deletion:

1. disable tenant
2. stop new writes
3. create final backup if configured
4. mark deletion time
5. preserve retained backups
6. preserve retained snapshots
7. remove active filestore references
8. schedule object cleanup
9. permanently delete only after retention rules allow it

Tenant deletion must respect backup and snapshot retention.

DATABASE NAME CHANGES

Do not use the database name as the permanent storage identity.

Tenant storage identity must remain stable when a database name changes.

Use tenant UUID / immutable storage ID.

SECURITY

Review:

* SSRF
* path traversal
* tenant isolation
* S3 key injection
* unauthorized presigned URL access
* insecure bucket policies
* public bucket access
* IAM privileges
* credential exposure
* logging of credentials
* object overwrite
* attachment authorization

S3 bucket should not be public.

Block public access unless there is an explicitly documented exception.

Use TLS.

Add secure bucket policies.

S3 supports Versioning, Lifecycle, encryption, Object Lock, and replication capabilities. Use those capabilities where they support the SaaS recovery model rather than enabling every feature indiscriminately.

DATABASE AND FILESTORE CONSISTENCY

This is a critical requirement.

You must document exactly how the system guarantees:

PostgreSQL backup
+
Filestore state
===============

restorable tenant state

Do not use vague statements such as "snapshot completed".

Explain the exact consistency model.

Explain what happens if:

attachment upload happens during backup
attachment delete happens during backup
attachment update happens during backup
database transaction rolls back
Odoo worker crashes
S3 upload fails
PostgreSQL dump succeeds but filestore processing fails

The system must recover safely from every situation.

TESTING

Create a full automated test suite.

Unit tests:

* S3 key generation
* tenant isolation
* upload
* download
* delete
* checksum
* retry logic
* retention
* manifest
* session backend
* backup state transitions
* snapshot state transitions

Integration tests:

* real S3 or LocalStack if appropriate
* PostgreSQL
* Odoo
* Redis when enabled
* multiple workers

End-to-end:

1. Create tenant.
2. Login.
3. Upload attachment.
4. Verify S3 object.
5. Open attachment.
6. Modify attachment.
7. Create backup.
8. Create snapshot.
9. Delete attachment.
10. Run garbage collector.
11. Confirm snapshot object still exists.
12. Restore snapshot.
13. Verify attachment.
14. Test from another Odoo application node.
15. Test session from another application node.
16. Test S3 failure.
17. Resume failed backup.
18. Test retention.
19. Test tenant deletion.

Load tests:

* many attachments
* large attachments
* many tenants
* concurrent backups
* concurrent downloads
* multiple application servers
* high session traffic

REGRESSION SAFETY

Do not break:

* normal Odoo attachment upload
* chatter attachments
* email attachments
* documents
* reports
* generated PDFs
* website files
* portal attachments
* user images
* product images
* POS attachments if present
* import/export generated files if they use persistent storage
* any SaaS-specific file handling already implemented

Inspect where Odoo stores every persistent file type.

Do not assume ir.attachment is the only file storage mechanism.

DEPLOYMENT

Provide production deployment documentation:

docs/S3_DEPLOYMENT.md

Include:

1. AWS S3 bucket creation.
2. Bucket naming.
3. Prefix structure.
4. Versioning.
5. Lifecycle policies.
6. Encryption.
7. KMS.
8. IAM roles.
9. Bucket policy.
10. Environment variables.
11. Odoo configuration.
12. Redis configuration if enabled.
13. Cron configuration.
14. Monitoring.
15. Backup scheduling.
16. Restore procedure.
17. Migration procedure.
18. Disaster recovery procedure.

Provide an example environment configuration.

Example:

AWS_REGION=...
S3_BUCKET=...
S3_PREFIX=...
S3_ENCRYPTION=SSE-KMS
S3_KMS_KEY_ID=...
S3_ENDPOINT_URL=
S3_MULTIPART_THRESHOLD=...
S3_MULTIPART_CHUNK_SIZE=...
S3_MAX_CONCURRENCY=...
S3_CONNECT_TIMEOUT=...
S3_READ_TIMEOUT=...
S3_MAX_RETRIES=...

Do not hardcode secrets.

CLI

Provide administrative commands such as:

s3-health
s3-test
s3-migrate-filestore
s3-verify-filestore
s3-gc
s3-backup
s3-snapshot
s3-list-backups
s3-list-snapshots
s3-verify-backup
s3-restore
s3-verify-restore

Commands must support:

--tenant
--database
--dry-run
--force
--verify
--verbose

For destructive commands, require an explicit option.

Example:

--delete

DRY RUN

Every destructive storage operation must support dry-run mode.

Show:

Objects inspected
Objects referenced
Objects protected
Objects eligible for deletion
Objects selected for deletion
Estimated storage reclaimed

Do not delete anything during dry-run.

DOCUMENTATION

Create:

docs/S3_ARCHITECTURE.md
docs/S3_DEPLOYMENT.md
docs/S3_SECURITY.md
docs/S3_BACKUP_RESTORE.md
docs/S3_RETENTION.md
docs/S3_MIGRATION.md
docs/S3_DISASTER_RECOVERY.md
S3_SAAS_ARCHITECTURE_AUDIT.md
RESTORE_VERIFICATION.md

ARCHITECTURE DECISION

At the end of the implementation, create:

docs/ARCHITECTURE_DECISIONS.md

Document why each major decision was made.

Especially explain:

Why S3 for filestore
Why Redis or S3 for sessions
Why manifests are used
Why snapshots do or do not duplicate filestore objects
Why Versioning is enabled or disabled
Why Object Lock is enabled or disabled
Why Lifecycle rules are configured
How tenant isolation works
How retention works
How restore works
How consistency is guaranteed
How failure recovery works

CODE QUALITY

Follow Odoo development standards.

Use:

* proper models
* proper access rights
* proper transactions
* proper exception handling
* structured logging
* type hints where useful
* docstrings for complex components
* small services/classes
* dependency injection where appropriate
* testable components

Do not create huge Python files.

Do not place all S3 functionality inside one model.

Prefer a service architecture such as:

S3ClientService
S3StorageService
S3FilestoreService
S3SessionService
S3BackupService
S3SnapshotService
S3RetentionService
S3GarbageCollector
S3RestoreService
S3HealthService
S3MigrationService

Reuse existing services if equivalent services already exist.

Do not create duplicate functionality.

EXISTING MODULE FIRST

This is mandatory.

Before creating a new model, service, cron, or addon:

1. Search the existing repository.
2. Identify equivalent functionality.
3. Reuse it when safe.
4. Extend it when appropriate.
5. Only create new functionality when the existing implementation cannot support the requirement.

Do not duplicate existing SaaS features.

DO NOT BREAK CURRENT DATA

Before migration or destructive changes:

* create a verified backup
* run migration dry-run
* validate S3 access
* validate checksums
* validate object counts
* validate restore process

Do not automatically delete the current local filestore.

Do not automatically delete current backups.

Do not automatically delete existing snapshots.

FINAL IMPLEMENTATION REPORT

After implementation create:

S3_IMPLEMENTATION_REPORT.md

Include:

1. What was found.
2. What was broken.
3. What was changed.
4. What was preserved.
5. New architecture.
6. Database changes.
7. New configuration.
8. New cron jobs.
9. New CLI commands.
10. S3 structure.
11. Session architecture.
12. Backup architecture.
13. Snapshot architecture.
14. Retention architecture.
15. Security improvements.
16. Performance improvements.
17. Migration procedure.
18. Restore procedure.
19. Test results.
20. Known limitations.
21. Production rollout plan.

ROLLOUT PLAN

Use phases.

PHASE 1
Audit only.

Exit criteria:

* audit completed
* current implementation understood
* risks documented
* no production data changed

PHASE 2
S3 client and configuration.

Exit criteria:

* authentication works
* encryption works
* health check works
* test objects work

PHASE 3
Filestore integration.

Exit criteria:

* upload works
* download works
* delete works
* checksum works
* tenant isolation verified

PHASE 4
Migration.

Exit criteria:

* dry-run works
* migration works
* resume works
* verification works
* no local data deleted

PHASE 5
Backup.

Exit criteria:

* database backup
* filestore manifest
* verification
* retention
* failure recovery

PHASE 6
Snapshot.

Exit criteria:

* consistent snapshot
* snapshot manifest
* restore
* retention
* object protection

PHASE 7
Session architecture.

Exit criteria:

* multiple Odoo nodes share sessions
* login survives node changes
* logout works
* session expiration works
* no unnecessary S3 session growth

PHASE 8
Garbage collection.

Exit criteria:

* dry-run
* reference detection
* snapshot protection
* backup protection
* safe deletion

PHASE 9
Disaster recovery testing.

Exit criteria:

* full restore tested
* failed backup recovery tested
* S3 outage tested
* node failure tested
* tenant restore tested

PHASE 10
Production rollout.

Exit criteria:

* monitoring active
* alerts active
* verified backup available
* restore test successful
* migration verified
* rollback plan documented

IMPORTANT

Do not stop after writing code.

You must:

* inspect
* design
* implement
* test
* simulate failures
* verify backups
* verify restore
* review security
* review performance
* review data consistency
* produce documentation

Do not claim something is production-ready unless the relevant tests actually pass.

When an existing implementation conflicts with this design, explain the conflict and choose the safest production architecture.

Do not remove working functionality without proving it is obsolete or unsafe.

The final result must be suitable for a production Odoo SaaS environment with multiple application servers, multiple customer databases, centralized S3 storage, automated backups, snapshots, retention policies and disaster recovery.

