# Grafeo Graph Backend

Grafeo is the default graph backend on Python 3.12: a high-performance embedded
graph database with a Rust core exposed through PyO3. It ships as a single small
wheel, supports native Cypher queries and ACID transactions, and stores the
entity-relation graph on disk. On Python 3.11 HydraMem falls back to a
pure-Python NetworkX backend.
