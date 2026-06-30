# Night Gardener

The Night Gardener is HydraMem's autonomous offline learning engine. It runs
nightly to infer new relations from stored sessions, verify them, and prune
spurious edges from the knowledge graph. Pruning removes isolated entities and
low-confidence relations. The honesty contract guarantees the Night Gardener
emits zero relations when there is no real evidence.
