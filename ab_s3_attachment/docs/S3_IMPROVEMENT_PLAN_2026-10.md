# Ghaima S3 Attachments, Backups and Snapshots: Final Improvement Plan

*2026-10-09. Read-only research. No code, database or S3 object was changed.*

---

## الملخص التنفيذي (عربي)

**الوضع الحالي:** كل ملفات المستأجرين محفوظة على S3. عند التنزيل يُحوَّل المستخدم إلى رابط S3 موقَّع. مرفقات المحادثة (chatter) تُرفع من المتصفح مباشرة إلى S3 كروابط `cloud_storage`، تماماً كما يعمل Google Cloud Storage. هدف «حفظ أي مرفق في S3 واستخدام الرابط» **متحقق فعلياً** لكل ما يمكن أن يكون رابطاً.

**لماذا لا نحوّل كل شيء إلى روابط؟** بعض الملفات يحتاج Odoo نفسه إلى قراءة محتواها:
- فواتير ZATCA (XML/PDF والـ QR)
- الصور ومصغراتها
- ملفات الـ assets
- توليد PDF وإرسال البريد

لو صارت هذه روابط فقط فستتعطل الفوترة الإلكترونية. Odoo نفسه يستثنيها عمداً. تبقى هذه الملفات على S3 كـ binary يقرؤها Odoo عند الحاجة. التخزين نفسه (S3) واحد في الحالتين.

**الخطر الحقيقي ليس الرفع، بل:**
1. لا توجد Versioning على الـ bucket: أي حذف خاطئ أو مفتاح مسرَّب يعني فقدان الملفات نهائياً.
2. لا يوجد PITR لقاعدة البيانات: نقطة الاستعادة هي آخر dump، وخادم PG وحيد.
3. ملفات الروابط المحذوفة لا تُنظَّف أبداً ولا تُحسب في الحصة، والنسخ الاحتياطية لا تحميها.
4. اختبار الاستعادة يتحقق من قاعدة البيانات فقط، لا من وجود الملفات ولا من الـ snapshots.

**التوصية:**
- **المرحلة 0** (مع نشر الليلة، بدون إعادة تشغيل): تفعيل Versioning وقواعد Lifecycle، ونشر الـ GC الجديد للإنتاج بعد Fast Snapshot لـ fayia.
- **بعدها:** نقل قاعدة البيانات إلى قرص xvdb (80 GB) ثم WAL archiving عبر wal-g (فقد بيانات أقصاه ~1 دقيقة بدل يوم كامل)، واختبارات استعادة تتحقق من الملفات ومن سلامة فواتير ZATCA، ثم تنظيف ملفات الروابط بأمان.
- **الإجمالي:** ~12–14 يوم عمل للمراحل الأساسية. التكلفة الإضافية على AWS ~2–5 دولار شهرياً حالياً.

---

## Executive summary (EN)

- **"Same as Google Cloud Storage" is already delivered for the files where it can be.** Chatter uploads go browser→S3 as `cloud_storage` links (threshold 0). Every other file is on S3 and served through a signed 302.
- **Files Odoo must read stay S3-backed binaries:** ZATCA/invoice documents, field images, assets, PDF inputs and mail attachments. Converting them to link-only breaks e-invoicing. Odoo core excludes them for the same reason.
- **The real risks are elsewhere:**
  1. No S3 versioning (one bad delete or leaked key means permanent loss).
  2. No database PITR on a single PG master with a 19 GB root disk.
  3. Cloud-link files are never cleaned up and are not covered by snapshot manifests.
  4. Restore drills never check files or S3 snapshots.
- **Plan:** a cheap safety net first (tonight-safe, AWS config only), then a disk move plus wal-g PITR, proven restores, and cloud-file lifecycle.
- **Effort:** ~13 dev-days for Phases 0–4. Scale items are deferred to explicit triggers.

---

## 1. What we have today

| Area | Status |
|---|---|
| Filestore | 100% on S3 (`ab_s3_attachment`). Bucket `clouderps-saas-filestore`, prefix `entity_N/filestore/`, SSE, SHA-256 writes. |
| Downloads | Signed 302 to S3 (`ab_s3.signed_urls=True`). Each redirect does one extra `head_object` (`ab_s3_attachment/models/ir_attachment.py:465`). |
| Cloud links (GCS-style) | `ab_cloud_storage_s3`: browser presigned PUT. Row is `type='cloud_storage'` + `url`. Prefix `entity_N/cloud_storage/`. Plan-driven min size = 0. |
| Migration old→link | `_s3_migrate_to_cloud_storage`: server-side `copy_object`, record/chatter files only, templates excluded. |
| Tenant GC | Snapshot-aware (needs `.ghaima/protected.json`, 7-day grace, SHARE lock). **Demo only.** Prod still runs the old GC (G1). Lists `filestore/` only. |
| Snapshots | `pg_dump -Fc` streamed to S3, SHA-256, manifest of `store_fname`, protected list. "Fast" uses the same S3 dump path. |
| Retention | `plan_retention.py`: tiered daily/weekly/monthly. Deploy snapshots in their own lane (keep 2). |
| Restore test | Weekly, newest zip only, DB-level checks only. |
| DB | One PG16 master. No replica, no WAL archive. 19 GB root disk filled once (2026-10-03). 80 GB `xvdb` unused. |
| S3 protection | No versioning, no Object Lock, no off-site copy. Tenant keys hold `DeleteObject` on their prefix. |

