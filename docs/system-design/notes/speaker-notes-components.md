# HomeFinder: component speaker notes

Long-form notes for every component in the explorer, written to be read aloud (good source for a podcast). Same text as the "Learn it" section in each detail panel. Numbers are our assumptions unless marked as a GCP limit or price.

## MLS integration and ingest

### MLS feeds + public data

**What it is.** The supply. More than 800 MLSs, the regional databases where agents list homes, plus public data: county deeds and tax rolls, school boundaries, crime and permits.

**How it works.** Most MLSs sit on one of about fifteen vendor platforms and speak the RESO Web API, older ones still RETS. So we write one adapter per platform and treat each MLS as config: credentials, poll cadence, field mappings and display rules.

**Why this choice.** We own our adapters instead of buying everything from one aggregator, because some aggregators belong to competitors; Bridge Interactive is owned by Zillow. Where an MLS already distributes through a neutral aggregator, we use it.

**The numbers.** About 1M listing changes a day across all feeds. 1M divided by 86,400 seconds is roughly 12 a second on average, with bursts of a few hundred when a big MLS publishes a batch.

**What can go wrong.** Feeds go quiet, change schemas without notice, or send a storm of updates after a fix on their side. We alert on silence per feed and hold alerts if a feed's change rate jumps five times.

### Feed

**What it is.** One MLS's stream of changes, pulled at its own pace. A feed has a cursor (the last modification timestamp we saw), a mapping version and a freshness target.

**How it works.** Every poll asks for records modified since the cursor, then moves the cursor forward. Once a night we pull the full list of active keys and diff it against ours, because many feeds never tell you about deletes.

**Why this choice.** Treating each MLS as its own feed means one slow or broken MLS never delays the others, and onboarding a new one is config, not code.

**The numbers.** Cadence is 1 to 15 minutes depending on the MLS contract. That poll interval is the floor on freshness; we can't be fresher than the source.

**What can go wrong.** Missed deletes and status changes are the classic accuracy bug; the nightly key diff catches them. A mapping bug is fixed by replaying raw payloads, not by re-pulling from the MLS.

### Cloud Tasks

**What it is.** Cloud Tasks is Google's managed task queue. Each task is an HTTP call that the queue delivers to a target, with rate limits and retries.

**How it works.** Cloud Scheduler drops a job like 'pull Austin MLS since 10:42' into that MLS's queue every few minutes. The queue dispatches it to an Ingest worker on Cloud Run at the rate we set for that queue, and retries with backoff if the worker fails.

**Why this choice.** Each MLS contract caps how often we may call it. One queue per MLS gives each feed its own rate limit and concurrency, so a slow MLS can't starve the others. Pub/Sub can't rate-limit per source, which is why Tasks sits in front of ingest and Pub/Sub sits after it.

**The numbers.** About 800 queues, one per MLS. A queue can dispatch up to 500 tasks a second, far above what any MLS allows, so the limit we set is always the contract, not the product.

**What can go wrong.** If a worker keeps failing, tasks pile up and retry; we cap attempts and alert. Pausing a feed is just pausing its queue.

### Ingest pipeline

**What it is.** Our own code: workers running on Cloud Run, one container image that holds the fifteen platform adapters.

**How it works.** A Cloud Tasks job wakes a worker. It calls the MLS API, saves the raw payload to GCS untouched, maps vendor fields to the RESO Data Dictionary using a versioned mapping file, validates and geocodes the address, resolves the listing to a property_id, and upserts AlloyDB together with an outbox row.

**Why this choice.** This is where data accuracy is won, so we build it. Keeping the raw payload means any mapping bug becomes a replay, not a re-pull from the MLS.

**The numbers.** Target: 99.9% field accuracy against the source and p95 under 5 minutes from MLS change to golden record, on top of the poll interval.

**What can go wrong.** A record that fails validation goes to quarantine with a reason, and the last good version stays live. We measure accuracy daily by sampling listings against the source.

### Property

**What it is.** One identity per physical home, the property_id. It's both a concept and the service that owns the golden record.

**How it works.** property_id is built from the county FIPS code plus the parcel number (APN). If there's no parcel, we fall back to a normalized address plus geographic proximity. Two listings that land on the same property_id merge into one record, and per-field precedence rules pick values, usually the listing agent's home MLS.

**Why this choice.** Overlapping MLSs list the same house. Without one identity you show duplicates and conflicting prices.

