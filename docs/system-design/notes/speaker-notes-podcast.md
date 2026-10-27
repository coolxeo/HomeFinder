# HomeFinder: the podcast

A two-voice script for learning the design before the interview. About 30 minutes read aloud. **Maya** is the host and plays the interviewer's curiosity. **Sam** is the architect and explains it the way Dani will present it.

The listener already knows GCP well (Pub/Sub, Cloud Tasks, BigQuery slots), so the script skips product basics and spends its time on reasoning, numbers and phrasing. All numbers are our assumptions unless they're called out as a GCP limit or price.

---

## Episode 1: The shape of the problem

**MAYA:** So, HomeFinder. A national real estate platform. Give me the one-sentence version.

**SAM:** A hundred million people a month search two hundred million US properties on a map, and the data comes from more than eight hundred MLSs that each speak a slightly different dialect. That last part is the real problem.

**MAYA:** Why is that the real problem, and not the hundred million users?

**SAM:** Because reads are easy to scale. You add replicas and cache. What's hard is that the data is messy, it changes all the time, and if a house shows as active when it went pending yesterday, users stop trusting you. So the design is really two systems: a careful, correct write path, and a fast, cheap read path.

**MAYA:** Let's get the numbers in. How much search traffic?

**SAM:** I start from daily users. A hundred million monthly users, and I assume twenty percent come on a given day, so twenty million. Each does about twenty searches, because every map pan and filter change is a query. That's four hundred million searches a day.

**MAYA:** And per second?

**SAM:** Divide by 86,400 and you get about 4,600 a second on average. The evening peak is about two and a half times that, so around 12,000. Spring weekends are the real peak for housing, roughly double again, so about 25,000 a second. I design for 40,000 to leave headroom.

**MAYA:** And writes?

**SAM:** Tiny. About a million listing changes a day across all the MLSs. A million divided by 86,400 is about twelve a second. Bursts of a few hundred when a big MLS publishes a batch.

**MAYA:** Twelve a second. That number is going to come back.

**SAM:** It drives half the decisions. Say it like this in the interview: "Reads outnumber writes about a thousand to one. So I scale reads out and keep writes simple and correct."

**MAYA:** One more number before we move on. The size of the search index.

**SAM:** This is the single biggest win in the design. Of two hundred million properties, only about five million are actively listed at any time. Ninety-five percent of searches are over those. A search document is about four kilobytes, so five million times four KB is about twenty gigabytes. That fits in memory. If you indexed all two hundred million for every search, it would be four hundred gigabytes.

**MAYA:** So the trick is noticing that the searchable set is small.

**SAM:** Exactly. "The searchable set is small" is a sentence worth saying out loud.

---

## Episode 2: The rule

**MAYA:** You're on GCP. But you said "GCP-native, kept light." What does light mean?

**SAM:** One rule: managed where the protocol is open, proprietary only behind an adapter.

**MAYA:** Unpack that.

**SAM:** If a managed service speaks an open protocol, I buy it happily, because leaving is a migration, not a rewrite. AlloyDB speaks Postgres. Memorystore for Valkey speaks the Redis protocol. Cloud Run runs plain containers. The data lake is Apache Iceberg files on Cloud Storage. Any of those can move.

**MAYA:** And the proprietary ones?

**SAM:** Pub/Sub, Cloud Tasks and BigQuery are proprietary APIs. They're great, so I use them, but they stay off the user request path or behind one adapter. Producers publish through a small CloudEvents adapter, so if we ever moved to Kafka it's one module, not every service.

**MAYA:** And what do you build?

**SAM:** What differentiates us: the MLS normalization, search ranking on OpenSearch, and the valuation model. The short version is "buy the plumbing, build the product."

---

## Episode 3: MLS integration, the write path

**MAYA:** Walk me through a price change. An agent in Austin drops a price. What happens?

**SAM:** Five steps: pull, land, normalize, resolve, publish. Let's start with pull.

**MAYA:** Why pull? Doesn't the MLS push?

