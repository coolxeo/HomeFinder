# HomeFinder: architecture study notes

Speaker notes, not slides. One line per decision, then why. All numbers are our assumptions unless marked as a GCP limit or price. Long-form notes per component (podcast source): `speaker-notes-components.md`.

## Section picks
- **High-level:** MLS integration and data pipeline
- **Deep dive:** geospatial property search
- **Scaling:** cost optimization (build vs buy, BigQuery slots)

## The rule
**Managed where the protocol is open, proprietary only behind an adapter.**
- Why: leaving AlloyDB (Postgres) or Memorystore (Redis protocol) is a migration, not a rewrite.
- Proprietary services (Pub/Sub, Cloud Tasks, BigQuery) stay off the user request path, behind one adapter or in open formats.

## Numbers to remember
- 100M monthly users, 200M properties, 800+ MLS feeds, 5M active listings
- ~1M listing changes/day = **~12 events/s** avg, ~100/s burst
- ~25k peak search QPS, p95 < 200 ms, ~40% served from cache
- Golden record: 200M x ~10 KB = **~2 TB**

## Eventing
- **Pub/Sub over Kafka.** We have 12 events/s, and Kafka means brokers and partitions sized for scale we don't have.
- **Pub/Sub over Cloud Tasks for fan-out.** A Cloud Task hits one target, so 5 consumers means 5 tasks, and every new consumer changes the producer. A Pub/Sub topic just gets one more subscription.
- **Cloud Tasks for MLS polling.** One queue per MLS, with the rate cap set to that MLS's contract (GCP limit: up to 500 dispatches/s per queue). A slow MLS can't starve the others, and retries with backoff come built in.
- **Version check over ordering keys.** Ordering keys only keep publish order. Races between workers, redelivery and replay need "write only if the MLS `ModificationTimestamp` + sequence is newer". On top of that, one poison message blocks its whole ordering key.
- **Adapter + CloudEvents envelope.** The lock-in is one module, so swapping to Kafka later means one rewrite, not N.
- **Eventarc only for GCS triggers.** Example: photo uploaded, then Cloud Run makes thumbnails. It isn't the business event bus.
- **Dead-letter topic per subscription.** A bad message is parked, not retried forever.

## Data
- **AlloyDB over Spanner.** ~2 TB at 12 writes/s from one write region. Spanner sells multi-region writes and 99.999% that we don't need, and we'd lose PostGIS.
- **AlloyDB read pools behind the cache.** Reads that miss the cache go to a read pool, never to the primary.
- **Pub/Sub BigQuery subscription over Datastream.** Every change lands as history (price history, days on market, training data) with zero pipeline code.
- **Lake as BigQuery tables for Apache Iceberg on GCS.** Open format, so any engine can read it, which follows the rule.

## Cache (build vs buy)
- **Chosen: Memorystore for Valkey.** We buy it: Google runs failover with replicas at a 99.99% SLA, and it speaks the Redis protocol, so it passes the rule.
- **Why speed doesn't decide:** the hot set is ~50-100 GB at a few hundred k ops/s. A small Valkey cluster handles that.

**Why not Dragonfly (build, self-host on GKE)**
- Its edge is multi-threading: one big node replaces a sharded cluster, with no fork on snapshot. At our size that saves a handful of nodes, not a fleet.
- Failover, upgrades, backups and the pager become ours, and that costs more than the cache bill we'd save.
- BSL license and one vendor. Its multi-node setup is newer than Redis clustering.
- **Switch trigger:** cache becomes a top-3 cost, or a hot key outgrows one shard. The cache can be rebuilt from AlloyDB, so it is the safest thing to self-host later.

**Why not Redis (Memorystore for Redis Cluster, or Redis Cloud)**
- Redis moved off BSD in 2024 (RSAL/SSPL, AGPL added in 2025). Valkey is the BSD fork under the Linux Foundation, with the same API and tools.
- Redis Cloud extras (active-active geo, search modules) aren't needed: search lives in OpenSearch, and we write from one region.
- Same performance class as Valkey, so the license and roadmap decide.