---

## 2. Goal 1: GCS-style S3 attachments with URL links

### 2.1 Two-class model (keep it)

| Class | Storage | Who reads the bytes | Covers |
|---|---|---|---|
| **A. Link file** | `type='cloud_storage'`, `url` → S3 key | Browser only (signed 302, 300 s) | Chatter, discuss, record attachments not excluded by core |
| **B. S3-backed binary** | `type='binary'`, `store_fname` on S3 | Odoo server code; downloads still get a signed 302 | `res_field` images, `mail.thread.main.attachment` (invoices, bills, ZATCA XML/PDF), assets/website/`ir.ui.view`, report inputs, outgoing mail attachments |

Both classes keep 100% of their bytes on S3 and nothing on the app host. The only difference is whether Odoo may read the bytes.

### 2.2 Transparent fetch layer: not adopted

**Idea:** convert class B to `cloud_storage` and patch `raw`/`datas` to `get_object` the URL on demand.

**Rejected because:**
- `ab_s3_attachment._file_read` already does exactly this, so storage gains nothing.
- Core branches on `type`: `/web/image` resize is skipped for cloud rows (thumbnails break), ZATCA and `_get_invoice_legal_documents` expect binaries, and `cloud_storage_migration` and `_migrate_remote_to_local` assume link rows have no bytes.
- It patches core field computes, an upgrade hazard on every Odoo release.
- A silent `b''` on an S3 timeout could get a partial or empty ZATCA document signed. That is legal risk.

If the owner still wants it: ~3 days of work, with the risks above. Not recommended.

### 2.3 What actually improves Goal 1

1. **Check credential scope first (½ d).**
   - Find which keys sign `cloud_storage_s3` links: `SELECT key,value FROM ir_config_parameter WHERE key LIKE 'cloud_storage_s3_%' OR key LIKE 'ab_s3.%'`, plus `s3.tenant.credentials.s3_prefix`.
   - If the tenant IAM policy only covers `entity_N/filestore/*`, widen it to `entity_N/*` with an explicit **Deny on `entity_N/.ghaima/*`**. Re-push the policy only (`s3_tenant_credentials.py:86-97`).
   - Platform credentials must never sit in tenant ICP, because a tenant admin can read them.
2. **Finish the link rollout (½ d).**
   - Per tenant, count `type, res_field IS NULL` rows. Run `_s3_migrate_to_cloud_storage` where candidates are above 0.
   - Keep templates excluded.
   - Rollback: `_migrate_remote_to_local`.
3. **Cheaper downloads (½ d).**
   - ICP flag `ab_s3.signed_head_check` (default False) skips `head_object` before the 302. The hourly self-check covers missing objects.
   - Add `Cache-Control: private, max-age=<ttl-10>` on the 302, as `cloud_storage_google` does.
4. **Link-file lifecycle (2–3 d, only after the Phase 0 versioning step).** Steps a–c ship in this order:
   - a. `_build_manifest` (`s3_snapshot.py:121-217`) also collects `url` keys of `type='cloud_storage'` rows as `cloud_keys`. `protected.json` merges them.
   - b. Tenant GC (`ab_s3_attachment/models/ir_attachment.py:634-700`) also lists `entity_N/cloud_storage/`. A key is alive if it is referenced by `ir_attachment.url` or listed in `protected.json`. Same 7-day grace, same pause when `protected.json` is missing.
   - c. Dry-run ICP `ab_s3.gc_cloud_storage_dry_run=True` for one week on demo, then log-only on fayia, then live.
   - **Never delete on unlink.** Rollback and snapshot restores need the objects to still exist.
   - d. Quota: `_s3_get_usage_bytes` (`:739`) sums both prefixes.
   - e. One test, `ab_s3_attachment/tests/test_gc_cloud.py`, covering three cases:

     | Case | Expected |
     |---|---|
     | Orphan older than 7 d, not protected | Deleted |
     | Orphan that is protected | Kept |
     | Key that is still referenced | Kept |

