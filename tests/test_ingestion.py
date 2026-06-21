from movia_sales_agent.config.knowledge import iter_rag_documents, load_products_seed
from movia_sales_agent.ingestion.chunker import build_document_records


def test_products_seed_has_available_products():
    products = load_products_seed()
    available = [product for product in products if product["status"] == "available"]

    assert {product["slug"] for product in available} == {"movia-captura", "movia-hibrido"}
    assert all(product["setup_price_mxn"] for product in available)


def test_rag_documents_build_chunks_with_metadata():
    records = build_document_records(iter_rag_documents())

    assert records
    assert all(record["source_type"] == "rag" for record in records)
    assert all(record["chunks"] for record in records)
    first_chunk = records[0]["chunks"][0]
    assert first_chunk["metadata"]["source_type"] == "rag"
    assert first_chunk["metadata"]["funnel_stage"] == "pre_purchase"

