# ruff: noqa: E501
"""Builds ../wiki_eval.json: 30 questions over the 30 Wikipedia articles fetched by fetch_wiki.py.
Each question's answer sits in one sentence; the marker is a verbatim phrase from that sentence.
Run after fetch_wiki.py: python build_wiki_eval.py"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
QUESTIONS = [
("Who conceived the Python language, and at which research institute in the Netherlands?","python_programming_language","Guido van Rossum at Centrum"),
("Which online chat between two developers in 1993 is credited with the origin of Ruby?","ruby_programming_language","Keiju Ishitsuka"),
("Which company officially sponsored Rust starting in 2009?","rust_programming_language","officially sponsored"),
("Which three people designed Go at Google in 2007?","go_programming_language","Griesemer"),
("Which company covers the language development costs of Kotlin?","kotlin_programming_language","bears language development"),
("Who created Swift in 2010 for Apple?","swift_programming_language","created by Chris Lattner in 2010"),
("Which river flows through the Danube Delta in Romania into the Black Sea?","danube","Danube Delta in Romania"),
("What is the total length of the Elbe?","elbe","total length is 1,094"),
("Into which lagoon does the Oder flow near Szczecin?","oder","Szczecin Lagoon"),
("Into which sea does the Rhine finally empty?","rhine","North Sea"),
("In which year did Marie Curie share the Nobel Prize in Physics with her husband Pierre?","marie_curie","1903 Nobel Prize in Physics"),
("Which Austrian and Swedish nuclear physicist was instrumental in the discovery of nuclear fission?","lise_meitner","nuclear fission"),
("Which X-ray diffraction photograph by Rosalind Franklin was key to the structure of DNA?","rosalind_franklin","Photo 51"),
("Which theorem linking symmetries and conservation laws is named after Emmy Noether?","emmy_noether","Noether's theorem"),
("Whose proposed mechanical general-purpose computer is Ada Lovelace chiefly known for work on?","ada_lovelace","Charles Babbage's proposed mechanical"),
("What are the two ways solar power converts sunlight into electricity?","solar_power","photovoltaic"),
("How is wind power generated almost completely today?","wind_power","generated almost completely using wind turbines"),
("Which dam surpassed Itaipu in 2008 as the largest hydroelectric producer?","hydroelectricity","Three Gorges"),
("In which city was a geothermal well used to heat greenhouses in 1926?","geothermal_energy","greenhouses in Boise in 1926"),
("Which two accidents, in 1979 and 1986, increased regulation of and opposition to nuclear power plants?","nuclear_power","Chernobyl"),
("Which annual event is described as the world's largest Volksfest in Munich?","munich","Oktoberfest"),
("Which port is Germany's largest and Europe's third-largest after Rotterdam and Antwerp?","hamburg","port"),
("Which two automobile museums reflect Stuttgart's status as Germany's car capital?","stuttgart","Mercedes-Benz Museum"),
("Which cathedral was the world's tallest building from 1880 to 1890?","cologne","Cologne Cathedral (Kölner Dom) was"),
("Which mechanism are transformer architectures based on?","transformer_deep_learning","multi-head attention mechanism"),
("Why are vanishing and exploding gradients prevented in convolutional neural networks?","convolutional_neural_network","regularization that comes from using shared weights"),
("Which architecture, developed in 1997, became the standard RNN variant for long-term dependencies?","recurrent_neural_network","long short-term memory"),
("Who developed gradient boosting in 1999 and 2001, alongside Llew Mason's functional perspective?","gradient_boosting","Friedman"),
("Whose idea of searching over a random subset of decisions when splitting a node influenced Breiman's random forests?","random_forest","Amit and Geman"),
("What lets support vector machines perform non-linear classification?","support_vector_machine","kernel"),
]

queries = []
for i, (query, slug, kw) in enumerate(QUESTIONS, 1):
    flat = re.sub(r"\s+", " ", (HERE / f"{slug}.md").read_text(encoding="utf-8"))
    m = re.search(re.escape(kw), flat, re.I)
    assert m, (slug, kw)
    start = flat.rfind(". ", 0, m.start()) + 2
    end = flat.find(". ", m.end())
    sentence = flat[max(start, 0): end + 1 if end > 0 else None].strip()
    queries.append({
        "id": f"w{i:02d}", "query": query, "category": "cluster_discrimination",
        "relevant_chunks": [{"document_id": slug, "content_marker": flat[m.start(): m.start() + 55].split(" ##")[0]}],
        "reference_answer": sentence, "answerable": True,
    })
dataset = {
    "description": "30 questions over 30 Wikipedia articles (CC BY-SA 4.0) grouped into confusable "
                   "clusters; see fetch_wiki.py. A harder, larger-corpus counterpart to knowledge_base_eval.json.",
    "documents": [{"id": p.stem, "path": f"wiki/{p.name}", "file_type": "md"}
                  for p in sorted(HERE.glob("*.md"))],
    "queries": queries,
}
(HERE.parent / "wiki_eval.json").write_text(json.dumps(dataset, indent=1, ensure_ascii=False))
print(len(queries), "queries,", len(dataset["documents"]), "documents")