**The numbers.** 200M properties at about 10 KB each is roughly 2 TB of golden records.

**What can go wrong.** Low-confidence matches go to a review queue instead of merging automatically. Provenance is stored per field so we can explain every value.

### Listing

**What it is.** An offer on a property: for sale, for rent, pending or sold, with a price, a status and an MLS id.

**How it works.** A property lives for decades; listings come and go on it. Each listing change updates the golden record and emits a property.changed event.

**Why this choice.** Separating the house from the offer keeps history clean: price history, days on market and past sales all hang off one property.

**The numbers.** About 5M active listings out of 200M properties. That small ratio is what makes the hot search index small.

**What can go wrong.** Status lag is the visible failure, a home shown as active after it went pending. Freshness SLOs per feed catch it.

## Events

### property.changed

**What it is.** property.changed, the one business event. It says a fact about a property changed, carrying the property_id, the MLS ModificationTimestamp plus a sequence number, inside a CloudEvents envelope.

**How it works.** Every consumer stores the version it last applied and writes only if the incoming version is newer. A late or duplicate event simply loses.

**Why this choice.** Pub/Sub delivers at least once and can redeliver or be replayed. The version check makes every sink idempotent, which covers worker races, redelivery and replay. Ordering keys only keep publish order, and one poison message blocks its whole key.

**The numbers.** About 12 events a second on average.

**What can go wrong.** If two systems assign versions differently, you get flapping. The version always comes from the source MLS timestamp plus our sequence, never from the consumer's clock.

### Pub/Sub

**What it is.** Google's managed publish-subscribe messaging. A topic receives events; each subscription gets its own copy.

**How it works.** An outbox relay publishes property.changed to one topic. Five subscriptions read it: the search indexer, cache purge, alert matcher, AVM refresh and a BigQuery subscription that writes rows directly. Each has a dead-letter topic for messages that keep failing.

**Why this choice.** At 12 events a second, Kafka means brokers and partitions sized for scale we don't have. Pub/Sub gives fan-out, seek-to-replay and dead letters fully managed. Producers go through our CloudEvents adapter, so moving to Kafka later is one module.

**The numbers.** About 12 events a second, bursts of a few hundred. Topic retention up to 31 days lets us seek back and replay.

**What can go wrong.** Messages can arrive twice or out of order; the version check handles that. A consumer that falls behind shows up as subscription backlog, which we alert on.

## Storage

### AlloyDB

**What it is.** AlloyDB, Google's managed PostgreSQL-compatible database. It's the only place a property fact is written: the golden record.

**How it works.** Ingest upserts the record and an outbox row in one transaction. A relay reads the outbox and publishes to Pub/Sub. PostGIS tags each home with its neighborhood, school district and other polygons at write time. Read pools serve detail pages that miss the cache, and a secondary cluster in another region is ready for disaster recovery.

**Why this choice.** It's about 2 TB and 12 writes a second from one region. We need transactions for record plus outbox, and PostGIS. Spanner sells multi-region writes and five nines we don't need, and we'd lose PostGIS. It speaks the Postgres protocol, so leaving is a migration, not a rewrite.

**The numbers.** 200M times 10 KB is 2 TB. 12 writes a second average, bursts near 500. Replica lag under a second.

**What can go wrong.** Losing the primary region means promoting the secondary: minutes of write downtime, about a second of data at risk. Reads keep working from cache and CDN meanwhile.

### Lake (GCS + Iceberg)

**What it is.** Two things on Cloud Storage: a raw zone with every payload exactly as the MLS sent it, and history tables in Apache Iceberg format that BigQuery manages.

**How it works.** Ingest writes raw payloads first, partitioned by MLS and day. History lands through the BigQuery subscription into BigQuery tables for Apache Iceberg, partitioned by state and year: deeds, tax rolls, permits and listing events.

**Why this choice.** Everything downstream can be rebuilt from here. Iceberg is an open format, so BigQuery, Spark or Trino can read the same files, which follows our rule of open protocols. Time travel lets models train on what we knew at the time, which avoids leakage.

**The numbers.** Tens of terabytes compressed for 30 years of history.

**What can go wrong.** Raw data grows forever; lifecycle rules move old partitions to colder storage classes.

### BigQuery

**What it is.** Google's serverless data warehouse. It holds history and analytics and trains the valuation model. It is never on the user request path.