## ML (valuation / price prediction)
- **XGBoost in a container over Vertex AI endpoints.** Train on BigQuery data, run as a Cloud Run job or on GKE. The same image runs anywhere.
- **BigQuery ML as the day-one baseline.** `CREATE MODEL ... BOOSTED_TREE_REGRESSOR` gives a benchmark in hours. Production moves to the container once we need custom features.
- **Nightly batch scores into AlloyDB, not live scoring.** Values change slowly. Re-score only homes touched by a `property.changed` event, and pages read a stored number.

## Search and geospatial (deep dive)
- **OpenSearch on GKE over Vertex AI Search.** We need `geo_shape`, custom ranking and facets we control. Vertex AI Search is a relevance black box and not geo-first.
- **Escape hatch:** Elastic Cloud on GCP if running the cluster ourselves hurts. Same query model.
- **PostGIS for geometry at write time.** Neighborhood and school-zone polygons are computed once per write (~1M/day), not per search (~400M/day).
- **H3 cells precomputed on each listing.** The search filters by cell term first, then runs the exact check only on the boundary ring.
- **BigQuery GIS for analytics only.** Market heatmaps and AVM features like distance to transit. It never sits on the request path.

## Cost optimization (scaling section)
- **Illustrative bill, sums to 100%:** photo storage 30, image egress + CDN 25, search compute 15, AlloyDB 9, BigQuery 6, batch + ML 5, cache 4, Cloud Run APIs 3, Pub/Sub + Tasks + other 3. Photos plus egress are over half, so start there.
- **BigQuery editions slots for steady jobs, on-demand for ad hoc.** ETL and training run on a baseline reservation with autoscaling. Analysts pay per TiB scanned (on-demand list price ~$6.25/TiB).
- **Partition by date, cluster by geo/H3.** Queries scan only the days and cells they need, which cuts the bytes billed.
- **BigQuery long-term storage.** Tables untouched for 90 days automatically drop to ~half price.
- **Photos are the biggest storage cost.** Use GCS lifecycle rules: Standard, then Nearline at 30 days, Coldline at 90 days, Archive for sold listings. Resize on upload, and serve hot images from Cloud CDN.
- **Spot VMs for batch.** Nightly scoring and reindexing can be interrupted, and GCP lists up to ~91% off.
- **Committed use discounts for the steady base.** AlloyDB and the core GKE nodes run 24/7.
- **Cache as a cost lever.** A ~40% hit rate means ~40% less search compute.
- **Build vs buy in one line:** buy what is stateful, painful to run and speaks an open protocol (AlloyDB, Memorystore). Build what differentiates us (ranking, valuation).

## Compute
- **Cloud Run for stateless APIs and workers.** It scales to zero, bills per request, and runs plain containers, so it passes the rule.
- **GKE only for OpenSearch.** It's our one stateful build: geo plus ranking is the product, so we keep control. Elastic Cloud is the buy fallback.
- **Photos: GCS upload, then Eventarc, then a Cloud Run resize, then Cloud CDN.** Resize once at write time, never per view.

## Edge and multi-region
- **One write region plus an AlloyDB cross-region secondary for DR.** At 12 writes/s there's no need for multi-region writes, and DR is a promotion, not a rebuild.
- **Global external load balancer + Cloud CDN + Cloud Armor.** One anycast IP. The CDN absorbs photos and anonymous search pages, and Armor blocks scrapers and runs WAF rules before traffic reaches us.
- **Warm OpenSearch standby in the DR region, fed from Pub/Sub.** The 20 GB hot index makes it cheap. Serve from it only on a region loss, or if p95 ever needs a second serving region.
- **Data locality:** listings are US public data, so there's no residency constraint. User PII stays in the primary region.
