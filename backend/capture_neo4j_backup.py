"""Export all Neo4j nodes and relationships to backup/pre-refactor/neo4j-backup.json.
Run once before any Phase 3D graph schema changes.
"""
import json
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

url      = os.getenv("NEO4J_URL", "neo4j://127.0.0.1:7687")
user     = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "")

driver = GraphDatabase.driver(url, auth=(user, password))

with driver.session() as session:
    # Export all nodes
    nodes = []
    result = session.run("MATCH (n) RETURN labels(n) AS labels, properties(n) AS props")
    for record in result:
        nodes.append({"labels": record["labels"], "properties": record["props"]})

    # Export all relationships
    rels = []
    result = session.run(
        "MATCH (a)-[r]->(b) "
        "RETURN labels(a) AS from_labels, properties(a) AS from_props, "
        "type(r) AS rel_type, properties(r) AS rel_props, "
        "labels(b) AS to_labels, properties(b) AS to_props"
    )
    for record in result:
        rels.append({
            "from_labels":  record["from_labels"],
            "from_props":   record["from_props"],
            "rel_type":     record["rel_type"],
            "rel_props":    record["rel_props"],
            "to_labels":    record["to_labels"],
            "to_props":     record["to_props"],
        })

driver.close()

os.makedirs("./backup/pre-refactor", exist_ok=True)
output_path = "./backup/pre-refactor/neo4j-backup.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump({"nodes": nodes, "relationships": rels}, f, indent=2, default=str)

print(f"Saved to {output_path}")
print(f"  Nodes exported:         {len(nodes)}")
print(f"  Relationships exported: {len(rels)}")
print()
# Summary by label
from collections import Counter
label_counts = Counter(tuple(sorted(n["labels"])) for n in nodes)
for labels, count in sorted(label_counts.items()):
    print(f"  {'/'.join(labels):<30} {count} node(s)")