**How it works.** A Pub/Sub BigQuery subscription writes every change as a row with no pipeline code. Analysts query it, BigQuery GIS builds market heatmaps and features like distance to transit, and BigQuery ML trains the day-one valuation baseline.

**Why this choice.** Datastream would mirror current state minutes behind; the subscription keeps every change, which price history and model training need. For cost, steady jobs like ETL and training run on a baseline slot reservation with autoscaling, while ad hoc analyst queries go on-demand.

**The numbers.** On-demand is about $6.25 per TiB scanned. Partitioning by date and clustering by H3 cuts bytes scanned. Tables untouched for 90 days drop to long-term storage at about half price.

**What can go wrong.** One bad query that scans everything can cost real money; we set per-user quotas and require partition filters.

### Memorystore for Valkey

**What it is.** Memorystore for Valkey, Google's managed in-memory store. Valkey is the open-source, BSD-licensed fork of Redis with the same API.

**How it works.** Search checks it first with a key made from the normalized query plus map tile. It also holds listing cards, AVM values and ranking features. When a property changes, the cache-purge subscriber deletes the affected keys; pins also carry a 30 to 60 second TTL.

**Why this choice.** It's rebuildable from AlloyDB and speaks an open protocol, so we buy it: Google runs replicas and failover at a 99.99% SLA. Dragonfly is faster per node but BSL-licensed and we'd own the pager; we'd revisit if the cache became a top-three cost. Redis itself left the BSD license in 2024.

**The numbers.** About 40% of searches stop here. The hot set is 50 to 100 GB at a few hundred thousand operations a second, small for a Valkey cluster. Budget is 5 ms.

**What can go wrong.** Stale prices after a change, handled by event purges, and stampedes when a hot key expires, handled by request coalescing and stale-while-revalidate.

### Dedupe keys

**What it is.** Dedupe keys: a small, separate Valkey instance that remembers which notifications we already sent.

**How it works.** Before sending, the alert service runs SET NX on a key made of user, listing, change type and version, with a TTL of a few days. SET NX only succeeds if the key doesn't exist yet, so the first sender wins and every duplicate is dropped. The TTL makes keys expire on their own.

**Why this choice.** It answers one question, 'did we already send this?', in a millisecond. A separate database like Bigtable would be one more service to run for a job a small Valkey does at this size. It runs with eviction turned off so keys are never dropped early.

**The numbers.** About 15M matches a day; with a few days of TTL that's tens of millions of tiny keys, a few GB.

**What can go wrong.** If the instance is lost, the worst case is a duplicate push for recent changes, not a lost alert. That's the failure direction we prefer.

### Feature store

**What it is.** A small feature store: about 50 inputs per listing used by the search re-rank and the valuation model.

**How it works.** Features are computed in BigQuery and refreshed on events, then served from Valkey so the re-rank can fetch them in one batch.

**Why this choice.** Personalization and re-rank are optional. If features aren't back before the 20 ms deadline, search skips the re-rank and returns the base order.

**The numbers.** About 50 features, 20 ms re-rank budget on the top 200 results.

**What can go wrong.** Fair housing: no protected-class attributes or proxies like neighborhood demographics, legal review of the feature list, and disparate-impact tests on each model release.

## Search and geo

### OpenSearch

**What it is.** OpenSearch, the open-source search engine forked from Elasticsearch. We run it ourselves on GKE with the OpenSearch operator.

**How it works.** Two indexes. A hot index of about 5M active listings, around 20 GB, fits in memory. A warm index of all 200M properties, about 400 GB, sits on cheaper SSD nodes. Indexes are versioned behind an alias, so a rebuild is built on the side and swapped in, and rollback is one swap.

**Why this choice.** Geo filters, facets and custom ranking are the product, so this is our one stateful build. Vertex AI Search is a relevance black box and isn't geo-first. Elastic Cloud is the buy fallback with the same query model.

**The numbers.** 25k peak queries a second, designed for 40k. At about 1,500 queries a second per node, 40k needs around 27 nodes.

**What can go wrong.** Hot spots in big metros: we shard by traffic, so New York and LA get their own shards and extra replicas. Index lag is watched as event-to-searchable time, target p95 under 30 seconds.

### Search document

**What it is.** The search document: a roughly 4 KB record built only for filtering and ranking.