---

## 3. Goal 2: Backups, snapshots and DR

### 3.1 S3 safety net (biggest risk, cheapest fix): Phase 0

Configure on `clouderps-saas-filestore`:
- **Bucket Versioning ON.**
- **Lifecycle rules:**
  - `NoncurrentVersionExpiration` after 30 d, plus `ExpiredObjectDeleteMarker`;
  - `AbortIncompleteMultipartUpload` after 1 d (failed `pg_dump` streams leave billed orphan parts).

No code change and no restart. GC deletes become delete markers, which can be undone for 30 days. Rollback: suspend versioning.

**Then remove `s3:DeleteObject` from tenant keys, but only after confirming** that tenant GC and the self-heal do not delete with tenant credentials. If they do, move deletion to platform-side first. Otherwise leave this as-is and rely on versioning.

### 3.2 DB disk, then PITR: Phases 1 and 2

1. **Move PGDATA (or at least `pg_wal`) to `xvdb` (80 GB).**
   - Steps: stop, rsync, change `data_directory`, start.
   - Keep the old directory until verified.
   - Expect 15–30 min of downtime for all tenants. Run it in a maintenance window outside fayia's meal times.
   - Alerts at 70% and 85% on both disks.
2. **wal-g on DB server 6.** Set up via `bk.server 6 _execute_command`.
   - Settings: `archive_mode=on` (restart, same window as the disk move), `archive_command='wal-g wal-push %p'`, `archive_timeout=60`, zstd compression, `max_slot_wal_keep_size` set.
   - Nightly delta `backup-push` (`WALG_DELTA_MAX_STEPS=6`), full on Sunday, `delete retain FULL 4`.
   - Dedicated IAM user scoped to the `wal/pg16-master/` prefix only.
   - **Required alerts:**
     - `pg_stat_archiver.failed_count > 0`
     - last archive older than 5 min
     - `pg_wal` over 5 GB

     A failing archive is the same failure class as the 2026-10-03 disk-full outage.
   - **Rollback:** `archive_command='/bin/true'` plus a reload (no restart needed).
   - **Result:** RPO goes from up to 24 h to about 1 min.
   - **Limit:** PITR is cluster-wide. Per-tenant restore to time T is a **runbook**, not a wizard: restore the cluster to scratch, `pg_dump` the one DB, then restore it through the cockpit.
3. **Before each deploy,** record `pg_current_wal_lsn()` in func_history next to the fast snapshot.

### 3.3 Restore drills v2: Phase 3 (`restore_test.py`)

- **Rotation:**
  - alternate weeks between the newest zip and the newest **S3 snapshot** (the deploy safety net has never been tested);
  - monthly, a wal-g PITR to now−1 h on xvdb scratch, as a manual runbook first.
- **New checks (any failure fails the drill):**
  1. `head_object` on a sample of 200 `store_fname` values plus 200 cloud keys, skipping `checksum IS NULL` rows (the 2025 empty bills).
  2. fayia ZATCA: last 20 `account.move` attachments, SHA-256(bytes) == `checksum`.
  3. Manifest SHA-256 == object hash, as a hard failure.
- **Guards:** skip the drill if DB-server free disk is below 2× the DB size. Drop `rtest_*` in `finally`.
- **Reporting:** results go to the cockpit Backups tab plus the existing alert digest.

### 3.4 Lifecycle tiers (config only, after measuring)

- Move `snapshots/` and `backups/` to Standard-IA or Glacier IR only after the real snapshot age distribution is known. The 30/90-day minimum-storage charges would otherwise cost more than they save.
- App-side `plan_retention.py` remains the primary deleter.

### 3.5 Immutable / off-site copies: deferred, triggered

- Separate `clouderps-saas-backups` bucket with **Object Lock in Governance mode** (14 d) for `snapshots/`, `backups/` and `wal/`.
  - Add ICP `ab_saas_backup_s3.bucket`. Make retention lock-aware. Tenant keys get no access.
- Cross-account replication to `me-central-1` (data-residency fit).
- **Trigger:** a second paying tenant, a contractual SLA, or backups over 100 GB.

---

## 4. Phased roadmap