**SAM:** Almost never. We poll. And each MLS contract caps how often we may call it. That's where Cloud Tasks comes in. Every MLS gets its own queue. Cloud Scheduler drops a job into it, like "pull Austin since 10:42", every one to fifteen minutes. The queue's dispatch rate is set to that MLS's contract.

**MAYA:** Why a queue per MLS and not one big poller?

**SAM:** Isolation. One slow or broken MLS can't starve the other eight hundred. And retries with backoff come for free. A queue can go up to 500 dispatches a second, which is a GCP limit far above anything an MLS allows, so the contract is always the real cap.

**MAYA:** Why not Pub/Sub here?

**SAM:** Pub/Sub can't rate-limit per source. That's the clean way to say it: "Cloud Tasks throttles, Pub/Sub fans out." Tasks sits in front of ingest; Pub/Sub sits after it.

**MAYA:** OK. The queue triggers a worker.

**SAM:** An ingest worker on Cloud Run. It's our code: one container with about fifteen adapters, because most of the eight hundred MLSs run on a handful of vendor platforms that speak the RESO Web API or the older RETS. Each MLS is just config: credentials, cadence, field mappings, display rules. A new MLS is a config change, not a deploy.

**MAYA:** The worker pulls the changes. Then what?

**SAM:** Land. It writes the raw payload to Cloud Storage exactly as received. That sounds boring, but it's the most important habit in the pipeline. If we find a mapping bug next week, we fix the mapping and replay the raw files. We never have to re-pull from the MLS.

**MAYA:** Normalize.

**SAM:** A versioned mapping per MLS turns vendor fields into the RESO Data Dictionary, the industry standard schema. Then validation: standardize the address, geocode it, sanity rules. Anything that fails goes to quarantine with a reason, and the last good version stays live. A bad record never replaces a good one.

**MAYA:** Resolve. This is the dedupe part?

**SAM:** Yes. The same house can be listed in two overlapping MLSs. We resolve every listing to a property_id built from the county FIPS code plus the parcel number. If there's no parcel, a normalized address plus distance. Two listings on one property_id merge into one golden record, and precedence rules pick each field, usually the listing agent's home MLS wins. We store provenance per field.

**MAYA:** And then it writes.

**SAM:** One transaction in AlloyDB: upsert the golden record and insert an outbox row. A small relay reads the outbox and publishes to Pub/Sub. That's the transactional outbox pattern, and it kills the dual-write bug. Either the record and the event both happen, or neither does.

**MAYA:** How do you hit 99.9 percent accuracy?

**SAM:** Four layers. Validation with quarantine. Entity resolution so duplicates merge. A nightly full-key reconciliation per feed, because many feeds never tell you about deletes. And per-feed freshness SLOs that alert when a feed goes quiet. We measure accuracy by sampling listings against the source every day.

---

## Episode 4: Events and ordering

**MAYA:** The change is in AlloyDB, the outbox publishes. Why Pub/Sub and not Kafka? Interviewers love that question.

**SAM:** Twelve events a second. That's the whole answer, then the detail: Kafka means brokers and partitions sized for scale we don't have. Pub/Sub gives managed fan-out, seek to replay, dead-letter topics and a direct BigQuery subscription. I'd switch at sustained ten thousand events a second, or if we needed log compaction. And the adapter keeps that exit cheap.

**MAYA:** Who consumes the event?

**SAM:** One topic, property.changed, with five subscriptions. The search indexer, cache purge, the alert matcher, the valuation refresh, and a BigQuery subscription that writes rows with no code.

**MAYA:** Ordering. Pub/Sub has ordering keys. Do you use them?

**SAM:** Optionally, but they're not the guarantee. Ordering keys keep publish order. They don't protect you from two workers racing, from redelivery, or from replay. And one poison message blocks its whole key. The real guarantee is a version check: the event carries the MLS ModificationTimestamp plus a sequence number, and every sink writes only if that version is newer than what it holds. A late or duplicate event simply loses.

**MAYA:** So delivery is at-least-once, and the sinks make it effectively-once.

**SAM:** Exactly that sentence.

---

## Episode 5: Storage

