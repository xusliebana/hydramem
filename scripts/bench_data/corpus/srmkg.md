# SR-MKG Topological Scorer

SR-MKG is the first verification layer. It scores a candidate relation purely
from graph topology with no LLM call, combining base confidence, the Jaccard
common-neighbour coefficient, a named-relation-type boost, and an isolation
penalty. Scores above the accept threshold are kept, scores below the reject
threshold are dropped, and borderline scores are forwarded to VoG.