**How it works.** It carries price, beds, baths, status, the H3 cell ids at three resolutions, district ids and a version. Display data like descriptions and photos stays out and is fetched from the cache when the card is shown.

**Why this choice.** Small documents mean the hot index fits in memory and queries stay fast.

**The numbers.** 5M active docs times 4 KB is about 20 GB. New changes become searchable 1 to 2 seconds after the indexer receives them.

**What can go wrong.** A late, older event arriving after a newer one: the indexer uses external versioning, so the older version is rejected.

### Search

**What it is.** The search service: stateless code on Cloud Run that turns a map viewport and filters into results in under 200 ms.

**How it works.** It converts the viewport into a set of H3 cells, checks the cache, then queries one OpenSearch shard group for the top 500, optionally re-ranks the top 200 with a small model, and hydrates cards from the cache.

**Why this choice.** We buy the engine and build the index and routing, because what goes into the index and how queries are shaped is where the speed and relevance come from.

**The numbers.** 20M daily users times 20 searches is 400M a day, 4.6k a second on average. Times 2.5 for the evening peak and times 2 for spring weekends gives about 25k; we design for 40k. Budget: about 70 ms in OpenSearch out of 200.

**What can go wrong.** A slow shard drags p95. Routing a viewport to one shard group keeps p95 from being the slowest of many.

### H3 cell

**What it is.** An H3 cell: a hexagon from Uber's global grid, identified by a 64-bit id, with parent and child cells at each resolution.

**How it works.** Every listing stores its cell at resolutions 5, 7 and 9. A viewport is covered by cells: interior cells become exact-match term filters, and only listings in the boundary ring get the expensive geometry check.

**Why this choice.** Term filters are cheap and cacheable; geometry on every document for every query is not. One grid serves search, map clustering and alerts.

**The numbers.** Resolution 5 is about 250 km², resolution 7 about 5 km², resolution 9 about a tenth of a km², a few city blocks.

**What can go wrong.** Cover resolution must follow zoom, or a viewport turns into thousands of cells. We cap covers at a few hundred.

### Map pins

**What it is.** Map pins: what the user actually sees, 1,000 or more pins on a map in under 300 ms.

**How it works.** Requests snap to map tiles so neighbors share cache entries. Zoomed out, the server returns about 200 clusters instead of tens of thousands of pins. Pins are a compact binary payload rendered on the GPU, and card details load on hover.

**Why this choice.** It's a payload problem more than a query problem; sending less is what makes it fast.

**The numbers.** About 16 bytes per pin, so 1,500 pins is roughly 24 KB. A cached tile returns in about 40 ms.

**What can go wrong.** Drawn polygons with too many points or huge result sets; we cap at about 2,000 results and switch to clusters or a list.

## Alerts

### Saved-search alerts

**What it is.** The saved-search alert service: tells a buyer within a minute when a home matching their saved search appears or changes price.

**How it works.** Instead of re-running saved searches, we index the searches themselves by H3 cell. Each property.changed event looks up its cell, finds the candidate searches, applies their filters, dedupes, and sends one push.

**Why this choice.** Re-running 30M searches every 10 minutes would be 50k queries a second, more than all user traffic, and still 10 minutes late. Reverse search costs one lookup per change. The OpenSearch percolator is a valid first version; a custom in-memory index gives predictable latency.

**The numbers.** 30M saved searches, about 20 GB in memory. About 15M matches a day. p95 under 60 seconds from ingest to phone.

**What can go wrong.** A node dies: Pub/Sub redelivers its messages to other nodes and a fresh node reloads its cells from AlloyDB in minutes. A nightly re-run of the last 24 hours is the safety net.

### Saved search

**What it is.** A saved search: 'tell me when something like this appears'. Stored as about 40 cells plus compiled filters.

**How it works.** When saved, the search's area is converted to H3 cells and added to posting lists keyed by cell. It uses the same query language as live search, so alerts and search always agree.

**Why this choice.** Search and alerts disagreeing is the fastest way to lose trust; one DSL avoids it.

**The numbers.** 30M saved searches, about 40 cells each.

**What can go wrong.** Huge areas like all of Manhattan create many candidates per change, about 200k, still around 10 ms to filter.

### Notification

**What it is.** The delivery side: push, email and in-app, sent once and at a sensible time.

**How it works.** Matches are deduped with the dedupe keys, merged across a user's searches, held during quiet hours by time zone, and capped per day with overflow to a digest.