**MAYA:** Why AlloyDB and not Spanner? You're on GCP, Spanner is right there.

**SAM:** It's about two terabytes and twelve writes a second from one region. Two hundred million properties times ten kilobytes. Spanner sells multi-region writes and five nines that we don't need, and we'd lose PostGIS. AlloyDB gives us Postgres transactions for the outbox, PostGIS for geometry, read pools for detail pages, and a cross-region secondary for disaster recovery.

**MAYA:** Why one write region?

**SAM:** Writes are tiny and multi-writer means conflict resolution for a problem we don't have. A West Coast user saving a search pays sixty or seventy milliseconds extra. Nobody notices.

**MAYA:** And history?

**SAM:** The Pub/Sub BigQuery subscription lands every change as a row. Long history sits in BigQuery tables for Apache Iceberg on Cloud Storage: deeds, tax rolls, permits, listing events, partitioned by state and year. Open format, so Spark or Trino can read the same files. And time travel lets the valuation model train on what we knew at the time, which prevents leakage.

**MAYA:** Why not Datastream into BigQuery?

**SAM:** Datastream mirrors current state, minutes behind. We want every change for price history and training. I'd add it only if analysts wanted a live snapshot table.

**MAYA:** Cache.

**SAM:** Memorystore for Valkey. It holds the query cache keyed by normalized query plus map tile, listing cards, valuation numbers and ranking features. About forty percent of searches stop there. When a property changes, the cache-purge subscriber deletes its keys.

**MAYA:** This is your build versus buy story, isn't it?

**SAM:** It's the best one. Three options. Valkey, managed: BSD license, Google runs failover at a 99.99 percent SLA. Dragonfly, self-hosted on GKE: multi-threaded, so one big node replaces a sharded cluster, genuinely faster per node. But it's BSL licensed, and failover, upgrades and the pager become ours. At our hot set, fifty to a hundred gigabytes at a few hundred thousand operations a second, that saves a few nodes, not a fleet. Redis itself left the BSD license in 2024.

**MAYA:** So when would you build it?

**SAM:** Explicit trigger: when the cache becomes a top-three cost, or a hot key outgrows one shard. And the cache is the safest thing to self-host later, because it rebuilds from AlloyDB.

**MAYA:** There's a tiny store for alert dedupe too.

**SAM:** A small separate Valkey with eviction off. SET NX with a TTL: the first sender wins, duplicates are dropped, keys expire on their own. No extra database like Bigtable for a job that small.

---

## Episode 6: Geospatial search, the deep dive

**MAYA:** This is your fifteen minutes. Set it up.

**SAM:** A user draws a map viewport with filters. We have 200 milliseconds at p95, at 25,000 queries a second. The naive way is running polygon math on every document for every query. That's slow and you can't cache it.

**MAYA:** So what do you do instead?

**SAM:** Two ideas. Precompute geometry at write time, and use a grid at read time.

**MAYA:** Start with write time.

**SAM:** When a listing changes, PostGIS tags it once with its neighborhood, school district, ZIP and city. The search document stores those ids. So "homes in this school district" becomes an exact-match term filter, not a polygon query. We compute geometry about a million times a day on writes instead of four hundred million times a day on reads.

**MAYA:** "One million writes versus four hundred million reads."

**SAM:** That's the line.

**MAYA:** And the grid?

**SAM:** H3, Uber's hexagon grid. Each listing stores its cell at three resolutions: 5, 7 and 9. Resolution 7 is about five square kilometers, resolution 9 is a few city blocks. When a viewport comes in, we cover it with cells. Interior cells become term filters, which Lucene caches beautifully. Only listings in the boundary ring get the exact geometry check.

**MAYA:** Why hexagons and not geohash?

**SAM:** Hexagons have six equidistant neighbors and no corner ambiguity. Geohash cells are distorted and have edge effects. S2 would also be fine. Using one grid everywhere, for search, map clustering and alerts, matters more than which grid.

**MAYA:** Walk the 200 millisecond budget.