| Phase | Deliverable | Modules / files | Effort | Risk | Rollback | Demo-first gate |
|---|---|---|---|---|---|---|
| **0 – Tonight-safe** | Versioning + lifecycle (3.1); G1 snapshot-aware GC to prod; credential-scope and type-count checks (2.3.1) | AWS console/CLI; cockpit deploy saas-share `ab_s3_attachment` (81c2859+) | 1 d | Low | Suspend versioning; redeploy previous commit (a missing `protected.json` pauses GC) | Demo GC clean since 2026-10-04; **Fast Snapshot fayia first**, outside meal times |
| **1 – DB disk** | PGDATA/`pg_wal` → xvdb, disk alerts | DB server 6, `ab_saas_monitor` alerts | 1 d + window | Medium (15–30 min downtime, all tenants) | Old data directory kept | Rehearse on a scratch PG |
| **2 – PITR** | wal-g + archiver alerts + first manual PITR drill + LSN in func_history | DB server 6 (systemd timer), `ab_saas_monitor`, deploy engine | 3 d | Medium (WAL fills disk if S3 is down → alerts) | `archive_command=/bin/true` + reload | Same window as Phase 1 |
| **3 – Proven restores** | Drill v2 (snapshot rotation, S3 sample, ZATCA checksum, disk guard) | `ab_saas_backup_s3/models/restore_test.py`, cron XML | 2–3 d | Low | Disable cron | Run on demo's snapshots first |
| **4 – Link lifecycle + perf** | Manifest `cloud_keys` → GC of `cloud_storage/` (dry-run) → quota; IAM widen + `.ghaima` deny; head-check flag + Cache-Control; migration sweep | `s3_snapshot.py`, `ab_s3_attachment/models/ir_attachment.py`, `ab_cloud_storage_s3`, `s3_tenant_credentials.py` | 4–5 d | Medium (wrong delete; covered by 30-d versions) | ICP kill switches; restore noncurrent versions | 1 week dry-run on demo; **must not start before Phase 0** |
| **5 – Triggered** | Object Lock backup bucket, cross-account replication, IA/Glacier tiers, CloudFront (egress over 100 GB/mo), PG streaming replica | `ab_saas_backup_s3`, AWS | 3–5 d | Low–Medium | ICP back to the old bucket | Per trigger |

**Total for Phases 0–4: ~12–14 dev-days.** Phases 0–2 (~5 d) remove most real data-loss risk. Rollout order for every phase: demo 84 → abdalmola-test 87 → templates → qira/stones/alshaya/yummy → fayia last.

---

## 5. Cost notes (us-east-1; verify current prices)

| Item | Estimate |
|---|---|
| Versioning (30-d noncurrent) | Mostly write-once bucket, about $1–3/mo now |
| wal-g WAL + base backups | 30–80 GB rolling, about $1–2/mo |
| Dropping `head_object` | About 50% fewer request-type calls per download |
| Object Lock bucket + replication | About 1.3× backup storage + $0.02/GB transfer (deferred) |
| CloudFront | Only once egress costs more than the setup work |

- The xvdb move is free, since the disk is already paid for.
- The DB server will limit growth (CPU and connections at ~30–40 tenants) long before S3 cost does.

---

## 6. Decisions needed from the owner

1. **Accept the two-class model.** Class B (ZATCA, images, assets) stays S3-backed binary rather than link-only. *Recommended: yes.*
2. **Maintenance window** for the PGDATA → xvdb move plus the `archive_mode` restart: 15–30 min of downtime for all tenants. Proposed: after midnight KSA, not at fayia meal times.
3. **Tonight's deploy scope:** only Phase 0 (AWS versioning/lifecycle + the G1 GC deploy). Phases 1–4 are scheduled separately. Note that the AI-agent/HR/API module deploys also requested tonight are separate work, not part of this plan.
4. **Tenant IAM:** widen to `entity_N/*` with a `.ghaima` deny (recommended), or move cloud keys under `filestore/`.
5. **Remove tenant `DeleteObject`?** Only if GC is confirmed platform-side; otherwise rely on versioning.
6. **Budget triggers for Phase 5:** Object Lock bucket, me-central-1 replica, and the second DB server (replica). Proposed trigger: a second paying tenant or an SLA contract.
7. **Data residency:** must backups stay in KSA or the GCC (me-central-1) for customer contracts?

---

**Key files**
- /home/clouderps/custom-addons/saas-share/ab_s3_attachment/models/ir_attachment.py
- /home/clouderps/custom-addons/saas-share/ab_cloud_storage_s3/models/ir_attachment.py
- /home/clouderps/custom-addons/saas-server/ab_saas_backup_s3/models/s3_snapshot.py
- /home/clouderps/custom-addons/saas-server/ab_saas_backup_s3/models/plan_retention.py
- /home/clouderps/custom-addons/saas-server/ab_saas_backup_s3/models/restore_test.py
- /home/clouderps/custom-addons/saas-server/ab_s3_storage_management/models/s3_tenant_credentials.py
- /home/clouderps/custom-addons/saas-share/ab_s3_attachment/docs/S3_SAAS_STORAGE_PLAN.md