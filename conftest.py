def pytest_addoption(parser):
    parser.addoption("--document_store_type", action="store", default="elasticsearch, faiss, memory, milvus, weaviate")


def pytest_generate_tests(metafunc):
    # Get selected docstores from CLI arg
    document_store_type = metafunc.config.option.document_store_type
    selected_doc_stores = [item.strip() for item in document_store_type.split(",")]

    found_mark_parametrize_document_store = any(
        "document_store" in marker.args[0]
        for marker in metafunc.definition.iter_markers("parametrize")
    )
    # for all others that don't have explicit parametrization, we add the ones from the CLI arg
    if "document_store" in metafunc.fixturenames and not found_mark_parametrize_document_store:
        metafunc.parametrize("document_store", selected_doc_stores, indirect=True)