**Why this choice.** Spam kills engagement and carries legal risk under TCPA and CAN-SPAM.

**The numbers.** p95 under 60 seconds from ingest to device for instant alerts.

**What can go wrong.** A feed storm can flood users; the storm guard holds a feed's alerts if its change rate jumps five times.

## Edge and apps

### Web, iOS, Android

**What it is.** The apps: web, iOS and Android.

**How it works.** They send tile-snapped search requests, render pins on the GPU, and load listing pages that are server-side rendered.

**Why this choice.** Listing pages drive organic search traffic, so they must be crawlable and fast on first paint.

**The numbers.** 100M monthly users, about 20M daily, 35M on a spring Sunday.

**What can go wrong.** Old app versions hitting changed APIs; the gateway versions APIs and keeps old ones alive.

### CDN + WAF

**What it is.** Cloud CDN and Cloud Armor on a global external load balancer: one anycast IP worldwide.

**How it works.** The CDN serves photos, map tiles and anonymous pages from the edge, and serves stale content while refreshing if the origin hiccups. Armor blocks scrapers and applies WAF rules before traffic reaches us.

**Why this choice.** Most bytes are photos; serving them from the edge is the biggest cost and latency win.

**The numbers.** About 170 Gbps of photo egress at peak, above 95% cache hit rate for photos.

**What can go wrong.** A cache-busting change or a purge storm sends traffic to origin; we purge by key, never globally.

### Media pipeline

**What it is.** The media pipeline: photos, tours and video at the right size for each device.

**How it works.** An upload lands in Cloud Storage, Eventarc fires, a Cloud Run job makes every size and format (AVIF, WebP) once, and the CDN serves them. Identical photos are stored once by content hash.

**Why this choice.** Resize once at write time, never per view. Originals are only read again to make a new size, so they move to cold storage.

**The numbers.** 7.5 PB of originals, about 1.5 PB of sizes kept hot.

**What can go wrong.** Format support differs by device; we keep JPEG as the fallback.

### API gateway / BFF

**What it is.** The API gateway, or backend-for-frontend: the one front door for all requests.

**How it works.** It authenticates, rate-limits, sets feature flags, server-renders pages and assigns a priority class to each request.

**Why this choice.** Load shedding needs one place to decide what to drop first.

**The numbers.** About 10 ms of the 200 ms budget.

**What can go wrong.** Overload: it sheds low-priority work first based on CPU, queue depth and p95, with a manual override.

### Degradation ladder

**What it is.** The degradation ladder: what we turn off, in order, when traffic exceeds capacity.

**How it works.** Longer cache TTLs first, then skip the re-rank and personalization, then serve only precomputed values, then pause background jobs. Search, listing pages, contact-agent and mortgage are never shed.

**Why this choice.** Bend, don't break. A rate cut or a viral story can bring 4x traffic faster than autoscaling reacts.

**The numbers.** Scheduled capacity floors cover the known spring peak; the ladder covers surprises.

**What can go wrong.** Leaving a degraded mode on after the spike; every flag has an owner and an alarm.

## Product services

### Valuation (AVM)

**What it is.** The automated valuation model: an estimated value for all 200M homes.

**How it works.** We train gradient-boosted trees (XGBoost) on BigQuery data, packaged in a container that runs as a Cloud Run job or on GKE. Each night it re-scores only homes touched by a change, on Spot VMs, and writes values to AlloyDB and Valkey. BigQuery ML's boosted-tree regressor is the day-one baseline.

**Why this choice.** Valuation is a differentiator, so we build it. A container is portable; Vertex AI endpoints would be always-on serving for a number that changes nightly.

**The numbers.** About 55 CPU-hours a night for a full re-score; a live re-estimate when an owner edits facts runs in under a second. Confidence ranges come from quantile regression.

**What can go wrong.** Training leakage: Iceberg time travel lets us train on what was known at the time. Fair housing rules apply to features here too.

### Agent marketplace

**What it is.** The agent marketplace: connecting buyers with agents. This is the revenue event.

**How it works.** A contact-agent request is written transactionally and routed to the agent's CRM.

**Why this choice.** Search can be seconds stale; a lead can never be lost. So leads are strongly consistent and never shed.

**The numbers.** Small volume compared with search, but every one is revenue.

**What can go wrong.** Losing a lead during an incident; writes are durable before we acknowledge them.

### Mortgage

