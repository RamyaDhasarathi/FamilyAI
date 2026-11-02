# FamilyOS object storage (S3)

Originals (PDFs, photos, mail, screenshots) are never stored in the database. They are sealed and written to an S3-compatible object store. The `blobs` table holds the pointer and the wrapped key. This page documents the bucket, the key layout and what is inside an object.

## Backends

| Setting | Meaning | Default |
|---|---|---|
| `FAMILYOS_BLOB_BACKEND` | `local` writes to a directory (development and tests). `s3` uses any S3-compatible store: AWS S3, MinIO, Cloudflare R2. | `local` |
| `FAMILYOS_BLOB_DIR` | Directory used by the `local` backend. | `.blobs` |
| `FAMILYOS_S3_BUCKET` | Bucket name. | `familyos-originals` |
| `FAMILYOS_S3_ENDPOINT_URL` | Endpoint for a non-AWS store such as MinIO or R2. Unset for AWS. | unset |
| `FAMILYOS_S3_REGION` | Region. | `ap-south-1` |
| `FAMILYOS_S3_ACCESS_KEY_ID`, `FAMILYOS_S3_SECRET_ACCESS_KEY` | Credentials. Keep them out of git. | unset |

The store interface has three calls: `put(key, bytes)`, `get(key)` and `delete(key)`. Nothing lists the bucket, so a read-only role on `get` and a write role on `put` and `delete` is enough.

## Key layout

```
<bucket>/
  households/
    <household_id>/
      blobs/
        <blob_id>          one sealed object per stored original
```

- `household_id` and `blob_id` are random UUIDs. A key never contains a filename, a media type or a content hash, so the store learns nothing about what an object is.
- All objects are written with the content type `application/octet-stream`. They are ciphertext.
- The local backend uses the same layout under `FAMILYOS_BLOB_DIR`.

## What an object contains

An object is the original file, encrypted with AES-GCM:

1. Each blob gets its own random 256-bit data key.
2. The blob is sealed with that key. The additional authenticated data binds it to the household and to the SHA-256 of the plaintext, so an object cannot be moved to another household or swapped for different content.
3. The data key is itself sealed (wrapped) with a scope key and stored in `blobs.wrapped_key`. The scope key is the household key for a shared notice, or the member's key for a notice private to that member. The household key is stored only wrapped by the deployment's master key (`FAMILYOS_MASTER_KEY`, 32 bytes, base64).

So a copy of the bucket alone is unreadable. Reading needs the database row for the wrapped key and the master key.

## Pointers in the database

`blobs` columns: `id`, `household_id`, `sha256`, `size_bytes`, `media_type`, `storage_key`, `wrapped_key`, `sealed_for`, `created_at`. See `database-schema.md`.

- `storage_key` is the object key above.
- Deduplication is by `(household_id, sealed_for, sha256)`. The same bytes forwarded privately by two members are stored twice, because neither may open the other's copy. Household-wide deduplication would also let one member learn that another already holds the same file.
- `input_artifacts` points at a blob. Derived data (claims, obligations, medicines, receipt lines) lives in database tables and points back at the artifact.

## Erasure

Erasing a household destroys its wrapped key first. From that moment every copy of its objects, including ones in backups or on a lagging replica of the store, is unreadable. The objects are then deleted. Erasing one notice deletes its blob when nothing else points to it, and removes everything derived from it.

## Operating notes

- **Backups:** the bucket needs its own backup or versioning. `scripts/backup.sh`-style jobs that copy only the local directory do not cover S3.
- **Lifecycle rules:** do not expire objects by age. An object is deleted only when its notice or household is erased.
- **Rotating the master key:** re-wrap the household keys and the wrapped data keys. The objects themselves do not need re-encrypting.
- **Access:** give the application a role limited to this bucket. No public access, no listing for end users.
