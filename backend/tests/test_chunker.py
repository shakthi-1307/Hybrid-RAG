from __future__ import annotations

from app.ingestion.chunker import StructuralChunker
from app.schemas.ingestion import Section

TARGET = 10
OVERLAP = 3
MINIMUM = 2


def make_chunker(counter) -> StructuralChunker:
    return StructuralChunker(
        target_tokens=TARGET,
        overlap_tokens=OVERLAP,
        min_tokens=MINIMUM,
        counter=counter,
    )


def test_chunks_never_cross_section_boundaries(counter):
    sections = [
        Section(order=0, heading_path=["A"], text="alpha beta gamma."),
        Section(order=1, heading_path=["B"], text="delta epsilon zeta."),
    ]

    chunks = make_chunker(counter).chunk(sections)

    assert [chunk.heading_path for chunk in chunks] == [["A"], ["B"]]
    assert all("delta" not in c.text for c in chunks if c.heading_path == ["A"])


def test_packing_respects_target_and_carries_overlap(counter):
    sentences = " ".join(f"word{i} filler filler." for i in range(6))
    section = Section(order=0, heading_path=["H"], text=sentences)

    chunks = make_chunker(counter).chunk([section])

    assert len(chunks) > 1
    assert all(chunk.token_count <= TARGET + OVERLAP for chunk in chunks)
    # The overlap tail of chunk N is the opening of chunk N+1.
    assert chunks[1].text.startswith("word2")


def test_oversized_sentence_is_hard_split(counter):
    long_sentence = " ".join(f"w{i}" for i in range(35)) + "."
    section = Section(order=0, heading_path=[], text=long_sentence)

    chunks = make_chunker(counter).chunk([section])

    assert len(chunks) > 1
    assert all(chunk.token_count <= TARGET + OVERLAP for chunk in chunks)


def test_undersized_tail_is_merged_into_previous_chunk(counter):
    section = Section(
        order=0,
        heading_path=[],
        text=" ".join(f"t{i} a b c d e f g h i." for i in range(3)) + " tiny.",
    )

    chunks = make_chunker(counter).chunk([section])

    assert chunks[-1].token_count >= MINIMUM
    assert "tiny." in chunks[-1].text


def test_chunk_indices_are_contiguous_across_sections(counter):
    sections = [
        Section(order=i, heading_path=[f"S{i}"], text="one two three.")
        for i in range(3)
    ]

    chunks = make_chunker(counter).chunk(sections)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