**What it is.** Mortgage pre-approval and rate comparison, built with lending partners.

**How it works.** It runs in its own GCP project behind VPC Service Controls, with Cloud KMS encryption and every access logged. We store consent and every disclosure shown, versioned.

**Why this choice.** We aren't the lender; partners carry the licensing and most of the TILA-RESPA liability. Isolation keeps the blast radius and audit boundary small.

**The numbers.** One region with warm DR.

**What can go wrong.** Showing a rate that can't be reproduced; quotes are stored so they can be.

## Build vs buy

### Build vs buy

**What it is.** The build versus buy rule: managed where the protocol is open, proprietary only behind an adapter.

**How it works.** We buy what is stateful, painful to run and speaks an open protocol: AlloyDB, Memorystore for Valkey, the CDN. Proprietary services like Pub/Sub, Cloud Tasks and BigQuery stay off the user request path or behind our adapter. We build what differentiates: normalization, ranking on OpenSearch and the valuation model. Mortgage is a partnership.

**Why this choice.** Relevance and data are the product; engines and plumbing are commodities.

**The numbers.** Switch triggers are explicit: Dragonfly if the cache becomes a top-three cost, Elastic Cloud if running OpenSearch costs more than an engineer, Kafka above sustained 10k events a second.

**What can go wrong.** Lock-in creeping in through convenience features; every proprietary call goes through one module.

## Numbers

### ~25k search QPS

**What it is.** Peak search load: about 25,000 queries a second.

**How it works.** 20M daily users times 20 searches each is 400M searches a day. Divided by 86,400 seconds is about 4,600 a second on average. The evening peak is about 2.5 times average, around 12k, and spring weekends double that to about 25k.

**Why this choice.** Map pans and filter changes each count as a search, which is why 20 a day is realistic.

**The numbers.** Design target 40k for headroom.

**What can go wrong.** If we're two times wrong, we add replicas; nothing structural changes.

### ~170 Gbps egress

**What it is.** Peak photo traffic: about 170 gigabits a second.

**How it works.** About 9,000 listing views a second at peak, times about 15 photos loaded, times about 150 KB per photo, is roughly 20 GB a second, about 170 Gbps.

**Why this choice.** This is why the CDN and modern image formats matter so much.

**The numbers.** CDN hit rate above 95% keeps origin traffic small.

**What can go wrong.** A drop in CDN hit rate multiplies origin and egress cost quickly.

### 12 writes / s

**What it is.** Write load: about 12 writes a second.

**How it works.** 1M listing changes a day divided by 86,400 seconds is about 12 a second; bursts reach a few hundred when a large MLS publishes a batch.

**Why this choice.** Writes are tiny, so the hard part is correctness, not throughput. That's why one AlloyDB primary and Pub/Sub are enough.

**The numbers.** Reads outnumber writes about 1,000 to 1.

**What can go wrong.** Bursts after an MLS outage; the queues absorb them.

### ~20 GB hot index

**What it is.** The hot search index: about 20 GB.

**How it works.** 5M active listings times about 4 KB per search document is about 20 GB. Indexing all 200M properties would be about 400 GB.

**Why this choice.** Because it fits in memory, queries are fast, the DR standby is cheap, and a full rebuild takes under an hour.

**The numbers.** Even at 10M active listings it's 40 GB and still fits.

**What can go wrong.** If product wanted every search to cover off-market homes, this assumption breaks and the cost model changes.

### 7.5 PB of photos

**What it is.** Photo storage: about 7.5 petabytes of originals.

**How it works.** 100M homes with photos times about 25 photos times about 3 MB each is 7.5 PB.

**Why this choice.** Photos are the biggest line on the bill, so storage tiering is the first cost lever.

**The numbers.** At standard storage that's roughly $160k a month; moving originals to Nearline, Coldline and Archive brings it to roughly $30k.

**What can go wrong.** Retrieval fees from cold tiers if we read originals too often; we only read them to make a new size.

### 15M matches / day

**What it is.** Alert volume: about 15M matches a day.

**How it works.** Roughly 300k relevant changes a day, like new listings and price drops, times about 50 matching saved searches each.

**Why this choice.** It shows why polling is wrong: re-running searches would be 50k queries a second, while streaming handles about 12 changes a second.

**The numbers.** Matches are highly skewed toward popular areas.

**What can go wrong.** A storm of changes from one feed; the storm guard holds it.