**SAM:** About ten at the gateway. Check the cache, five milliseconds, and forty percent of requests stop there. Otherwise query OpenSearch, about seventy milliseconds, routed to one shard group by metro, for the top 500. An optional twenty-millisecond re-rank on the top 200 with a deadline: if it's late, we skip it. Hydrate the cards from the cache. That totals around 160, leaving forty of headroom.

**MAYA:** How do you get a thousand pins on a map that fast?

**SAM:** Send less. About sixteen bytes per pin, so fifteen hundred pins is twenty-four kilobytes. Requests snap to tiles so neighbors share cache entries. Zoomed out, we return a couple of hundred clusters, not forty thousand pins.

**MAYA:** Why OpenSearch on GKE? You said you buy managed things.

**SAM:** Geo and ranking are the product, so this is our one stateful build. Vertex AI Search is a relevance black box and isn't geo-first. We need geo_shape, facets and our own ranking. Elastic Cloud is the escape hatch with the same query model, if running the cluster costs more than an engineer's time.

**MAYA:** Index layout.

**SAM:** A hot index of five million active listings, twenty gigabytes, in memory. A warm index of all two hundred million properties, four hundred gigabytes, on cheaper SSD nodes. Shard by traffic, not by area: New York and LA get their own shards and extra replicas. At about fifteen hundred queries a second per node, forty thousand needs about twenty-seven nodes.

**MAYA:** Reindexing without downtime?

**SAM:** Build a new index from AlloyDB on the side, under an hour for five million docs. Seek a fresh Pub/Sub subscription back to the start time so nothing is missed. Mirror some traffic to compare, then swap the alias. Rollback is swapping it back.

**MAYA:** Where does BigQuery GIS fit?

**SAM:** Analytics only. Heatmaps and features like distance to transit. It answers in seconds, not milliseconds, so it never touches the request path.

---

## Episode 7: Alerts, in two minutes

**MAYA:** Saved-search alerts. Thirty million saved searches. Why not just re-run them?

**SAM:** Thirty million every ten minutes is fifty thousand queries a second. More than all user traffic, and still ten minutes late. So we flip it: index the queries, stream the listings. Each saved search is stored as about forty H3 cells. When a property changes, we look up its cell, find candidate searches, apply their filters, dedupe, push. About twelve changes a second instead of fifty thousand queries.

**MAYA:** What if the matcher node dies?

**SAM:** Pub/Sub redelivers its unacknowledged messages. Saved searches live in AlloyDB, so a fresh node reloads its cells in minutes and seeks back a few minutes. A nightly re-run of the last twenty-four hours is the safety net, and dedupe stops double sends.

---

## Episode 8: Cost optimization, your scaling section

**MAYA:** You chose cost as your scaling topic. Why?

**SAM:** Because it's where the build versus buy story lives, and because the bill has a surprising shape. Here's an illustrative split that adds up to a hundred percent. Photo storage thirty. Image egress and CDN twenty-five. Search compute fifteen. AlloyDB nine. BigQuery six. Batch and ML five. Cache four. Cloud Run APIs three. Pub/Sub and everything else three.

**MAYA:** So more than half the bill is photos.

**SAM:** Right. Structured data is almost a rounding error. So you start where the money is.

**MAYA:** Photos first.

**SAM:** Seven and a half petabytes of originals: a hundred million homes, twenty-five photos, three megabytes each. Resize once on upload, so originals are only read again to make a new size. Then GCS lifecycle rules: Standard, then Nearline at thirty days, Coldline at ninety, Archive once the home sells. At list prices that's roughly a hundred and sixty thousand dollars a month down to about thirty.

**MAYA:** Egress.

**SAM:** Cloud CDN above ninety-five percent hit rate, and AVIF or WebP at the right size per device. That cuts bytes on the wire by a third or more.

**MAYA:** Now BigQuery. You know slots well.

**SAM:** Both models, for different shapes of work. ETL and model training run every night and are predictable, so they go on an editions baseline reservation with autoscaling on top. Analysts' ad hoc queries go on-demand, around six dollars twenty-five per TiB scanned. Then the usual hygiene: partition by date, cluster by H3, require partition filters, and tables untouched for ninety days drop to long-term storage at about half price.

