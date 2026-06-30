# LanceDB Vector Store

HydraMem stores chunk embeddings in LanceDB, an embedded serverless vector
database. LanceDB provides fast approximate nearest-neighbour search over the
384-dimensional vectors produced by the embedder. The vector index is queried
during retrieval to find semantically similar chunks. When LanceDB is
unavailable an in-memory fallback is used instead.