**MAYA:** Compute.

**SAM:** Pay for the shape of the load. Cloud Run scales stateless APIs to zero overnight. Nightly valuation scoring and reindexing can be interrupted, so they run on Spot VMs, up to about ninety-one percent off. The steady base, AlloyDB and the core GKE nodes, gets committed use discounts. And the cache is a cost lever too: forty percent hits means forty percent less search compute.

**MAYA:** And spring?

**SAM:** Scheduled capacity floors for the known spring weekend peak, because autoscaling reacts in minutes and new search nodes start cold. Autoscaling handles anything above the floor, and a degradation ladder handles surprises: longer cache TTLs, skip the re-rank, precomputed values only, pause batch jobs. Search, listing pages, contact-agent and mortgage are never shed.

---

## Episode 9: Reliability in one breath

**MAYA:** 99.95 percent. How?

**SAM:** One serving region across three zones, so a zone failure is invisible. The global load balancer and CDN keep cached pages and photos up during an incident. A region loss means promoting the AlloyDB secondary and the warm OpenSearch standby, which is cheap because the hot index is twenty gigabytes. RTO is tens of minutes, RPO about a second of replication lag. 99.95 percent is about twenty-two minutes of downtime a month.

---

## Episode 10: Recap, the one-liners

**MAYA:** Let's do rapid fire. I say the topic, you give me the line.

**SAM:** Go.

**MAYA:** Events.

**SAM:** Pub/Sub, because twelve events a second doesn't need Kafka.

**MAYA:** MLS rate limits.

**SAM:** A Cloud Tasks queue per MLS, capped to its contract.

**MAYA:** Ordering.

**SAM:** A version check at every sink; ordering keys only keep publish order.

**MAYA:** Database.

**SAM:** AlloyDB: two terabytes at twelve writes a second, with PostGIS.

**MAYA:** History.

**SAM:** A Pub/Sub BigQuery subscription into Iceberg tables.

**MAYA:** Cache.

**SAM:** Memorystore for Valkey; Dragonfly when the cache is a top-three cost.

**MAYA:** Search.

**SAM:** OpenSearch on GKE, our one stateful build; Elastic Cloud is the fallback.

**MAYA:** Geo.

**SAM:** Geometry at write time, H3 at read time. A million writes versus four hundred million reads.

**MAYA:** Valuation.

**SAM:** XGBoost in a container, BigQuery ML as the baseline, nightly on Spot.

**MAYA:** Cost.

**SAM:** Photos are half the bill, so tier them first.

**MAYA:** And the rule.

**SAM:** Managed where the protocol is open, proprietary only behind an adapter.

---

## Bonus: curveballs to rehearse

**MAYA:** Last segment. Questions that might throw you.

**MAYA:** "What if your assumptions are badly wrong?"

**SAM:** Only one really matters: the size of the searchable set. If users mostly searched all two hundred million properties, the hot index is four hundred gigabytes and the cheap standby stops being cheap. Everything else scales by adding nodes.

**MAYA:** "What would you do with half the team?"

**SAM:** Fewer services, the OpenSearch percolator instead of a custom matcher, Elastic Cloud instead of running OpenSearch, BigQuery ML instead of the XGBoost container, a vendor valuation at launch.

**MAYA:** "What's the biggest risk?"

**SAM:** Underestimating how messy MLS data is. That's why the first ninety days pilot three MLSs end to end and measure accuracy against the source.

**MAYA:** "How do you stay compliant with fair housing?"

**SAM:** No protected-class attributes or obvious proxies in ranking or recommendations, legal review of the feature list, disparate-impact tests on every model release, and sponsored results labeled.

**MAYA:** And if you don't know a number?

**SAM:** Say how you'd get it. "I'd load-test that before committing." And if they add a constraint you didn't have, say what changes. Changing your mind with a reason scores better than defending a slide.

**MAYA:** Good luck tomorrow.

**SAM:** Thanks. Twelve events a second. I won't forget.
